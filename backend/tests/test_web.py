"""OPERATOR live web: extract / DDG parse / SSRF / tool dispatch — no live network."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.tools import run_tool
from app.operator import web


DDG_HTML = """
<html><body>
<a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FAstraea">Astraea (mythology)</a>
<span class="result__snippet">Greek goddess of justice, later a constellation.</span>
<a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fgithub.com%2Fastronomia">Astronomia on GitHub</a>
<span class="result__snippet">Open-source astronomy tools.</span>
</body></html>
"""

PAGE_A = """
<html><head><title>Wikipedia — Astraea</title>
<meta name="description" content="Star-maiden who returned as Virgo."></head>
<body><p>Astraea is the Greek star-maiden of justice.</p></body></html>
"""
PAGE_B = """
<html><head><title>GitHub · astronomia</title></head>
<body><p>This repository is unrelated mythology text on purpose.</p></body></html>
"""


def test_extract_text_title_and_strips_script():
    html = "<html><head><title> Hello  World </title></head>" \
           "<body><script>evil()</script><p>Visible prose.</p></body></html>"
    out = web.extract_text(html)
    assert out["title"] == "Hello World"
    assert "evil" not in out["text"]
    assert "Visible prose" in out["text"]


def test_ddg_links_unwrap_uddg_and_are_unique():
    hits = web._ddg_links(DDG_HTML)
    assert [h["url"] for h in hits] == [
        "https://en.wikipedia.org/wiki/Astraea",
        "https://github.com/astronomia",
    ]
    assert "justice" in hits[0]["snippet"].lower()
    assert hits[0]["title"] != hits[1]["title"]


def test_assert_public_url_blocks_loopback():
    with pytest.raises(ValueError):
        web.assert_public_url("http://127.0.0.1/secret")
    with pytest.raises(ValueError):
        web.assert_public_url("https://192.168.1.9/x")
    assert web.assert_public_url("https://en.wikipedia.org/wiki/Astraea").startswith("https://")


@pytest.mark.asyncio
async def test_research_pages_are_per_url_not_a_template():
    hits = [
        {"title": "Astraea", "url": "https://en.wikipedia.org/wiki/Astraea", "snippet": "goddess"},
        {"title": "Repo", "url": "https://github.com/astronomia", "snippet": "code"},
    ]

    async def fake_fetch(url: str, **_kw):
        body = PAGE_A if "wikipedia" in url else PAGE_B
        extracted = web.extract_text(body)
        extracted.update({"url": url, "status": 200, "ok": True})
        return extracted

    with patch.object(web, "search", AsyncMock(return_value=hits)), \
            patch.object(web, "fetch_url", side_effect=fake_fetch):
        pack = await web.research("astraea constellation", max_results=2)

    texts = [p["text"] for p in pack["pages"]]
    assert pack["pages"][0]["url"] != pack["pages"][1]["url"]
    assert texts[0] != texts[1]
    assert "star-maiden" in texts[0].lower()
    assert "repository" in texts[1].lower()


@pytest.mark.asyncio
async def test_web_search_tool_dispatch(app):
    hits = [{"title": "T", "url": "https://example.com/a", "snippet": "s"}]
    with patch.object(web, "search", AsyncMock(return_value=hits)):
        out = await run_tool(None, None, "web.search", {"query": "hello", "max_results": 3})
    assert out["ok"] is True
    assert out["hits"][0]["url"] == "https://example.com/a"


@pytest.mark.asyncio
async def test_research_endpoint_returns_distinct_pages(client, auth_headers):
    pack = {
        "query": "astraea",
        "engine": "duckduckgo",
        "hits": [
            {"title": "A", "url": "https://en.wikipedia.org/wiki/Astraea", "snippet": "one"},
            {"title": "B", "url": "https://github.com/astronomia", "snippet": "two"},
        ],
        "pages": [
            {"url": "https://en.wikipedia.org/wiki/Astraea", "title": "Wiki",
             "text": "star-maiden of justice", "ok": True, "status": 200},
            {"url": "https://github.com/astronomia", "title": "GH",
             "text": "unrelated repository readme", "ok": True, "status": 200},
        ],
    }
    mock_complete = AsyncMock(return_value={
        "content": "Cite https://en.wikipedia.org/wiki/Astraea",
        "provider": "ollama", "model": "llama3.2",
    })
    with patch.object(web, "research", AsyncMock(return_value=pack)), \
            patch("app.sentinel.llm.complete", mock_complete):
        resp = await client.post(
            "/api/operator/research",
            headers=auth_headers,
            json={"query": "astraea", "max_results": 2, "synthesize": True},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pages"][0]["text"] != body["pages"][1]["text"]
    assert body["synthesis"]["text"].startswith("Cite")
    assert mock_complete.await_args.kwargs.get("ml") is False


@pytest.mark.asyncio
async def test_run_task_skips_walled_garden_after_research(app, auth_headers):
    from app.shared.security import decode_access_token

    tenant_id = decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]
    pack = {
        "query": "what is astraea",
        "engine": "duckduckgo",
        "hits": [{"title": "A", "url": "https://en.wikipedia.org/wiki/Astraea", "snippet": "s"}],
        "pages": [{
            "url": "https://en.wikipedia.org/wiki/Astraea", "title": "Astraea",
            "text": "the star-maiden who returned", "ok": True, "snippet": "s",
        }],
    }
    from app.core import engine
    from app.core.models import Run
    from app.db import SessionLocal

    steps = engine.validate_workflow([{
        "name": "operate", "type": "tool", "tool": "operator.run_task",
        "args": {"goal": "what is astraea", "url": "https://www.google.com/search?q=astraea"},
    }])
    async with SessionLocal() as db:
        run = Run(tenant_id=tenant_id, goal="what is astraea",
                  workflow=steps, origin_module="operator")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    with patch.object(web, "research", AsyncMock(return_value=pack)):
        await engine.execute(run_id)

    async with SessionLocal() as db:
        done = await db.get(Run, run_id)
    import json
    result = json.loads(done.result["outputs"]["operate"])
    assert result["success"] is True
    assert result.get("mode") == "web_research"
    assert result.get("browser") == "skipped_walled_garden"
    assert "star-maiden" in result["web"]["pages"][0]["text"]
