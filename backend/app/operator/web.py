"""Live web search / fetch / research — real pages, never a canned answer.

OPERATOR's computer-use loop cannot read Google/GitHub/ChatGPT the same way a
logged-in human does (bot walls, logins). This module is the honest path for
*finding and reading* the public web:

  web.search   — DuckDuckGo (no key) or Brave if ASTRAEA_BRAVE_API_KEY is set
  web.fetch    — HTTP GET + HTML extract, SSRF-guarded
  web.research — search → fetch top hits → structured excerpts (optional LLM fold)

Every result carries the live URL and extracted text from *that* request.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from app.config import settings

BLOCKED_HOSTS = ("localhost", "127.", "0.0.0.0", "10.", "192.168.", "172.16.", "169.254.", "[::1]")
_UA = "Astraea-Operator/0.4 (+https://astraea.local; research)"


def assert_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("url must be http(s) with a host")
    host = parsed.hostname.lower()
    if any(host.startswith(b) or host == b.strip(".") for b in BLOCKED_HOSTS):
        raise ValueError("blocked host (private network range)")
    return url


def extract_text(html: str, *, limit: int = 4000) -> dict:
    """Strip scripts/styles and return title + text. Deterministic, no LLM."""
    raw = html or ""
    raw = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", raw)
    title_m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    title = unescape(re.sub(r"\s+", " ", title_m.group(1)).strip()) if title_m else ""
    desc_m = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', raw)
    if not desc_m:
        desc_m = re.search(r'(?is)content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', raw)
    description = unescape(desc_m.group(1).strip()) if desc_m else ""
    text = re.sub(r"(?is)<[^>]+>", " ", raw)
    text = unescape(re.sub(r"\s+", " ", text)).strip()
    return {"title": title[:240], "description": description[:400], "text": text[:limit]}


def _ddg_links(html: str) -> list[dict]:
    """Parse DuckDuckGo HTML results (uddg= unwrap)."""
    out: list[dict] = []
    for m in re.finditer(
        r'(?is)<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
    ):
        href, label = m.group(1), re.sub(r"<[^>]+>", "", m.group(2))
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            href = unquote(qs.get("uddg", [href])[0])
        title = unescape(re.sub(r"\s+", " ", label)).strip()
        if href.startswith("http") and title:
            out.append({"title": title[:200], "url": href, "snippet": ""})
        if len(out) >= 8:
            break
    # snippets sit next to results
    snippets = re.findall(r'(?is)<a?[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</', html)
    for i, snip in enumerate(snippets[: len(out)]):
        out[i]["snippet"] = unescape(re.sub(r"<[^>]+>", " ", snip))[:280].strip()
    return out


async def search(query: str, *, max_results: int = 5) -> list[dict]:
    q = (query or "").strip()
    if not q:
        raise ValueError("search requires a query")
    max_results = max(1, min(int(max_results), 8))
    headers = {"User-Agent": _UA}

    if settings.brave_api_key:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": q, "count": max_results},
                headers={**headers, "X-Subscription-Token": settings.brave_api_key},
            )
            resp.raise_for_status()
            web = (resp.json().get("web") or {}).get("results") or []
            return [{"title": r.get("title", ""), "url": r.get("url", ""),
                     "snippet": r.get("description", "")} for r in web[:max_results] if r.get("url")]

    # DuckDuckGo Instant Answer (JSON) + HTML results — both live, no key
    hits: list[dict] = []
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as client:
        inst = await client.get("https://api.duckduckgo.com/",
                                params={"q": q, "format": "json", "no_html": 1, "skip_disambig": 1})
        if inst.status_code == 200:
            body = inst.json()
            if body.get("AbstractURL"):
                hits.append({"title": body.get("Heading") or q, "url": body["AbstractURL"],
                             "snippet": (body.get("AbstractText") or "")[:280]})
            for t in body.get("RelatedTopics") or []:
                if isinstance(t, dict) and t.get("FirstURL"):
                    hits.append({"title": re.sub(r"<[^>]+>", "", t.get("Text") or "")[:200],
                                 "url": t["FirstURL"], "snippet": (t.get("Text") or "")[:280]})

        html = await client.post("https://html.duckduckgo.com/html/",
                                 data={"q": q},
                                 headers={**headers, "Content-Type": "application/x-www-form-urlencoded"})
        if html.status_code == 200:
            hits.extend(_ddg_links(html.text))

    seen: set[str] = set()
    uniq: list[dict] = []
    for h in hits:
        u = h.get("url") or ""
        if u and u not in seen:
            seen.add(u)
            uniq.append(h)
        if len(uniq) >= max_results:
            break
    return uniq


async def fetch_url(url: str, *, limit: int = 4000) -> dict:
    assert_public_url(url)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": _UA}) as client:
        resp = await client.get(url)
    extracted = extract_text(resp.text if "html" in resp.headers.get("content-type", "") else resp.text, limit=limit)
    extracted.update({"url": str(resp.url), "status": resp.status_code, "ok": resp.status_code < 400})
    return extracted


async def research(query: str, *, max_results: int = 4) -> dict:
    hits = await search(query, max_results=max_results)
    pages: list[dict] = []
    for h in hits:
        try:
            page = await fetch_url(h["url"])
            pages.append({**h, **page, "source_title": h.get("title")})
        except Exception as exc:  # noqa: BLE001 — one dead link must not abort the pack
            pages.append({**h, "ok": False, "error": str(exc)[:160], "text": ""})
    return {
        "query": query,
        "hits": hits,
        "pages": pages,
        "engine": "brave" if settings.brave_api_key else "duckduckgo",
    }
