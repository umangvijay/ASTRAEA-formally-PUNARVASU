"""SHIELD API: event ingest, lab attack trigger, incidents, live stream, FP drill, benchmark."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shield import lab
from app.shield.detector import detect_once, evaluate_rules
from app.shield.models import SecurityEvent, ShieldIncident
from app.shared.bus import sse_format, subscribe, unsubscribe
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/shield", tags=["shield"])


@router.post("/ingest")
async def ingest(events: list[dict], request: Request, db: AsyncSession = Depends(get_db)):
    """Security-event ingest (lab + external collectors; same auth shape as pulse)."""
    tok = request.headers.get("X-Internal-Token", "")
    if tok and tok == settings.effective_ingest_token:
        from app.core.models import Tenant

        tenant = (
            await db.execute(select(Tenant).order_by(Tenant.created_at).limit(1))
        ).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=401, detail="no tenant available")
        tenant_id = tenant.id
    else:
        user = await get_current_user(request, db)
        tenant_id = user.tenant_id

    accepted = 0
    for ev in events[:200]:
        if lab.is_blocked(ev.get("src_ip"), ev.get("user")):
            ev = {**ev, "blocked": True}  # containment has real effects on the stream
        db.add(SecurityEvent(
            tenant_id=tenant_id, host=ev.get("host", "unknown"), event=ev.get("event", "connection"),
            user=ev.get("user"), src_ip=ev.get("src_ip"), dst_ip=ev.get("dst_ip"),
            dst_port=ev.get("dst_port"), external=bool(ev.get("external")),
            process=ev.get("process"), bytes_out=int(ev.get("bytes_out", 0)),
            blocked=bool(ev.get("blocked")),
        ))
        accepted += 1
    await db.commit()
    return {"accepted": accepted}


class AttackIn(BaseModel):
    scenario: str | None = None   # random when omitted
    target: str | None = None


@router.post("/lab/attack")
async def lab_attack(payload: AttackIn, user=Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    """Fire an attack playbook — random scenario when omitted. Real events hit the ingest."""
    scenario = payload.scenario or __import__("random").choice(lab.SCENARIOS)
    if scenario not in lab.SCENARIOS:
        raise HTTPException(status_code=422, detail=f"unknown scenario '{scenario}'")
    events = lab.scenario_events(scenario, payload.target)
    asyncio.get_running_loop().create_task(
        lab.ingest_events(user.tenant_id, events)
    )  # own sessions, own pace — the detector sees a live attack
    return {"scenario": scenario, "target": payload.target or "random", "events": len(events),
            "note": "events are streaming now — the detector ticks every "
                    f"{settings.shield_detector_interval_seconds}s"}


@router.get("/incidents")
async def incidents(limit: int = 25, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        (await db.execute(
            select(ShieldIncident).where(ShieldIncident.tenant_id == user.tenant_id)
            .order_by(desc(ShieldIncident.id)).limit(min(limit, 100))
        )).scalars().all()
    )
    return {"incidents": [{
        "id": i.id, "host": i.host, "attacker_ip": i.attacker_ip, "severity": i.severity,
        "techniques": i.techniques, "rule_hits": i.rule_hits, "narrative": i.narrative,
        "attack_graph": i.attack_graph, "containment": i.containment, "status": i.status,
        "run_id": i.run_id, "detected_at": str(i.detected_at),
    } for i in rows]}


@router.get("/stream")
async def stream(request: Request, user=Depends(get_current_user)):
    async def gen():
        topic = f"shield:{user.tenant_id}"
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


@router.post("/lab/benign-drill")
async def benign_drill(hours: int = 24, user=Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    """False-positive drill: replay `hours` of compressed benign traffic (30s windows,
    accelerated clock) through the SAME rule evaluator the live detector uses."""
    import time as _t

    from app.shield.models import ShieldRule

    rules = (
        (
            await db.execute(
                select(ShieldRule).where(
                    ShieldRule.enabled.is_(True),
                    (ShieldRule.tenant_id.is_(None)) | (ShieldRule.tenant_id == user.tenant_id),
                )
            )
        )
        .scalars()
        .all()
    )
    rule_dicts = [
        {"name": r.name, "event_types": r.event_types, "threshold": r.threshold,
         "technique_id": r.technique_id, "severity": r.severity, "enabled": r.enabled}
        for r in rules
    ]
    windows = hours * 120  # 30s slices
    flagged = 0
    base = _t.time()
    for w in range(windows):
        events = lab.benign_window(now=base + w * 30)
        if evaluate_rules(events, rule_dicts):
            flagged += 1
    fp_rate = round(flagged / windows, 4) if windows else 0.0
    return {"windows": windows, "flagged": flagged, "false_positive_rate": fp_rate,
            "gate_target": 0.10, "hours_simulated": hours}


@router.get("/benchmark")
async def benchmark(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The scoreboard: lab attack detections + technique mapping + containment."""
    incidents = (
        (await db.execute(
            select(ShieldIncident).where(ShieldIncident.tenant_id == user.tenant_id)
            .order_by(desc(ShieldIncident.id)).limit(50)
        )).scalars().all()
    )
    attacks = [i for i in incidents if i.run_id]
    contained = [i for i in attacks if i.status == "contained"]
    with_techniques = [i for i in attacks if i.techniques]
    return {
        "incidents_total": len(incidents),
        "attacks_correlated": len(attacks),
        "techniques_mapped": len(with_techniques),
        "mapping_rate": round(len(with_techniques) / len(attacks), 2) if attacks else None,
        "contained": len(contained),
        "postmortems_written": len([i for i in attacks if i.status == "contained"]),
        "note": "fire 5 lab attacks (POST /api/shield/lab/attack) and approve containment "
                "in Runs — this scoreboard tracks correlation and mapping.",
    }
