"""Upstream LLM providers with the mandated fallback chain: gemini → groq → ollama.

Every provider is normalized to the same interface: an async iterator of text deltas.
OpenAI-style messages in, text deltas out — SENTINEL's proxy and the run engine share this.
Ollama (local, keyless) is always the terminal fallback; if nothing is reachable we raise
ProviderUnavailable and the caller degrades gracefully — never a hardcoded canned answer.
"""

from __future__ import annotations

import json
import logging
import socket
import time
from collections.abc import AsyncIterator
from urllib.parse import urlparse

import httpx

from app.config import settings


class ProviderUnavailable(Exception):
    pass


_ollama_probe: tuple[float, bool] | None = None  # (timestamp, reachable) — 60s cache


def _ollama_up() -> bool:
    """A configured base_url is not the same as a running daemon — probe it."""
    global _ollama_probe
    now = time.time()
    if _ollama_probe and now - _ollama_probe[0] < 60:
        return _ollama_probe[1]
    parsed = urlparse(settings.ollama_base_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 11434
    try:
        with socket.create_connection((host, port), timeout=0.5):
            ok = True
    except OSError:
        ok = False
    _ollama_probe = (now, ok)
    return ok


_adc_token: tuple[float, str] | None = None


def _vertex_adc_token() -> str:
    """Get a Vertex OAuth token from ADC, with a Cloud Run metadata fallback."""
    global _adc_token

    now = time.time()
    if _adc_token and now - _adc_token[0] < 240 and _adc_token[1]:
        return _adc_token[1]

    token = ""
    log = logging.getLogger(__name__)

    # Preferred path: Google Application Default Credentials.
    try:
        import google.auth
        from google.auth.transport.requests import Request

        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )

        if not creds.valid:
            creds.refresh(Request())

        token = creds.token or ""

        if token:
            log.info("Vertex ADC token acquired via google-auth")

    except Exception as exc:
        log.warning(
            "Vertex google-auth ADC unavailable: %s: %s",
            type(exc).__name__,
            str(exc),
        )

    # Cloud Run fallback: fetch an OAuth token directly from the metadata server.
    if not token:
        try:
            import urllib.request

            req = urllib.request.Request(
                "http://metadata.google.internal/computeMetadata/v1/"
                "instance/service-accounts/default/token",
                headers={"Metadata-Flavor": "Google"},
            )

            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))

            token = str(payload.get("access_token") or "")

            if token:
                log.info("Vertex ADC token acquired via Cloud Run metadata server")
            else:
                log.warning("Cloud Run metadata server returned no access token")

        except Exception as exc:
            log.warning(
                "Vertex metadata ADC unavailable: %s: %s",
                type(exc).__name__,
                str(exc),
            )

    _adc_token = (now, token)
    return token


def _vertex_ready() -> bool:
    """Return whether Vertex is configured and an OAuth credential is obtainable."""
    log = logging.getLogger(__name__)

    if not settings.vertex_project:
        log.warning("Vertex provider not ready: ASTRAEA_VERTEX_PROJECT is empty")
        return False

    if settings.vertex_access_token or settings.vertex_api_key or settings.gemini_api_key:
        return True

    token = _vertex_adc_token()

    if not token:
        log.warning(
            "Vertex provider not ready: project=%s location=%s but no ADC token",
            settings.vertex_project,
            settings.vertex_location,
        )

    return bool(token)


def _provider_ready(provider: str) -> bool:
    if provider == "vertex":
        return _vertex_ready()
    if provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if provider == "gemini":
        return bool(settings.gemini_api_key)
    if provider == "groq":
        return bool(settings.groq_api_key)
    if provider == "model_forge":
        from app.model_forge.serving import available

        return available()
    if provider == "mlx_local":
        from app.model_forge.serving import base_available

        return base_available()
    if provider == "ollama":
        return bool(settings.ollama_base_url) and _ollama_up()
    return False


def pick_provider(model: str | None) -> tuple[str, str]:
    """Returns (provider, model). Model name hints route to a provider; else first ready in order."""
    model = model or ""
    hint = None
    if model.startswith("vertex"):
        hint = "vertex"
    elif model.startswith("claude"):
        hint = "anthropic"
    elif model.startswith("gemini"):
        hint = "vertex" if _vertex_ready() and not settings.gemini_api_key else "gemini"
    elif model in ("pvu-sql", "model_forge"):
        hint = "model_forge"
    elif model:
        hint = "groq"

    order = settings.provider_order
    if hint and hint in order and _provider_ready(hint):
        return hint, _default_model(hint, model)

    # SQL / on-device specialists are never the general-chat fallback — they
    # hallucinate tools and "research". Hint pvu-sql / model_forge to use them.
    specialty = {"model_forge", "mlx_local"}
    for provider in order:
        if provider in specialty and hint != provider:
            continue
        if _provider_ready(provider):
            return provider, _default_model(provider, model)
    raise ProviderUnavailable(
        "no general LLM provider configured — set ASTRAEA_VERTEX_PROJECT (GCloud), "
        "GEMINI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, or run Ollama locally "
        "(the SQL champion is only used when you ask for pvu-sql / model_forge)"
    )


