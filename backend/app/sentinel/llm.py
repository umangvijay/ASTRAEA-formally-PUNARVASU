"""In-process LLM completion through the full SENTINEL pipeline.

Used by the run engine (and any module) — same scan→provider→scan path as the HTTP
proxy, minus the network hop. Input is scanned/redacted before the model sees it;
output is scanned/redacted mid-stream with the chunk-boundary-aware scanner.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import time as _time

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

    from app.sentinel.upstream import ProviderUnavailable, next_ready_provider, pick_provider

    provider, resolved_model = pick_provider(model)
    scanner = StreamScanner(await load_rules(db, tenant_id, "output"))

    parts: list[str] = []
    emitted = False

    async def _emit_delta(safe: str) -> None:
        nonlocal emitted
        parts.append(safe)
        if safe:
            emitted = True
        if on_delta and safe:
            await on_delta(safe)

    # Graceful degradation: a quota-stalled or dead provider hands the call to
    # the next ready one in the configured order — before any token reached the
    # console, so the console never sees a duplicated or half-switched stream.
    # Every attempt is also recorded as an outcome reward (module "llm"):
    # success rate + latency per provider/model accumulate in the scoreboard
    # (/api/benchmarks/llm) — the feedback signal FORGE and the operator use.
    tried: list[str] = [provider]

    async def _reward(prov: str, res_model: str, ok: bool) -> None:
        from app.sentinel.upstream import note_provider_outcome
        from app.shared.benchmarks import record as _record

        ms = round((_time.perf_counter() - t0) * 1000, 1)
        # the circuit breaker reacts in real time; the scoreboard keeps history
        note_provider_outcome(prov, ok)
        try:
            await _record(db, "llm", f"success:{prov}", 1.0 if ok else 0.0,
                          tenant_id=tenant_id, metadata={"model": res_model})
            if ok:
                await _record(db, "llm", f"latency_ms:{prov}", ms,
                              tenant_id=tenant_id, metadata={"model": res_model})
        except Exception:  # noqa: BLE001 — telemetry never breaks the call
            pass

    while True:
        t0 = _time.perf_counter()
        try:
            async for delta in stream_completion(
                provider, resolved_model, scan.messages, temperature=temperature, max_tokens=max_tokens
            ):
                await _emit_delta(scanner.add(delta))
            await _reward(provider, resolved_model, ok=True)
            break
        except ProviderUnavailable:
            await _reward(provider, resolved_model, ok=False)
            if emitted:
                raise
            nxt = next_ready_provider(tried, model)
            if nxt is None:
                raise
            provider, resolved_model = nxt
            tried.append(provider)
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
