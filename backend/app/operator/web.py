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
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx

from app.config import settings

BLOCKED_HOSTS = ("localhost", "127.", "0.0.0.0", "10.", "192.168.", "172.16.", "169.254.", "[::1]")
_UA = "Astraea-Operator/0.4 (+https://astraea.local; research)"


def assert_public_url(url: str) -> str:
    """Fast textual guard (edge validation, no DNS). The resolution-based
    check lives in shared/ssrf.py and runs inside fetch/scrape/runner."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("url must be http(s) with a host")
    host = parsed.hostname.lower().rstrip(".")
    if any(host.startswith(b) or host == b.strip(".") for b in BLOCKED_HOSTS):
        raise ValueError("blocked host (private network range)")
    return url


async def _assert_fetchable(url: str) -> None:
    """Full guard before any outbound fetch: textual + DNS resolution."""
    assert_public_url(url)
    from app.shared.ssrf import aassert_public_host

    await aassert_public_host(url)


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


async def _wikipedia_search(query: str, max_results: int) -> list[dict]:
    """Cloud Run-safe fallback — DDG HTML is often empty from datacenter IPs."""
    headers = {
        "User-Agent": "Astraea-Operator/0.4 (research; +https://astraea.local)",
        "Accept": "application/json",
    }
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as client:
        resp = await client.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": query,
                "limit": max_results,
                "namespace": 0,
                "format": "json",
            },
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    titles = data[1] if isinstance(data, list) and len(data) > 1 else []
    descs = data[2] if isinstance(data, list) and len(data) > 2 else []
    urls = data[3] if isinstance(data, list) and len(data) > 3 else []
    out: list[dict] = []
    for i, url in enumerate(urls):
        if not url:
            continue
        out.append({
            "title": (titles[i] if i < len(titles) else query)[:200],
            "url": url,
            "snippet": (descs[i] if i < len(descs) else "")[:280],
        })
        if len(out) >= max_results:
            break
    return out


async def search(query: str, max_results: int = 5) -> list[dict]:
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
            brave = [{"title": r.get("title", ""), "url": r.get("url", ""),
                      "snippet": r.get("description", "")}
                     for r in web[:max_results] if r.get("url")]
            if brave:
                return brave

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
    if not uniq:
        uniq = await _wikipedia_search(q, max_results)
    return uniq


async def fetch_url(url: str, *, limit: int = 4000) -> dict:
    await _assert_fetchable(url)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers={"User-Agent": _UA}) as client:
        resp = await client.get(url)
    extracted = extract_text(resp.text if "html" in resp.headers.get("content-type", "") else resp.text, limit=limit)
    extracted.update({"url": str(resp.url), "status": resp.status_code, "ok": resp.status_code < 400})
    return extracted


_PARAGRAPH = re.compile(r"(?is)<(p|h[1-4]|li|blockquote|td)[^>]*>(.*?)</\1>")
_LINK = re.compile(r'(?is)<a[^>]+href=["\']([^"#\']+)["\']')


def _readable_blocks(html: str, *, max_chars: int) -> list[str]:
    """Main-content blocks in reading order — headings/paragraphs/list items,
    not the whitespace-soup a whole-page tag-strip produces."""
    cleaned = re.sub(r"(?is)<(script|style|noscript|svg|template)[^>]*>.*?</\1>", " ", html)
    blocks: list[str] = []
    total = 0
    for m in _PARAGRAPH.finditer(cleaned):
        tag, inner = m.group(1).lower(), m.group(2)
        text = unescape(re.sub(r"\s+", " ", re.sub(r"(?is)<[^>]+>", " ", inner))).strip()
        if not text:
            continue
        if tag.startswith("h"):
            text = f"## {text}"
        elif tag == "li":
            text = f"- {text}"
        blocks.append(text)
        total += len(text)
        if total >= max_chars:
            break
    if not blocks:
        # no semantic blocks (legacy HTML) — fall back to the whole-page strip
        page = extract_text(html, limit=max_chars)
        return [page["text"]] if page["text"] else []
    return blocks


async def scrape_url(url: str, *, limit: int = 12_000, include_links: bool = True) -> dict:
    """Deep scrape: readable main content in reading order + metadata + links.

    Beyond web.fetch (a 4k text strip) — agents get structured paragraphs,
    headings and outbound links, enough to reason over a real page."""
    await _assert_fetchable(url)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                 headers={"User-Agent": _UA}) as client:
        resp = await client.get(url)
    ok = resp.status_code < 400
    content_type = resp.headers.get("content-type", "")
    html = resp.text if "html" in content_type else ""
    blocks = _readable_blocks(html, max_chars=limit) if html else \
        [resp.text[:limit]] if resp.text.strip() else []
    text = "\n\n".join(blocks)

    links: list[dict] = []
    if include_links and html:
        seen: set[str] = set()
        base = str(resp.url)
        for href in _LINK.findall(html)[:400]:
            absolute = urljoin(base, href.strip())
            if not absolute.startswith(("http://", "https://")):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            links.append({"url": absolute})
            if len(links) >= 25:
                break

    page = extract_text(html, limit=600) if html else {}
    return {
        "url": str(resp.url), "status": resp.status_code, "ok": ok,
        "title": page.get("title", ""), "description": page.get("description", ""),
        "word_count": len(text.split()),
        "content": text[:limit],
        "links": links,
    }


async def research(query: str, *, max_results: int = 4) -> dict:
    hits = await search(query, max_results=max_results)
    pages: list[dict] = []
    for h in hits:
        try:
            page = await fetch_url(h["url"])
            # empty extractions are noise for the synthesizer — skip, never synthesize on them
            if not (page.get("text") or "").strip():
                continue
            pages.append({**h, **page, "source_title": h.get("title")})
        except Exception as exc:  # noqa: BLE001 — one dead link must not abort the pack
            pages.append({**h, "ok": False, "error": str(exc)[:160], "text": ""})
    return {
        "query": query,
        "hits": hits,
        "pages": pages,
        "engine": (
            "wikipedia" if hits and all("wikipedia.org" in (h.get("url") or "") for h in hits)
            else "brave" if settings.brave_api_key
            else "duckduckgo"
        ),
    }
