"""OPERATOR's brain — decides the next action from the goal, the SoM elements and history.

Chain (auto): Gemini Flash vision (free tier) → Ollama qwen2.5vl (local) → heuristic
planner. The heuristic planner is NOT a canned script: it scores every visible element
against the goal with token/role matching and extracts parameters (search terms,
credentials) from the goal text — computed, data-driven, and fully inspectable.
Every tier speaks the same JSON action contract:

    {"action": "click|type|press|select|scroll|done|fail",
     "element": <id>, "text": "<for typing>", "reason": "..."}
"""

from __future__ import annotations

import json
import re

import httpx

from app.config import settings

INPUT_ROLES = {"text", "search", "email", "password", "tel", "textarea", None}


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z0-9]+", text or "")}


def _score(element: dict, words: set[str]) -> float:
    hay = " ".join([element.get("text", ""), element.get("placeholder", ""),
                    element.get("name_attr", ""), element.get("href", ""),
                    element.get("role", ""), element.get("tag", "")]).lower()
    toks = _tokens(hay)
    if not toks:
        return 0.0
    score = sum(1 for w in words if w in toks) / (1 + len(toks) ** 0.5)
    text = (element.get("text") or "").strip().lower()
    if text and text in words:
        score += 0.6  # exact label match beats partial overlap
    return score


def _extract_quoted(goal: str) -> str | None:
    m = re.search(r"[\"'“]([^\"'”]{1,60})[\"'”]", goal)
    if m:
        return m.group(1)
    m = re.search(r"search(?: for|ing)?\s+(?:the\s+)?(?:term\s+)?([A-Za-z0-9 '\-]{2,50})", goal, re.I)
    return m.group(1).strip() if m else None


async def decide(goal: str, elements: list[dict], history: list[dict], som_png: bytes | None) -> dict:
    """Pick the next action. Tiers: gemini → ollama → heuristic."""
    for provider in ("gemini", "ollama"):
        if settings.operator_vlm not in ("auto", provider):
            continue
        try:
            action = await _decide_vlm(goal, elements, history, som_png, provider)
            if action:
                return {**action, "brain": provider}
        except Exception:  # noqa: BLE001 — fall through to the next tier
            continue
    return {**heuristic(goal, elements, history), "brain": "heuristic"}


async def _decide_vlm(goal: str, elements: list[dict], history: list[dict],
                      som_png: bytes | None, provider: str) -> dict | None:
    listing = "\n".join(
        f"[{e['id']}] {e['role']}: {(e.get('text') or e.get('placeholder') or '')[:60]}"
        for e in elements
    )
    hist = "\n".join(f"- {h}" for h in history[-6:])
    instruction = (
        f"GOAL: {goal}\nRECENT ACTIONS:\n{hist or '(none)'}\nVISIBLE ELEMENTS:\n{listing}\n\n"
        'Reply with STRICT JSON only: {"action": "click|type|press|scroll|done|fail", '
        '"element": <id>, "text": "<text to type, if any>", "reason": "<one line>"}'
    )
    if provider == "gemini":
        if not settings.gemini_api_key or som_png is None:
            return None
        body = {
            "contents": [{"parts": [
                {"text": instruction},
                {"inline_data": {"mime_type": "image/png", "data": __import__("base64").b64encode(som_png).decode()}},
            ]}],
            "generationConfig": {"temperature": 0.1},
        }
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"{settings.gemini_default_model}:generateContent?key={settings.gemini_api_key}")
        async with httpx.AsyncClient(timeout=25) as client:
            resp = (await client.post(url, json=body)).json()
        text = resp["candidates"][0]["content"]["parts"][0]["text"]
        parsed = _parse_json(text)
        return _validated(parsed, elements)
    # ollama vision
    body = {
        "model": "qwen2.5vl:7b",
        "messages": [{"role": "user", "content": instruction,
                      "images": [__import__("base64").b64encode(som_png).decode() if som_png else ""]}],
        "format": "json", "stream": False,
    }
    async with httpx.AsyncClient(timeout=40) as client:
        resp = (await client.post(f"{settings.ollama_base_url.replace('/v1', '')}/api/chat", json=body)).json()
    parsed = _parse_json(resp.get("message", {}).get("content", ""))
    return _validated(parsed, elements)


def _parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _validated(action: dict | None, elements: list[dict]) -> dict | None:
    if not action or action.get("action") not in ("click", "type", "press", "select", "scroll", "done", "fail"):
        return None
    # VLMs frequently emit string element ids (e.g. {"element": "4"}); coerce to int
    # so the membership check below doesn't silently discard a valid decision (bug #8).
    if action.get("element") is not None:
        try:
            action["element"] = int(str(action["element"]).strip())
        except (ValueError, TypeError):
            action["element"] = None
    ids = {e["id"] for e in elements}
    if action["action"] in ("click", "type", "select") and action.get("element") not in ids:
        return None
    return action