def _default_model(provider: str, model: str) -> str:
    if model:
        return model
    return {
        "vertex": settings.vertex_default_model,
        "gemini": settings.gemini_default_model,
        "anthropic": settings.anthropic_default_model,
        "groq": settings.groq_default_model,
        "mlx_local": "qwen2.5-0.5b-mlx",
        "model_forge": "pvu-sql-champion",
        "ollama": settings.ollama_default_model,
    }[provider]


def _gemini_tools(tools: list[dict] | None) -> list[dict] | None:
    """Convert OpenAI `tools` declarations into Gemini `functionDeclarations`."""
    if not tools:
        return None
    decls = []
    for t in tools:
        fn = t.get("function", t) if isinstance(t, dict) else {}
        if not fn.get("name"):
            continue
        decls.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return [{"functionDeclarations": decls}] if decls else None


def _gemini_tool_config(tool_choice) -> dict | None:
    """Map OpenAI tool_choice to Gemini functionCallingConfig."""
    if tool_choice in (None, "auto"):
        return None
    if tool_choice == "none":
        mode = "NONE"
    elif tool_choice in ("required", "any"):
        mode = "ANY"
    else:  # {"type":"function","function":{"name":...}} → force that one
        return {"functionCallingConfig": {"mode": "ANY"}}
    return {"functionCallingConfig": {"mode": mode}}


