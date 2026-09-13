"""In-process LLM completion through the full SENTINEL pipeline.

Used by the run engine (and any module) — same scan→provider→scan path as the HTTP
proxy, minus the network hop. Input is scanned/redacted before the model sees it;
output is scanned/redacted mid-stream with the chunk-boundary-aware scanner.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.sentinel.pipeline import StreamScanner, estimate_tokens, load_rules, meter, scan_messages
from app.sentinel.upstream import pick_provider, stream_completion


async def complete(
    db: AsyncSession,
    tenant_id: str,
    messages: list[dict],
    *,
    model: str | None = None,
    origin_module: str = "engine",
    run_id: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 2048,
    on_delta: Callable[[str], Awaitable[None]] | None = None,
    ml: bool = True,
) -> dict:
    scan = await scan_messages(db, tenant_id, messages, model=model, ml=ml)
    if scan.action == "block":
        await meter(db, tenant_id, blocked=True)
        raise BlockedByGuardrail(scan.hits)

    provider, resolved_model = pick_provider(model)
    scanner = StreamScanner(await load_rules(db, tenant_id, "output"))

    parts: list[str] = []

    async def _emit_delta(safe: str) -> None:
        parts.append(safe)
        if on_delta and safe:
            await on_delta(safe)

    async for delta in stream_completion(
        provider, resolved_model, scan.messages, temperature=temperature, max_tokens=max_tokens
    ):
        await _emit_delta(scanner.add(delta))
    await _emit_delta(scanner.flush())
    content = "".join(parts)

    tokens_in = estimate_tokens("".join(str(m.get("content", "")) for m in scan.messages))
    tokens_out = estimate_tokens(content)
    await meter(db, tenant_id, tokens_in=tokens_in, tokens_out=tokens_out)

    return {
        "content": content,
        "provider": provider,
        "model": resolved_model,
        "usage": {"tokens_in": tokens_in, "tokens_out": tokens_out},
        "guardrails": scanner.hits,
        "origin_module": origin_module,
        "run_id": run_id,
    }


class BlockedByGuardrail(Exception):
    def __init__(self, hits: list[dict]) -> None:
        self.hits = hits
        super().__init__("blocked by sentinel guardrails")