def heuristic(goal: str, elements: list[dict], history: list[dict]) -> dict:
    """Evidence-based planner: scores real elements against the real goal. No canned moves."""
    goal_l = goal.lower()
    words = _tokens(goal)
    stop = {"the", "a", "an", "on", "in", "of", "to", "and", "with", "for", "open", "go",
            "click", "type", "into", "as", "user", "password", "page", "site", "then",
            "search", "log", "login", "enter", "fill", "submit", "form"}
    content_words = words - stop

    inputs = [e for e in elements if e["tag"] in ("input", "textarea") and e.get("role") != "hidden"]
    password = next((e for e in inputs if e.get("role") == "password"), None)
    search_like = [e for e in inputs if e.get("role") in ("search", "text") or "search" in (e.get("placeholder", "") + e.get("text", "")).lower() or e.get("tag") == "textarea"]
    buttons = [e for e in elements if e["tag"] == "button"
               or e.get("role") in ("button", "link", "submit")
               or e["tag"] == "a"]

    # 1. quoted / extracted parameter → type it into the best matching input
    param = _extract_quoted(goal)
    cred_user = re.search(r"user(?:name)?\s+(\w+)", goal_l)
    cred_pass = re.search(r"password\s+(\w+)", goal_l)

    typed = [h for h in history if h.get("action") == "type"]
    last_type = max((i for i, h in enumerate(history) if h.get("action") == "type"), default=None)
    acted_since_type = last_type is not None and any(
        h.get("action") in ("press", "click") for h in history[last_type + 1:])

    # loop guard: an element clicked 2+ times AT THE SAME URL is a no-op loop —
    # ids are per-parse, so cross-navigation repeats (pagination "Next") stay legal
    noop_clicks: dict[object, int] = {}
    for h in history:
        if h.get("action") == "click" and h.get("changed_pct", 0) < 0.05 and h.get("url_before"):
            key = (h.get("element"), h.get("url_before"))
            noop_clicks[key] = noop_clicks.get(key, 0) + 1
    dead = {el for (el, _url), n in noop_clicks.items() if n >= 2}
    buttons = [e for e in buttons if e["id"] not in dead]
    inputs = [e for e in inputs if e["id"] not in dead]
    search_like = [e for e in search_like if e["id"] not in dead]

    if password and cred_pass and not any("password" in h.get("note", "") for h in typed):
        return {"action": "type", "element": password["id"], "text": cred_pass.group(1),
                "reason": "password field matches the goal's credential"}
    if cred_user and search_like and not any("username" in h.get("note", "") for h in typed):
        user_input = next((e for e in inputs
                           if "user" in (e.get("text", "") + e.get("placeholder", "")).lower()
                           or e.get("role") in ("email", "text")), None)
        if user_input:
            return {"action": "type", "element": user_input["id"], "text": cred_user.group(1),
                    "reason": "username field matches the goal's credential"}
    if param and search_like and not typed:
        best = max(search_like, key=lambda e: _score(e, words | {"search"}))
        return {"action": "type", "element": best["id"], "text": param,
                "reason": f"input matches goal parameter '{param}'"}

    # 2. after typing without any follow-up action, submit the input
    if last_type is not None and not acted_since_type:
        if password and typed:
            # login form: Enter in the last typed field submits natively — far more
            # reliable than coordinate-clicking the submit button
            return {"action": "press", "element": typed[-1].get("element"), "text": "Enter",
                    "reason": "press Enter to submit the login form"}
        submit = next((e for e in buttons
                       if _score(e, {"search", "go", "submit", "login", "sign in", "next"}) > 0), None)
        if submit:
            return {"action": "click", "element": submit["id"], "reason": "submit the typed input"}
        if search_like:
            return {"action": "press", "element": search_like[0]["id"], "text": "Enter",
                    "reason": "press Enter to submit the search"}

    # 3. pagination: goals that mention pages/forward map to "next" controls
    if words & {"page", "forward", "next", "browse", "more", "continue"}:
        next_el = next((e for e in buttons if "next" in (e.get("text", "")).lower()), None)
        if next_el:
            return {"action": "click", "element": next_el["id"],
                    "reason": "goal asks to advance pages; clicking the next control"}

    # 3b. click the element whose text best matches the goal — never one already tried
    scored = [(e, _score(e, content_words)) for e in buttons + inputs]
    scored = [(e, s) for e, s in scored if s > 0]
    tried = {(h.get("element")) for h in history if h.get("action") == "click"}
    fresh = [(e, s) for e, s in scored if e["id"] not in tried]
    if fresh:
        best, score = max(fresh, key=lambda pair: pair[1])
        return {"action": "click", "element": best["id"],
                "reason": f"best text match for the goal (score {score:.2f})"}
    if scored:
        best, score = max(scored, key=lambda pair: pair[1])
        return {"action": "click", "element": best["id"],
                "reason": f"re-clicking the strongest remaining match (score {score:.2f})"}

    # 5. last resort before giving up: scroll (content may be below the fold) —
    # but never more than twice: nothing matched above the fold either
    scrolls = sum(1 for h in history if h.get("action") == "scroll")
    if scrolls >= 2:
        return {"action": "fail", "reason": "no element plausibly advances this goal (scrolled twice)"}
    return {"action": "scroll", "reason": "no matching element in viewport — scroll to reveal more"}
