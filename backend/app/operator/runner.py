"""The OPERATOR task loop: parse → decide → act → verify → replan, streamed live.

Runs as an engine tool (`operator.run_task`) so every task is a durable, auditable
run step — and publishes per-action events to the run's SSE topic for the console.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.operator import memory, parser
from app.operator.brain import decide
from app.operator.executor import BrowserSession, pixel_diff_pct
from app.shared.bus import publish

MAX_REPLANS = 3


async def run_task(db: AsyncSession, run, args: dict) -> dict:
    goal = str(args.get("goal") or "")
    url = args.get("url")
    html = args.get("html")  # local task content (tests / offline tasks)
    success_kind = args.get("success_kind", "url_contains")
    success_value = args.get("success_value", "")
    if not goal or not (url or html):
        raise ValueError("operator.run_task needs a goal and a url (or html)")

    session = BrowserSession()
    actions_taken: list[dict] = []
    result: dict = {"success": False, "steps": 0, "replans": 0}

    async def emit(event: dict) -> None:
        # persisted AND live — replay shows the whole action trail, not just a live tail
        from app.core.engine import _emit

        await _emit(db, run, "operator_progress", node="operator", payload=event)

    try:
        # Live web research first when the goal is to find/read public pages —
        # Google/ChatGPT/Claude/Cursor walls all look the same to a headless browser.
        if url and not html:
            from urllib.parse import parse_qs, urlparse

            from app.operator import web as webmod

            host = (urlparse(url).hostname or "").lower()
            research_hosts = (
                "google.", "bing.", "duckduckgo.", "chatgpt.com", "claude.ai",
                "cursor.com", "github.com", "wikipedia.org", "openai.com",
            )
            walled = (
                "google.", "bing.", "duckduckgo.", "chatgpt.com", "claude.ai",
                "cursor.com", "github.com", "openai.com",
            )
            looks_research = any(h in host for h in research_hosts) or any(
                w in goal.lower() for w in ("search", "find", "what is", "who is", "look up")
            )
            if looks_research:
                q = goal
                if "q=" in url:
                    q = parse_qs(urlparse(url).query).get("q", [goal])[0] or goal
                pack = await webmod.research(q, max_results=4)
                result["web"] = pack
                pages_ok = [
                    p for p in (pack.get("pages") or [])
                    if p.get("ok") and (p.get("text") or p.get("snippet"))
                ]
                unique = {(p.get("url"), (p.get("text") or "")[:120]) for p in pages_ok}
                await emit({"kind": "web_research", "query": q, "engine": pack.get("engine"),
                            "urls": [h.get("url") for h in pack.get("hits", [])],
                            "unique_pages": len(unique)})
                if unique:
                    result.update(success=True, mode="web_research",
                                  web_unique_pages=len(unique))
                    try:
                        from app.loom import service as loom

                        await loom.write_item(
                            db, run.tenant_id, origin_module="operator", origin_run_id=run.id,
                            kind="research", title=f"Web research: {q[:80]}",
                            summary=(pages_ok[0].get("text") or "")[:400],
                            payload={"query": q, "engine": pack.get("engine"),
                                     "urls": [h.get("url") for h in pack.get("hits", [])]},
                            share_with=["medic", "shield", "vaani", "forge"],
                        )
                    except Exception:  # noqa: BLE001 — memory write must not fail the task
                        pass
                    if any(h in host for h in walled):
                        result["browser"] = "skipped_walled_garden"
                        result["final_url"] = url
                        result["actions"] = []
                        result["goal"] = goal
                        return {"content": json.dumps(result, default=str),
                                "success": True, "steps": 0, "replans": 0,
                                "mode": "web_research"}

        try:
            await session.start()
            if html:
                await session.load_html(html)
            else:
                await session.fresh_page()
                await session.goto(url)
        except Exception as exc:  # noqa: BLE001 — research pack can still stand
            result["browser_error"] = str(exc)[:240]
            await emit({"kind": "browser_degraded", "reason": result["browser_error"]})
            if result.get("success"):
                result["final_url"] = url
                result["actions"] = actions_taken
                result["goal"] = goal
                return {"content": json.dumps(result, default=str),
                        "success": True, "steps": result.get("steps", 0),
                        "replans": result.get("replans", 0),
                        "mode": result.get("mode")}
            raise

        trajectory = await memory.retrieve(db, run.tenant_id, goal)
        if trajectory:
            await emit({"kind": "trajectory_reused", "trajectory_id": trajectory["trajectory_id"],
                        "overlap": trajectory["overlap"]})
            result["reused_trajectory"] = True
            replayed = await _replay(session, trajectory.get("actions", []), actions_taken, emit)
            if replayed and await _success(session.page, success_kind, success_value):
                result.update(success=True, steps=len(actions_taken))
            # if replay fell short, the live brain takes over below

        consecutive_noops = 0
        for step_no in range(1, settings.operator_max_steps + 1):
            if await _success(session.page, success_kind, success_value):
                result.update(success=True, steps=step_no - 1)
                break

            raw_png, som_png, elements = await parser.parse_page(session.page)
            action = await decide(goal, elements, actions_taken, som_png)
            if action["action"] in ("done", "fail") and action["action"] == "fail":
                result["last_reason"] = action.get("reason", "planner gave up")
                break

            before_raw, _, _ = await parser.parse_page(session.page)
            before_url = session.page.url
            before_text = await session.page.inner_text("body")
            await emit({"kind": "action", "step": step_no, "action": action,
                        "url": before_url})

            try:
                outcome = await session.perform(action, elements)
                if outcome.get("done"):
                    result.update(steps=step_no)
                    break
            except Exception as exc:  # noqa: BLE001 — failed action = replan signal
                consecutive_noops += 1
                result["replans"] += 1
                await emit({"kind": "replan", "step": step_no,
                            "reason": f"action failed: {str(exc)[:120]}"})
                if consecutive_noops >= MAX_REPLANS:
                    result["last_reason"] = "too many failed actions"
                    break
                continue

            after_raw, _, _ = await parser.parse_page(session.page)
            after_text = await session.page.inner_text("body")
            changed_pct = pixel_diff_pct(before_raw, after_raw)
            effective = (changed_pct > 0.05 or session.page.url != before_url
                         or after_text[:2000] != before_text[:2000])
            actions_taken.append({
                "action": action["action"], "element": action.get("element"),
                "text": action.get("text", ""), "url_before": before_url,
                "changed_pct": changed_pct,
                "note": action.get("reason", ""),
            })
            await emit({"kind": "verified", "step": step_no, "changed_pct": changed_pct,
                        "effective": effective})

            if not effective:
                consecutive_noops += 1
                result["replans"] += 1
                await emit({"kind": "replan", "step": step_no, "reason": "no page change detected"})
                if action["action"] == "scroll":
                    result["last_reason"] = "no matching element on the page (scroll exhausted)"
                    break
                if consecutive_noops >= MAX_REPLANS:
                    result["last_reason"] = "actions stopped changing the page"
                    break
            else:
                consecutive_noops = 0
            result["steps"] = step_no

        if session.page and await _success(session.page, success_kind, success_value):
            result.update(success=True)
        result["final_url"] = session.page.url if session.page else url
        result["actions"] = actions_taken
    finally:
        await session.close()

    print(f"[save] success={result.get('success')} n_actions={len(actions_taken)}", flush=True)
    if result.get("success") and actions_taken:
        try:
            trajectory_id = await memory.save(
                db, run.tenant_id, origin_run_id=run.id, goal=goal,
                url=result.get("final_url", url or "local"), actions=actions_taken,
            )
            result["trajectory_id"] = trajectory_id
        except Exception as exc:  # TEMP DEBUG: surface the real error
            raise

    result["goal"] = goal
    return {"content": json.dumps(result, default=str), "success": result["success"],
            "steps": result.get("steps", 0), "replans": result.get("replans", 0)}


async def _success(page, kind: str, value: str) -> bool:
    if not value:
        return False
    if kind == "url_contains":
        return value.lower() in page.url.lower()
    if kind == "content_contains":
        return value.lower() in (await page.inner_text("body")).lower()
    if kind == "content_not_contains":
        return value.lower() not in (await page.inner_text("body")).lower()
    raise ValueError(f"unknown success predicate '{kind}'")

async def _replay(session: BrowserSession, saved: list[dict], actions_taken: list[dict], emit) -> bool:
    """Replay a remembered action sequence. Any failure hands control back to the live brain."""
    try:
        for saved_action in saved:
            raw, som, elements = await parser.parse_page(session.page)
            el = next((e for e in elements if e.get("text", "")[:80] == (saved_action.get("text") or "")
                       and e["tag"] != "input"), None)
            if el is None and saved_action.get("action") == "type":
                el = next((e for e in elements if e["tag"] in ("input", "textarea")), None)
            if el is None and saved_action.get("element") is not None:
                el = next((e for e in elements if e["id"] == saved_action["element"]), None)
            if el is None:
                return False
            action = {"action": saved_action["action"], "element": el["id"], "text": saved_action.get("text", "")}
            await emit({"kind": "action", "replay": True, "action": action, "url": session.page.url})
            await session.perform(action, elements)
            actions_taken.append({**action, "replayed": True})
        return True
    except Exception:  # noqa: BLE001 — replay is an optimization, never a requirement
        return False