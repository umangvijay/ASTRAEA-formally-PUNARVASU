"""Unit tests for the SENTINEL upstream tool-calling wire adapters (bug #5 machinery)."""

from __future__ import annotations

import json

from app.sentinel import upstream


def test_from_openai_accumulates_streamed_tool_calls():
    acc: dict = {}
    # OpenAI streams tool calls as fragments across deltas
    upstream._from_openai(
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "call_1", "function": {"name": "check", "arguments": "{\"a\":"}}]}}]}, acc)
    upstream._from_openai(
        {"choices": [{"delta": {"tool_calls": [
            {"index": 0, "function": {"arguments": "1}"}}]}}]}, acc)
    assert acc[0]["id"] == "call_1"
    assert acc[0]["function"]["name"] == "check"
    assert acc[0]["function"]["arguments"] == '{"a":1}'


def test_from_openai_yields_text_delta():
    out = upstream._from_openai({"choices": [{"delta": {"content": "hello"}}]}, {})
    assert out == [{"type": "text", "text": "hello"}]


def test_from_gemini_collects_function_calls_and_text():
    calls: list = []
    out = upstream._from_gemini(
        {"candidates": [{"content": {"parts": [
            {"text": "sure"},
            {"functionCall": {"name": "book", "args": {"day": "mon"}}}]}}]}, calls)
    assert {"type": "text", "text": "sure"} in out
    assert calls[0]["function"]["name"] == "book"
    assert json.loads(calls[0]["function"]["arguments"]) == {"day": "mon"}


def test_vertex_url_uses_project_and_location(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vertex_project", "astraea-prod")
    monkeypatch.setattr(settings, "vertex_location", "us-central1")
    monkeypatch.setattr(settings, "vertex_access_token", "tok-1")
    monkeypatch.setattr(settings, "vertex_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    url, headers = upstream._gemini_or_vertex_url("vertex", "vertex/gemini-2.5-flash")
    assert "astraea-prod" in url
    assert "us-central1" in url
    assert "gemini-2.5-flash" in url
    assert "streamGenerateContent" in url
    assert headers["Authorization"] == "Bearer tok-1"
    studio, _ = upstream._gemini_or_vertex_url("gemini", "gemini-2.5-flash")
    assert "generativelanguage.googleapis.com" in studio


def test_vertex_ready_needs_project_and_cred(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "vertex_project", "")
    monkeypatch.setattr(settings, "vertex_access_token", "x")
    assert upstream._vertex_ready() is False
    monkeypatch.setattr(settings, "vertex_project", "p")
    monkeypatch.setattr(settings, "vertex_access_token", "")
    monkeypatch.setattr(settings, "vertex_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(upstream, "_vertex_adc_token", lambda: "")
    assert upstream._vertex_ready() is False
    monkeypatch.setattr(settings, "gemini_api_key", "studio")
    assert upstream._vertex_ready() is True
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(upstream, "_vertex_adc_token", lambda: "ya29.adc")
    assert upstream._vertex_ready() is True


def test_pick_provider_never_defaults_to_sql_champion(monkeypatch):
    from app.config import settings
    from app.sentinel.upstream import ProviderUnavailable, pick_provider

    monkeypatch.setattr(settings, "llm_provider_order",
                        "vertex,gemini,anthropic,groq,ollama,model_forge,mlx_local")
    monkeypatch.setattr("app.sentinel.upstream._provider_ready",
                        lambda p: p in ("model_forge", "mlx_local"))
    try:
        pick_provider(None)
        raise AssertionError("specialty models must not be the general fallback")
    except ProviderUnavailable:
        pass
    provider, model = pick_provider("pvu-sql")
    assert provider == "model_forge" and "sql" in model


def test_research_workflow_uses_live_web_tool():
    from app.shared.seed import WORKFLOW_TEMPLATES

    wf = next(t for t in WORKFLOW_TEMPLATES if t["name"] == "research-and-remember")
    assert any(s.get("tool") == "web.research" for s in wf["steps"])
    assert not any(s.get("type") == "llm" for s in wf["steps"])


def test_gemini_tools_and_tool_config_mapping():
    tools = [{"type": "function", "function": {"name": "f", "description": "d",
                                               "parameters": {"type": "object", "properties": {}}}}]
    decls = upstream._gemini_tools(tools)
    assert decls[0]["functionDeclarations"][0]["name"] == "f"
    assert upstream._gemini_tools(None) is None

    assert upstream._gemini_tool_config("auto") is None
    assert upstream._gemini_tool_config("none")["functionCallingConfig"]["mode"] == "NONE"
    assert upstream._gemini_tool_config("required")["functionCallingConfig"]["mode"] == "ANY"