async def stream_chat(
    provider: str, model: str, messages: list[dict], *, temperature: float = 0.4,
    max_tokens: int = 2048, tools: list[dict] | None = None, tool_choice=None,
) -> AsyncIterator[dict]:
    """Provider-agnostic chat stream.

    Yields event dicts:
      {"type": "text", "text": "..."}          — a content delta
      {"type": "tool_calls", "tool_calls": [...]} — accumulated OpenAI-format tool calls

    Raises ProviderUnavailable on connect errors. This is the single seam every
    caller shares; `stream_completion` is the text-only view used by the engine.
    """
    timeout = httpx.Timeout(settings.llm_timeout_seconds, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if provider in ("gemini", "vertex"):
                system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
                contents = [
                    {
                        "role": "model" if m.get("role") == "assistant" else "user",
                        "parts": [{"text": str(m.get("content", ""))}],
                    }
                    for m in messages
                    if m.get("role") in ("user", "assistant")
                ]
                body: dict = {"contents": contents,
                              "generationConfig": {"temperature": temperature,
                                                   "maxOutputTokens": max_tokens}}
                if system:
                    body["systemInstruction"] = {"parts": [{"text": system}]}
                gtools = _gemini_tools(tools)
                if gtools:
                    body["tools"] = gtools
                    cfg = _gemini_tool_config(tool_choice)
                    if cfg:
                        body["toolConfig"] = cfg
                url, headers = _gemini_or_vertex_url(provider, model)
                calls: list[dict] = []
                async with client.stream("POST", url, json=body, headers=headers) as resp:
                    if resp.status_code != 200:
                        detail = (await resp.aread()).decode()[:300]
                        raise ProviderUnavailable(f"{provider} {resp.status_code}: {detail}")
                    async for payload in _iter_sse(resp.aiter_lines()):
                        for ev in _from_gemini(payload, calls):
                            yield ev
                if calls:
                    yield {"type": "tool_calls", "tool_calls": calls}
            elif provider == "anthropic":
                async for ev in _stream_anthropic(client, model, messages, temperature, max_tokens, tools):
                    yield ev
            elif provider == "mlx_local":
                from app.model_forge.serving import generate_base

                text = generate_base(messages, max_tokens=max_tokens)
                if text:
                    yield {"type": "text", "text": text}
            elif provider == "model_forge":
                from app.model_forge.serving import generate as forge_generate

                text = forge_generate(
                    "\n".join(str(m.get("content", "")) for m in messages),
                    model_path=settings.forge_model_path or None,
                    max_tokens=max_tokens)
                if text:
                    yield {"type": "text", "text": text}
            else:  # groq / ollama — OpenAI-compatible
                base = settings.groq_base_url if provider == "groq" else settings.ollama_base_url
                headers = (
                    {"Authorization": f"Bearer {settings.groq_api_key}"} if provider == "groq" else {}
                )
                req: dict = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    req["tools"] = tools
                    if tool_choice is not None:
                        req["tool_choice"] = tool_choice
                acc: dict[int, dict] = {}
                async with client.stream(
                    "POST", f"{base}/chat/completions", json=req, headers=headers,
                ) as resp:
                    if resp.status_code != 200:
                        detail = (await resp.aread()).decode()[:300]
                        raise ProviderUnavailable(f"{provider} {resp.status_code}: {detail}")
                    async for payload in _iter_sse(resp.aiter_lines()):
                        for ev in _from_openai(payload, acc):
                            yield ev
                if acc:
                    yield {"type": "tool_calls",
                           "tool_calls": [acc[i] for i in sorted(acc)]}
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(f"{provider} unreachable: {exc}") from exc


async def stream_completion(
    provider: str, model: str, messages: list[dict], *, temperature: float = 0.4,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    """Text-only view over `stream_chat` — the interface the run engine relies on."""
    async for ev in stream_chat(provider, model, messages,
                                temperature=temperature, max_tokens=max_tokens):
        if ev["type"] == "text" and ev.get("text"):
            yield ev["text"]


def _from_openai(payload: dict, acc: dict[int, dict]) -> list[dict]:
    """Interpret one OpenAI-compatible SSE payload; accumulate tool-call fragments."""
    out: list[dict] = []
    try:
        delta = payload["choices"][0].get("delta", {})
    except (KeyError, IndexError, TypeError):
        return out
    if delta.get("content"):
        out.append({"type": "text", "text": delta["content"]})
    for tc in delta.get("tool_calls") or []:
        idx = tc.get("index", 0)
        slot = acc.setdefault(idx, {"id": tc.get("id") or f"call_{idx}",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}})
        if tc.get("id"):
            slot["id"] = tc["id"]
        fn = tc.get("function") or {}
        if fn.get("name"):
            slot["function"]["name"] = fn["name"]
        if fn.get("arguments"):
            slot["function"]["arguments"] += fn["arguments"]
    return out


def _from_gemini(payload: dict, calls: list[dict]) -> list[dict]:
    """Interpret one Gemini SSE payload; collect functionCall parts as tool calls."""
    out: list[dict] = []
    try:
        parts = payload["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return out
    for p in parts:
        if p.get("text"):
            out.append({"type": "text", "text": p["text"]})
        fc = p.get("functionCall")
        if fc and fc.get("name"):
            calls.append({
                "id": f"call_{len(calls)}",
                "type": "function",
                "function": {"name": fc["name"],
                             "arguments": json.dumps(fc.get("args") or {})},
            })
    return out


async def _iter_sse(lines: AsyncIterator[str]) -> AsyncIterator[dict]:
    async for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:").strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def _gemini_or_vertex_url(provider: str, model: str) -> tuple[str, dict]:
    if provider == "vertex":
        loc, proj = settings.vertex_location, settings.vertex_project
        model = model.removeprefix("vertex/")
        host = "aiplatform.googleapis.com" if loc == "global" else f"{loc}-aiplatform.googleapis.com"
        url = (
            f"https://{host}/v1/projects/{proj}/locations/{loc}"
            f"/publishers/google/models/{model}:streamGenerateContent?alt=sse"
        )
        token = settings.vertex_access_token or _vertex_adc_token()
        key = settings.vertex_api_key or (settings.gemini_api_key if not token else "")
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif key:
            url += f"&key={key}"
        return url, headers
    return (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:streamGenerateContent?alt=sse&key={settings.gemini_api_key}",
        {},
    )


async def _stream_anthropic(client: httpx.AsyncClient, model: str, messages: list[dict],
                            temperature: float, max_tokens: int,
                            tools: list[dict] | None):
    system = "\n".join(str(m.get("content", "")) for m in messages if m.get("role") == "system")
    body: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
        "messages": [{"role": m["role"], "content": str(m.get("content", ""))}
                     for m in messages if m.get("role") in ("user", "assistant")],
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = [
            {"name": (t.get("function") or t).get("name"),
             "description": (t.get("function") or t).get("description", ""),
             "input_schema": (t.get("function") or t).get("parameters") or {"type": "object"}}
            for t in tools if (t.get("function") or t).get("name")
        ]
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    async with client.stream("POST", "https://api.anthropic.com/v1/messages",
                             json=body, headers=headers) as resp:
        if resp.status_code != 200:
            detail = (await resp.aread()).decode()[:300]
            raise ProviderUnavailable(f"anthropic {resp.status_code}: {detail}")
        async for line in resp.aiter_lines():
            if not line.startswith("data:"):
                continue
            data = line.removeprefix("data:").strip()
            if data in ("[DONE]", ""):
                continue
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = payload.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                yield {"type": "text", "text": delta["text"]}
