"""Durable run queue — the distributed backbone under the run engine (Milestone 2).

A run's authoritative state lives in Postgres/SQLite. Workers CLAIM a queued (or
lease-expired) run atomically, HEARTBEAT while executing, and RELEASE the lease on
terminal/parked states. If a worker dies mid-run, its lease expires and any other
worker re-claims the run, which then resumes from the last completed event (the
event store makes this rework-free).

Postgres uses `SELECT ... FOR UPDATE SKIP LOCKED` for lock-free multi-worker claims.
SQLite (lite/dev) uses a guarded conditional UPDATE — safe for the single-writer
model WAL gives us, and never blocks the in-process fast path.
"""

from __future__ import annotations

import datetime as dt
import os
import socket

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Run
from app.db import engine as _engine

# A run is up for grabs when freshly queued, previously interrupted, or its owning
# worker's lease has expired (crash detection).
CLAIMABLE_STATUSES = ("queued", "interrupted")


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def worker_id() -> str:
    """Stable-per-process worker identity: host + pid."""
    return f"{socket.gethostname()}:{os.getpid()}"


def _is_postgres() -> bool:
    return _engine.url.drivername.startswith("postgresql")


def _claimable_predicate(now: dt.datetime):
    return or_(
        Run.status.in_(CLAIMABLE_STATUSES),
        and_(Run.status == "running", Run.lease_expires_at.is_not(None),
             Run.lease_expires_at < now),
    )


async def enqueue(db: AsyncSession, run_id: str) -> None:
    """Mark a run ready for a worker to claim."""
    run = await db.get(Run, run_id)
    if run is None:
        return
    run.status = "queued"
    run.worker_id = None
    run.lease_expires_at = None
    await db.commit()


async def lease_run(db: AsyncSession, run_id: str, wid: str, lease_seconds: int) -> None:
    """Directly lease a specific run to a worker (the in-process spawn fast path)."""
    now = _now()
    await db.execute(
        update(Run).where(Run.id == run_id).values(
            status="running", worker_id=wid,
            lease_expires_at=now + dt.timedelta(seconds=lease_seconds),
            heartbeat_at=now,
        )
    )
    await db.commit()


async def claim(db: AsyncSession, wid: str, lease_seconds: int) -> str | None:
    """Atomically claim one claimable/lease-expired run. Returns its id or None."""
    now = _now()
    expiry = now + dt.timedelta(seconds=lease_seconds)

    if _is_postgres():
        row = (await db.execute(
            select(Run.id).where(_claimable_predicate(now))
            .order_by(Run.created_at).limit(1)
            .with_for_update(skip_locked=True)
        )).scalar_one_or_none()
        if row is None:
            await db.commit()
            return None
        await db.execute(update(Run).where(Run.id == row).values(
            status="running", worker_id=wid, lease_expires_at=expiry, heartbeat_at=now))
        await db.commit()
        return row

    # SQLite / others: pick a candidate, then claim it with a conditional guard so a
    # racing worker cannot double-claim (the guard fails and we simply return None).
    row = (await db.execute(
        select(Run.id).where(_claimable_predicate(now)).order_by(Run.created_at).limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    result = await db.execute(
        update(Run).where(Run.id == row, _claimable_predicate(now)).values(
            status="running", worker_id=wid, lease_expires_at=expiry, heartbeat_at=now)
    )
    await db.commit()
    return row if result.rowcount else None


async def heartbeat(db: AsyncSession, run_id: str, wid: str, lease_seconds: int) -> bool:
    """Extend the lease. Returns False if the run is no longer ours (lease was stolen)."""
    now = _now()
    result = await db.execute(
        update(Run).where(Run.id == run_id, Run.worker_id == wid).values(
            lease_expires_at=now + dt.timedelta(seconds=lease_seconds), heartbeat_at=now)
    )
    await db.commit()
    return bool(result.rowcount)


async def release(db: AsyncSession, run_id: str, wid: str | None = None) -> None:
    """Drop the lease (on completion, failure, or an approval park)."""
    stmt = update(Run).where(Run.id == run_id)
    if wid is not None:
        stmt = stmt.where(Run.worker_id == wid)
    await db.execute(stmt.values(worker_id=None, lease_expires_at=None))
    await db.commit()


async def requeue_expired(db: AsyncSession) -> int:
    """Return lease-expired running runs to the queue. Atomic: the lease must
    STILL be expired at UPDATE time, so a heartbeat that renewed between the
    scan and the write can never lose its run (no double execution)."""
    now = _now()
    result = await db.execute(
        update(Run).where(
            Run.status == "running", Run.lease_expires_at.is_not(None),
            Run.lease_expires_at < now,
        ).values(status="queued", worker_id=None, lease_expires_at=None)
    )
    await db.commit()
    return result.rowcount or 0
