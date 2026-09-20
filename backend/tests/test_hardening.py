"""Regression tests for the Milestone 1 hardening fixes (audited bugs).

Bug 1 (console auth guard) and bug 3 (blog hydration) are frontend-only and are
covered by `next build` / tsc, not pytest. The rest are exercised here.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.sentinel import proxy as sentinel_proxy


# ── Bug 4: empty messages → OpenAI-shaped 400 (not FastAPI 422) ──────────────
async def test_empty_messages_returns_openai_400(client, auth_headers):
    resp = await client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={"model": "gemini-2.5-flash", "messages": []},
    )
    assert resp.status_code == 400
    err = resp.json()["error"]
    assert err["type"] == "invalid_request_error"
    assert err["param"] == "messages"


async def test_blank_message_content_returns_openai_400(client, auth_headers):
    resp = await client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={"model": "auto", "messages": [{"role": "user", "content": "   "}]},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["type"] == "invalid_request_error"


# ── Bug 5: tool-calling is threaded through and surfaced in the response ──────
async def test_tool_calls_passed_through(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")
    seen: dict = {}

    async def fake_stream_chat(provider, model, messages, **kwargs):
        seen.update(kwargs)
        yield {"type": "tool_calls", "tool_calls": [
            {"id": "call_0", "type": "function",
             "function": {"name": "check_server_status",
                          "arguments": '{"server_id": "db-1"}'}}]}

    monkeypatch.setattr(sentinel_proxy, "stream_chat", fake_stream_chat)

    resp = await client.post(
        "/v1/chat/completions",
        headers=auth_headers,
        json={
            "model": "gemini-2.5-flash",
            "messages": [{"role": "user", "content": "status of db-1?"}],
            "tools": [{"type": "function", "function": {
                "name": "check_server_status",
                "parameters": {"type": "object",
                               "properties": {"server_id": {"type": "string"}}}}}],
            "tool_choice": "auto",
        },
    )
    assert resp.status_code == 200
    assert seen.get("tools"), "tools were not threaded through to the provider layer"
    choice = resp.json()["choices"][0]
    assert choice["finish_reason"] == "tool_calls"
    assert choice["message"]["tool_calls"][0]["function"]["name"] == "check_server_status"


# ── Bug 8: VLM string element ids are coerced to int before validation ───────
def test_operator_validated_coerces_string_element():
    from app.operator.brain import _validated

    elements = [{"id": 4, "tag": "button", "role": "button"}]
    action = _validated({"action": "click", "element": "4"}, elements)
    assert action is not None and action["element"] == 4
    # a non-numeric id is rejected cleanly, never crashes
    assert _validated({"action": "click", "element": "abc"}, elements) is None


# ── Bug 10: GitHub PR flow never KeyErrors on an error response ───────────────
async def test_github_pr_handles_error_response(monkeypatch):
    from app.medic import tools as medic_tools

    monkeypatch.setattr(settings, "github_token", "tok")
    monkeypatch.setattr(settings, "github_repo", "owner/repo")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def make(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(medic_tools.httpx, "AsyncClient", make)
    result = await medic_tools._open_github_pr("payments", "diff-body", "goal text")
    assert result is None  # graceful, no KeyError


# ── Bug 11: durable engine substitutes hyphenated step names ─────────────────
def test_engine_render_handles_hyphenated_step_names():
    from app.core.engine import _render

    out = _render({"prompt": "use {build-image} now"}, {"build-image": "sha256:abc"})
    assert out["prompt"] == "use sha256:abc now"


async def test_retrieved_context_skips_ml_injection_layers(app, auth_headers):
    """Wikipedia-sized retrieved text must still redact PII, not ONNX-block the fold."""
    from app.db import SessionLocal
    from app.sentinel.pipeline import scan_text
    from app.shared.security import decode_access_token

    tid = decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]
    blob = (
        "Answer from THESE live excerpts only.\n"
        "SOURCE 1: https://en.wikipedia.org/wiki/Astraea\n"
        "Astraea is a Greek goddess. Contact editor@wikimedia.org for reuse.\n"
        + ("the star-maiden of justice in the constellation Virgo. " * 40)
    )
    async with SessionLocal() as db:
        full = await scan_text(db, tid, blob, "input", persist=False, ml=True)
        fold = await scan_text(db, tid, blob, "input", persist=False, ml=False)
    assert fold.action != "block"
    assert "[REDACTED:EMAIL]" in fold.text
    assert full.action in ("redact", "allow", "block")  # ML may FP; fold must not


# ── Bug 13: hashed embedder dim matches MiniLM (no ChromaDB dim mismatch) ─────
def test_vector_embedder_dim_matches_minilm():
    from app.shared.vector import _EMBED_DIM, HashedEmbedder

    assert HashedEmbedder.dim == _EMBED_DIM == 384
    vec = HashedEmbedder().encode(["hello world of astraea"])[0]
    assert len(vec) == 384


def test_cors_regex_matches_regional_cloud_run():
    import re

    rx = re.compile(settings.cors_origin_regex)
    assert rx.fullmatch("https://astraea-console-714727365323.us-central1.run.app")
    assert rx.fullmatch("http://127.0.0.1:3000")
    assert rx.fullmatch("https://astraea-api-714727365323.us-central1.run.app")
    assert not rx.fullmatch("https://evil.example.com")


def test_sse_format_json_encodes_dicts():
    import json as _json

    from app.shared.bus import sse_format

    frame = sse_format({"choices": [{"delta": {"content": "hi"}}]})
    assert frame.startswith("data: {")
    payload = _json.loads(frame.removeprefix("data: ").strip())
    assert payload["choices"][0]["delta"]["content"] == "hi"


def test_cloud_run_missing_secrets_boot(monkeypatch):
    from app import config

    prev = (config.settings.jwt_secret, config.settings.ingest_token, config.settings.env)
    monkeypatch.setenv("K_SERVICE", "astraea-api")
    try:
        config.settings.env = "production"
        config.settings.jwt_secret = ""
        config.settings.ingest_token = ""
        config.apply_production_guards()
        assert config.settings.jwt_secret.startswith("cloud-")
        assert config.settings.ingest_token.startswith("cloud-ingest-")
    finally:
        config.settings.jwt_secret, config.settings.ingest_token, config.settings.env = prev


async def test_contact_does_not_claim_email(client):
    resp = await client.post(
        "/api/contact",
        json={"name": "Ada", "email": "ada@example.com", "message": "hello from the lab"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["received"] is True
    assert body["emailed"] is False
    assert "sent" not in body


def test_production_hides_openapi(monkeypatch):
    prev = settings.env
    monkeypatch.setattr(settings, "env", "production")
    try:
        from app.main import create_app

        app = create_app()
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None
    finally:
        settings.env = prev
