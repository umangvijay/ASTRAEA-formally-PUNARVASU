"""PULSE API: telemetry ingest, chaos injection, series/anomalies, live stream, benchmark."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.pulse import detector
from app.pulse.models import Anomaly, FaultInjection
from app.pulse.store import get_store
from app.sentinel.deps import get_tenant_by_key
from app.shared.bus import sse_format, subscribe, unsubscribe
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/pulse", tags=["pulse"])


async def _resolve_ingest_tenant(request: Request, db: AsyncSession):
    """Demo services authenticate with the internal pipeline token (bound to the
    platform's own system workspace, or X-Tenant-Id); humans/clients use JWT or
    X-API-Key as usual."""
    tok = request.headers.get("X-Internal-Token", "")
    if tok and tok == settings.effective_ingest_token:
        from app.core.models import Tenant

        tid = request.headers.get("X-Tenant-Id")
        if tid:
            tenant = await db.get(Tenant, tid)
        else:
            # prefer the platform's own system workspace; never a random guest
            tenant = (
                await db.execute(
                    select(Tenant).where(Tenant.name == "Astraea HQ")
                    .order_by(Tenant.created_at).limit(1)
                )
            ).scalar_one_or_none()
            if tenant is None:
                tenant = (
                    await db.execute(
                        select(Tenant).where(Tenant.name.notlike("%(guest)%"))
                        .order_by(Tenant.created_at).limit(1)
                    )
                ).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=401, detail="no tenant available for internal ingest")
        return tenant
    return await get_tenant_by_key(request, db)


class IngestIn(BaseModel):
    type: str = Field(pattern="^(metrics|log|deploy)$")
    service: str = Field(min_length=1, max_length=60)
    metrics: dict[str, float] | None = None
    level: str = "INFO"
    message: str = ""
    kind: str = "deploy"
    description: str = ""


@router.post("/ingest")
async def ingest(payload: IngestIn, request: Request, db: AsyncSession = Depends(get_db)):
    tenant = await _resolve_ingest_tenant(request, db)
    store = get_store(db)
    if payload.type == "metrics":
        if not payload.metrics:
            raise HTTPException(status_code=422, detail="metrics payload required")
        await store.add_point(tenant.id, payload.service, payload.metrics)
    elif payload.type == "log":
        await store.add_log(tenant.id, payload.service, payload.level, payload.message)
    else:
        await store.add_deploy(tenant.id, payload.service, payload.kind, payload.description)
    return {"accepted": True}


# ── OTLP/HTTP (JSON) receiver — real OpenTelemetry ingestion ─────────────────
# An OTel Collector/SDK exporter can target these directly. Same auth as /ingest.

@router.post("/v1/logs")
async def otlp_logs(request: Request, db: AsyncSession = Depends(get_db)):
    from app.pulse import otlp

    tenant = await _resolve_ingest_tenant(request, db)
    store = get_store(db)
    payload = await request.json()
    n = 0
    for service, level, message in otlp.parse_logs(payload):
        await store.add_log(tenant.id, service, level, message)
        n += 1
    return {"partialSuccess": {}, "accepted": n}


@router.post("/v1/metrics")
async def otlp_metrics(request: Request, db: AsyncSession = Depends(get_db)):
    from app.pulse import otlp

    tenant = await _resolve_ingest_tenant(request, db)
    store = get_store(db)
    payload = await request.json()
    n = 0
    for service, metrics in otlp.parse_metrics(payload):
        await store.add_point(tenant.id, service, metrics)
        n += 1
    return {"partialSuccess": {}, "accepted": n}


@router.post("/v1/traces")
async def otlp_traces(request: Request, db: AsyncSession = Depends(get_db)):
    from app.pulse import otlp

    tenant = await _resolve_ingest_tenant(request, db)
    store = get_store(db)
    payload = await request.json()
    n = 0
    for service, level, message in otlp.parse_traces(payload):
        await store.add_log(tenant.id, service, level, message)
        n += 1
    return {"partialSuccess": {}, "accepted": n}


class ChaosIn(BaseModel):
    service: str | None = None   # random when omitted
    kind: str | None = None      # random when omitted


@router.post("/chaos")
async def chaos(payload: ChaosIn, user=Depends(get_current_user),
                db: AsyncSession = Depends(get_db)):
    """Inject a fault into live telemetry. Demo services if they are up; otherwise
    the control plane's own series (so Cloud Run MEDIC still has a real MTTD clock)."""
    from app.demo import services as demo
    from app.pulse import live as pulse_live
    from app.pulse.models import FaultInjection
    from app.pulse.store import get_store

    result = None
    try:
        result = await demo.inject_chaos(user.tenant_id, payload.service, payload.kind)
    except (httpx.HTTPError, OSError, TimeoutError, HTTPException):
        result = None
    if not result:
        result = pulse_live.inject_chaos(payload.kind)
        db.add(FaultInjection(tenant_id=user.tenant_id, service=result["service"], kind=result["fault"]))
        await db.commit()
        await get_store(db).add_deploy(
            user.tenant_id, result["service"], "deploy",
            f"chaos:{result['fault']} rolled to {result['service']} (live platform)",
        )
    return result


@router.get("/series/{service}")
async def series(service: str, limit: int = 120, user=Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    store = get_store(db)
    return {"service": service, "points": await store.window(user.tenant_id, service, min(limit, 300))}


@router.get("/anomalies")
async def anomalies(limit: int = 25, user=Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    rows = (
        (await db.execute(
            select(Anomaly).where(Anomaly.tenant_id == user.tenant_id)
            .order_by(desc(Anomaly.id)).limit(min(limit, 100))
        )).scalars().all()
    )
    return {"anomalies": [{
        "id": a.id, "service": a.service, "score": a.score, "metrics": a.metrics,
        "evidence": a.evidence, "run_id": a.run_id, "detected_at": str(a.detected_at),
    } for a in rows]}


@router.get("/stream")
async def stream(request: Request, user=Depends(get_current_user)):
    """Live anomaly stream — the console MEDIC page subscribes here."""
    async def gen():
        topic = f"pulse:{user.tenant_id}"
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


@router.get("/benchmark")
async def benchmark(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The scoreboard: MTTD + top-3 hypothesis accuracy over all injected faults."""
    faults = (
        (await db.execute(
            select(FaultInjection).where(FaultInjection.tenant_id == user.tenant_id)
            .order_by(FaultInjection.id.desc()).limit(50)
        )).scalars().all()
    )
    mttds, hits, total_detected = [], 0, 0
    for f in faults:
        if f.detected_at:
            total_detected += 1
            mttds.append((f.detected_at - f.injected_at).total_seconds())
        if f.anomaly_id:
            anomaly = await db.get(Anomaly, f.anomaly_id)
            if anomaly and anomaly.run_id:
                from app.core.models import Run, RunEvent

                # read the investigate STEP EVENT, not run.result — the run may still
                # be parked at its approval gate when the scoreboard is viewed
                ev = (
                    await db.execute(
                        select(RunEvent).where(
                            RunEvent.run_id == anomaly.run_id,
                            RunEvent.type == "step_completed",
                            RunEvent.node == "investigate",
                        ).order_by(RunEvent.id.desc()).limit(1)
                    )
                ).scalars().first()
                investigation = (ev.payload or {}).get("content", "") if ev else ""
                try:
                    parsed = json.loads(investigation)
                    top3 = [h["service"] for h in parsed.get("hypotheses", [])[:3]]
                except (json.JSONDecodeError, AttributeError, TypeError):
                    top3 = []
                if f.service in top3:
                    hits += 1
    total = len(faults)
    return {
        "faults_injected": total,
        "detected": total_detected,
        "detection_rate": round(total_detected / total, 2) if total else None,
        "mttd_seconds_avg": round(sum(mttds) / len(mttds), 1) if mttds else None,
        "mttd_target_seconds": 120,
        "top3_accuracy": round(hits / total_detected, 2) if total_detected else None,
        "top3_target": 0.7,
        "recent": [{"service": f.service, "kind": f.kind, "injected_at": str(f.injected_at),
                    "detected": f.detected_at is not None} for f in faults[:10]],
    }
