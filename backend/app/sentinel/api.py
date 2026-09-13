"""SENTINEL management API: rules editor (the anti-hardcoding surface), live event stream, stats."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sentinel.deps import get_tenant_by_key
from app.sentinel.models import GuardrailEvent, GuardrailRule
from app.sentinel.pipeline import quota_state
from app.shared.bus import sse_format, subscribe, unsubscribe
from app.shared.deps import get_db

router = APIRouter(prefix="/api/sentinel", tags=["sentinel"])


class RuleIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    pattern: str = Field(min_length=2)
    scope: str = Field(default="both", pattern="^(input|output|both)$")
    action: str = Field(default="redact", pattern="^(block|redact|flag)$")
    replacement: str = Field(default="[REDACTED]", max_length=60)
    description: str = Field(default="", max_length=300)


class RulePatch(BaseModel):
    enabled: bool | None = None
    action: str | None = Field(default=None, pattern="^(block|redact|flag)$")
    pattern: str | None = None
    replacement: str | None = None


def _rule_out(r: GuardrailRule, *, enabled: bool | None = None, overridden: bool = False) -> dict:
    return {
        "id": r.id, "name": r.name, "description": r.description, "pattern": r.pattern,
        "scope": r.scope, "action": r.action, "replacement": r.replacement,
        "severity": r.severity, "enabled": r.enabled if enabled is None else enabled,
        "global": r.tenant_id is None, "overridden": overridden,
    }


def _event_out(e: GuardrailEvent) -> dict:
    return {
        "id": e.id, "direction": e.direction, "rule_name": e.rule_name, "action": e.action,
        "count": e.count, "sample": e.sample, "model": e.model,
        "latency_ms": e.latency_ms, "at": str(e.created_at),
    }


@router.get("/rules")
async def list_rules(tenant=Depends(get_tenant_by_key), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(GuardrailRule)
            .where((GuardrailRule.tenant_id.is_(None)) | (GuardrailRule.tenant_id == tenant.id))
            .order_by(GuardrailRule.id)
        )
    ).scalars().all()
    # fold tenant overrides into their global parents: one row per rule, with the
    # EFFECTIVE enabled state — never a duplicate row in the console
    overrides = {r.name: r for r in rows if r.tenant_id is not None}
    out = []
    for r in rows:
        if r.tenant_id is not None:
            continue
        ov = overrides.get(r.name)
        if ov is not None:
            out.append(_rule_out(r, enabled=ov.enabled, overridden=True))
        else:
            out.append(_rule_out(r))
    for name, ov in overrides.items():
        if not any(g.name == name for g in rows if g.tenant_id is None):
            out.append(_rule_out(ov))  # tenant-only custom rule
    return {"rules": out}


@router.post("/rules", status_code=201)
async def add_rule(payload: RuleIn, tenant=Depends(get_tenant_by_key),
                   db: AsyncSession = Depends(get_db)):
    import re as _re

    try:
        _re.compile(payload.pattern)
    except _re.error as exc:
        raise HTTPException(status_code=422, detail=f"invalid regex: {exc}")
    rule = GuardrailRule(
        tenant_id=tenant.id, name=payload.name, pattern=payload.pattern, scope=payload.scope,
        action=payload.action, replacement=payload.replacement, description=payload.description,
        severity="custom",
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _rule_out(rule)


@router.patch("/rules/{rule_id}")
async def patch_rule(rule_id: int, payload: RulePatch, tenant=Depends(get_tenant_by_key),
                     db: AsyncSession = Depends(get_db)):
    rule = await db.get(GuardrailRule, rule_id)
    if rule is None or (rule.tenant_id is not None and rule.tenant_id != tenant.id):
        raise HTTPException(status_code=404, detail="rule not found")

    if rule.tenant_id is not None:
        # tenant-owned rule: edit in place
        if payload.enabled is not None:
            rule.enabled = payload.enabled
        if payload.action is not None:
            rule.action = payload.action
        if payload.pattern is not None:
            import re as _re

            try:
                _re.compile(payload.pattern)
            except _re.error as exc:
                raise HTTPException(status_code=422, detail=f"invalid regex: {exc}")
            rule.pattern = payload.pattern
        if payload.replacement is not None:
            rule.replacement = payload.replacement
        await db.commit()
        await db.refresh(rule)
        return _rule_out(rule)

    # global rule: upsert ONE tenant override (same name), reply with the global
    # rule's id so the console's state stays in sync — never a duplicate row
    override = (
        await db.execute(
            select(GuardrailRule).where(
                GuardrailRule.tenant_id == tenant.id, GuardrailRule.name == rule.name
            )
        )
    ).scalars().first()
    if override is None:
        override = GuardrailRule(
            tenant_id=tenant.id, name=rule.name,
            description=f"override of global #{rule.id}",
            pattern=rule.pattern, scope=rule.scope, action=rule.action,
            replacement=rule.replacement, severity="override", enabled=rule.enabled,
        )
        db.add(override)
    if payload.enabled is not None:
        override.enabled = payload.enabled
    if payload.action is not None:
        override.action = payload.action
    if payload.pattern is not None:
        import re as _re

        try:
            _re.compile(payload.pattern)
        except _re.error as exc:
            raise HTTPException(status_code=422, detail=f"invalid regex: {exc}")
        override.pattern = payload.pattern
    if payload.replacement is not None:
        override.replacement = payload.replacement
    await db.commit()
    await db.refresh(override)
    return _rule_out(rule, enabled=override.enabled, overridden=True)


@router.get("/events")
async def events(limit: int = 50, tenant=Depends(get_tenant_by_key),
                 db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(GuardrailEvent)
            .where(GuardrailEvent.tenant_id == tenant.id)
            .order_by(GuardrailEvent.id.desc())
            .limit(min(limit, 200))
        )
    ).scalars().all()
    return {"events": [_event_out(e) for e in rows]}


@router.get("/stats")
async def stats(tenant=Depends(get_tenant_by_key), db: AsyncSession = Depends(get_db)):
    total = (
        await db.execute(
            select(func.count()).select_from(GuardrailEvent).where(GuardrailEvent.tenant_id == tenant.id)
        )
    ).scalar_one()
    blocked = (
        await db.execute(
            select(func.count()).select_from(GuardrailEvent).where(
                GuardrailEvent.tenant_id == tenant.id, GuardrailEvent.action == "block"
            )
        )
    ).scalar_one()
    avg_latency = (
        await db.execute(
            select(func.avg(GuardrailEvent.latency_ms)).where(GuardrailEvent.tenant_id == tenant.id)
        )
    ).scalar_one()
    from app.config import settings

    return {
        "total_events": total,
        "blocked": blocked,
        "avg_scan_latency_ms": round(float(avg_latency or 0), 2),
        "target_overhead_ms": settings.sentinel_overhead_target_ms,
        "quota": await quota_state(db, tenant.id),
    }


@router.get("/stream")
async def stream(request: Request, tenant=Depends(get_tenant_by_key)):
    """Live SSE tail of this tenant's sentinel traffic."""

    async def gen():
        topic = f"sentinel:{tenant.id}"
        queue = subscribe(topic)
        try:
            yield sse_format('{"kind": "connected"}')
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield sse_format(payload)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(topic, queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
