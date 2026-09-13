"""The SENTINEL proxy: an OpenAI-compatible endpoint every LLM call in the platform passes through.

POST /v1/chat/completions
  - authenticates the tenant (X-API-Key or Bearer)
  - scans/redacts the INPUT against DB-driven rules (block → 400, redact → rewrite)
  - enforces the monthly token quota
  - streams from the provider chain (gemini → groq → ollama), scanning/redacting the
    OUTPUT mid-stream with a chunk-boundary-aware scanner
  - meters tokens per tenant and publishes live events to the console
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.sentinel.deps import get_tenant_by_key
from app.shared.deps import get_db
from app.sentinel.pipeline import (
    StreamScanner,
    estimate_tokens,
    load_rules,
    meter,
    quota_state,
    scan_messages,
    scan_text,
)
from app.sentinel.upstream import ProviderUnavailable, pick_provider, stream_chat, stream_completion
from app.shared.bus import publish, sse_format

router = APIRouter(tags=["sentinel"])


class ChatIn(BaseModel):
    model: str | None = None
    # No `min_length`: we validate manually so an empty list returns the standard
    # OpenAI-compatible 400 shape instead of FastAPI's raw 422 (bug #4).
    messages: list[dict] = Field(default_factory=list)
    stream: bool = False
    temperature: float = 0.4
    max_tokens: int = 2048
    tools: list[dict] | None = None
    tool_choice: object | None = None

    model_config = {"extra": "allow"}  # accept (and ignore) other OpenAI fields


def _openai_error(message: str, *, status: int, err_type: str, param: str | None = None,
                  extra: dict | None = None) -> JSONResponse:
    """A response body shaped exactly like the OpenAI API so SDK clients parse it."""
    err = {"message": message, "type": err_type, "param": param, "code": None}
    if extra:
        err.update(extra)
    return JSONResponse(status_code=status, content={"error": err})


async def _events(provider: str, model: str, messages: list[dict], body: "ChatIn"):
    """Unified event stream. Tool-calling requests use the structured `stream_chat`
    seam; plain text requests go through `stream_completion` (the text-only view the
    engine and tests rely on) so its patch points stay intact."""
    if body.tools:
        async for ev in stream_chat(provider, model, messages,
                                    temperature=body.temperature, max_tokens=body.max_tokens,
                                    tools=body.tools, tool_choice=body.tool_choice):
            yield ev
    else:
        async for delta in stream_completion(provider, model, messages,
                                             temperature=body.temperature,
                                             max_tokens=body.max_tokens):
            yield {"type": "text", "text": delta}


@router.post("/v1/chat/completions")
async def chat_completions(body: ChatIn, request: Request,
                           tenant=Depends(get_tenant_by_key), db: AsyncSession = Depends(get_db)):
    t0 = time.perf_counter()

    if not body.messages:
        return _openai_error("'messages' must contain at least one message",
                             status=400, err_type="invalid_request_error", param="messages")
    if not any(str(m.get("content") or "").strip() for m in body.messages if isinstance(m, dict)):
        return _openai_error("'messages' content must not be empty",
                             status=400, err_type="invalid_request_error", param="messages")

    scan = await scan_messages(db, tenant.id, body.messages, model=body.model)
    if scan.action == "block":
        await meter(db, tenant.id, blocked=True)
        await publish(f"sentinel:{tenant.id}", {"kind": "blocked", "hits": scan.hits})
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "type": "guardrail_blocked",
                    "message": "Request blocked by Sentinel guardrails",
                    "rules": [h["rule_name"] for h in scan.hits],
                    "overhead_ms": round((time.perf_counter() - t0) * 1000, 2),
                }
            },
        )

    quota = await quota_state(db, tenant.id)
    if quota["tokens_used"] >= quota["quota"]:
        return _openai_error(
            f"Monthly token quota exhausted ({quota['quota']})",
            status=429, err_type="insufficient_quota",
        )

    messages = getattr(scan, "messages", body.messages)

    try:
        provider, resolved_model = pick_provider(body.model)
    except ProviderUnavailable as exc:
        # graceful degradation: a clear 503, never a canned answer
        return _openai_error(str(exc), status=503, err_type="provider_unavailable")

    if body.stream:
        return StreamingResponse(
            _stream_response(db, tenant.id, provider, resolved_model, messages,
                             body, scan.latency_ms, t0),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # non-streaming: still stream internally, scan, then return one JSON body
    scanner = StreamScanner(await load_rules(db, tenant.id, "output"))
    parts: list[str] = []
    tool_calls: list[dict] = []
    async for ev in _events(provider, resolved_model, messages, body):
        if ev["type"] == "text":
            parts.append(scanner.add(ev["text"]))
        elif ev["type"] == "tool_calls":
            tool_calls = ev["tool_calls"]
    parts.append(scanner.flush())
    content = "".join(parts)

    if scanner.blocked:
        await meter(db, tenant.id, blocked=True)
        return JSONResponse(
            status_code=200,
            content={
                "error": {
                    "type": "output_guardrail_block",
                    "message": "Model output suppressed by Sentinel (block-rule hit)",
                    "rules": [h["rule_name"] for h in scanner.hits],
                }
            },
        )

    tokens_in = estimate_tokens("".join(str(m.get("content", "")) for m in messages))
    tokens_out = estimate_tokens(content)
    await meter(db, tenant.id, tokens_in=tokens_in, tokens_out=tokens_out)
    overhead = round((time.perf_counter() - t0) * 1000, 2)
    await publish(f"sentinel:{tenant.id}", {
        "kind": "completion", "provider": provider, "model": resolved_model,
        "stream": False, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "guardrails": scan.hits + scanner.hits, "overhead_ms": overhead,
    })
    message: dict = {"role": "assistant", "content": content or None}
    finish_reason = "stop"
    if tool_calls:
        message["tool_calls"] = tool_calls
        finish_reason = "tool_calls"
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "model": resolved_model,
        "choices": [{"index": 0, "finish_reason": finish_reason,
                     "message": message}],
        "usage": {"prompt_tokens": tokens_in, "completion_tokens": tokens_out,
                  "total_tokens": tokens_in + tokens_out},
        "astraea": {
            "provider": provider,
            "guardrails": scan.hits + scanner.hits,
            "input_guardrails": scan.hits,
            "output_guardrails": scanner.hits,
            "scan_overhead_ms": overhead,
            "target_overhead_ms": settings.sentinel_overhead_target_ms,
        },
    }


async def _stream_response(db: AsyncSession, tenant_id: str, provider: str, model: str,
                           messages: list[dict], body: ChatIn, input_overhead_ms: float, t0: float):
    def chunk(delta: dict, finish_reason: str | None = None) -> str:
        return sse_format({
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion.chunk",
            "model": model,
            "choices": [{"index": 0, "finish_reason": finish_reason, "delta": delta}],
        })

    yield chunk({"role": "assistant", "content": ""})

    scanner = StreamScanner(await load_rules(db, tenant_id, "output"))
    emitted = 0
    saw_tool_calls = False
    try:
        async for ev in _events(provider, model, messages, body):
            if ev["type"] == "text":
                safe = scanner.add(ev["text"])
                if safe:
                    emitted += len(safe)
                    yield chunk({"content": safe})
            elif ev["type"] == "tool_calls":
                saw_tool_calls = True
                yield chunk({"tool_calls": [
                    {"index": i, **tc} for i, tc in enumerate(ev["tool_calls"])
                ]})
        tail = scanner.flush()
        if tail:
            emitted += len(tail)
            yield chunk({"content": tail})
    except ProviderUnavailable as exc:
        yield sse_format({"error": {"type": "provider_unavailable", "message": str(exc)}})
        return

    if scanner.blocked:
        yield sse_format({"error": {"type": "output_guardrail_block",
                                    "rules": [h["rule_name"] for h in scanner.hits]}})
        await meter(db, tenant_id, blocked=True)
        return

    tokens_in = estimate_tokens("".join(str(m.get("content", "")) for m in messages))
    tokens_out = estimate_tokens("x" * max(emitted, 1))
    await meter(db, tenant_id, tokens_in=tokens_in, tokens_out=tokens_out)
    overhead = round((time.perf_counter() - t0) * 1000, 2)
    await publish(f"sentinel:{tenant_id}", {
        "kind": "completion", "provider": provider, "model": model,
        "stream": True, "tokens_in": tokens_in, "tokens_out": tokens_out,
        "guardrails": scanner.hits, "overhead_ms": overhead,
    })
    yield chunk({}, finish_reason="tool_calls" if saw_tool_calls else "stop")
    yield "data: [DONE]\n\n"
