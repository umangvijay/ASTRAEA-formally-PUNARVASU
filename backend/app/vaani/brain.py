"""VAANI conversation brain + the booking action, executed as durable engine runs.

The brain is the LLM (via SENTINEL, with tenant org profile + knowledge base from LOOM
in the prompt). It must return STRICT JSON: {"reply": "...", "booking": {...}|null}.
When no provider is configured the brain raises ProviderUnavailable — VAANI degrades to
a clear spoken apology, never a canned conversation script.
"""

from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.loom import service as loom


async def respond(db: AsyncSession, tenant_id: str, history: list[dict], user_text: str,
                  *, origin_run_id: str | None = None) -> dict:
    """One conversation turn. Returns {"reply": str, "booking": dict|None, "provider": str}."""
    org = await loom.org_profile(db, tenant_id)
    # RAG over shared memory: everything other agents learned about this business
    kb: list[dict] = []
    try:
        from app.shared import vector

        hits = await vector.asearch(tenant_id, user_text, k=5, module="vaani")
        kb = [{"kind": h["metadata"].get("kind"), "text": h["document"][:200]} for h in hits]
    except Exception:  # noqa: BLE001 — fall back to recency-only context
        kb = []
    if not kb:
        kb = [
            {"kind": i.get("kind", ""), "text": (i.get("summary") or i.get("title", ""))[:200]}
            for i in (await loom.context_for(db, tenant_id, "vaani", limit=5))
        ]
    system = (
        "You are VAANI, the voice assistant for this business. "
        f"Business profile: {json.dumps(org, default=str)}. "
        f"Known context you may use (from the shared memory of all our agents): "
        f"{json.dumps(kb, default=str)[:1500]}. "
        "Speak briefly and warmly (1-3 sentences, natural spoken English). "
        "If the caller wants an appointment, gather their name, the service and the time, "
        "then confirm by returning a booking object. Reply with STRICT JSON only: "
        '{"reply": "...", "booking": {"customer_name": "...", "service": "...", '
        '"scheduled_for": "..."} | null}'
    )
    messages = [{"role": "system", "content": system}]
    messages += [
        {"role": "assistant" if m["role"] == "assistant" else "user", "content": m["text"]}
        for m in history[-10:]
    ]
    messages.append({"role": "user", "content": user_text})

    from app.sentinel.llm import complete

    out = await complete(db, tenant_id, messages, origin_module="vaani", run_id=origin_run_id)
    parsed = _parse_json(out["content"])
    if parsed is None or "reply" not in parsed:
        # the model answered in prose: use it as the reply, no booking this turn
        return {"reply": out["content"].strip()[:400], "booking": None, "provider": out["provider"]}
    return {"reply": parsed["reply"], "booking": parsed.get("booking"), "provider": out["provider"]}


def _parse_json(text: str) -> dict | None:
    import re

    m = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def book(db: AsyncSession, tenant_id: str, booking: dict, *, origin_run_id: str | None = None) -> dict:
    """Confirmed booking → durable row + LOOM artifact stamped FROM VAANI."""
    from app.vaani.models import VaaniBooking

    row = VaaniBooking(
        tenant_id=tenant_id,
        customer_name=str(booking.get("customer_name", "caller"))[:120],
        service=str(booking.get("service", "appointment"))[:120],
        scheduled_for=str(booking.get("scheduled_for", "unspecified"))[:120],
        notes=str(booking.get("notes", "")),
        run_id=origin_run_id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    from app.loom import service as loom

    item = await loom.write_item(
        db, tenant_id, origin_module="vaani", origin_run_id=origin_run_id,
        kind="booking", title=f"Booking: {row.customer_name} — {row.service} @ {row.scheduled_for}",
        summary=f"voice booking confirmed (booking #{row.id})",
        payload={"customer_name": row.customer_name, "service": row.service,
                 "scheduled_for": row.scheduled_for},
        share_with=["medic", "operator", "shield", "forge"],
    )
    return {"booking_id": row.id, "loom_item_id": item.id,
            "customer_name": row.customer_name, "service": row.service,
            "scheduled_for": row.scheduled_for}


def sentences(text: str) -> list[str]:
    """Split a reply into spoken chunks for sentence-level TTS streaming."""
    import re

    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]