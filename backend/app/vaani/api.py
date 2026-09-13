"""VAANI REST surface: latency metrics, bookings, transcripts."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.vaani.gateway import LATENCIES
from app.vaani.models import VaaniBooking, VaaniTranscript
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/vaani", tags=["vaani"])


@router.get("/metrics")
async def metrics(user=Depends(get_current_user)):
    rows = LATENCIES.get(user.tenant_id, [])
    def p95(key: str):
        vals = sorted(r[key] for r in rows if key in r and r[key] is not None)
        if not vals:
            return None
        return round(vals[max(0, int(len(vals) * 0.95) - 1)], 1)
    return {
        "utterances": len(rows),
        "stt_p95_ms": p95("stt_ms"),
        "brain_p95_ms": p95("brain_ms"),
        "total_p95_ms": p95("total_ms"),
        "target_ms": settings.vaani_latency_target_ms,
        "recent": rows[-10:],
    }


@router.get("/bookings")
async def bookings(limit: int = 25, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        (await db.execute(
            select(VaaniBooking).where(VaaniBooking.tenant_id == user.tenant_id)
            .order_by(desc(VaaniBooking.id)).limit(min(limit, 100))
        )).scalars().all()
    )
    return {"bookings": [{
        "id": b.id, "customer_name": b.customer_name, "service": b.service,
        "scheduled_for": b.scheduled_for, "run_id": b.run_id,
        "created_at": str(b.created_at),
    } for b in rows]}


@router.get("/transcripts")
async def transcripts(limit: int = 10, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        (await db.execute(
            select(VaaniTranscript).where(VaaniTranscript.tenant_id == user.tenant_id)
            .order_by(desc(VaaniTranscript.id)).limit(min(limit, 50))
        )).scalars().all()
    )
    return {"transcripts": [{
        "id": t.id, "turns": t.turns, "outcome": t.outcome, "started_at": str(t.started_at),
    } for t in rows]}
