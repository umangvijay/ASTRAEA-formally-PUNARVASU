"""Milestone 2 gate: durable distributed run queue.

Proves runs survive a worker crash and are resumed exactly (no rework) by another
worker once the dead worker's lease expires — decoupled from `asyncio.create_task`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from app.core import engine, queue
from app.core import worker as run_worker
from app.core.models import Run, RunEvent
from app.db import SessionLocal
from app.shared.security import decode_access_token

THREE_STEPS = [
    {"name": "s1", "type": "tool", "tool": "shell", "args": {"command": "echo one"}},
    {"name": "s2", "type": "tool", "tool": "shell", "args": {"command": "echo two"}},
    {"name": "s3", "type": "tool", "tool": "shell", "args": {"command": "echo three"}},
]


def _tid(auth_headers) -> str:
    return decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]


async def _make_run(tenant_id: str, steps: list[dict]) -> str:
    async with SessionLocal() as db:
        run = Run(tenant_id=tenant_id, goal="durable run", origin_module="console",
                  workflow=engine.validate_workflow(steps), status="queued")
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id


async def _run(run_id: str) -> Run:
    async with SessionLocal() as db:
        return await db.get(Run, run_id)


async def _events(run_id: str) -> list[RunEvent]:
    async with SessionLocal() as db:
        return list((await db.execute(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.id)
        )).scalars().all())


async def test_worker_claims_and_completes_a_queued_run(auth_headers):
    run_id = await _make_run(_tid(auth_headers), THREE_STEPS)

    claimed = await run_worker.claim_and_run("worker-A:1", lease_seconds=30)
    assert claimed == run_id

    run = await _run(run_id)
    assert run.status == "completed"
    assert run.worker_id is None and run.lease_expires_at is None  # lease released
    assert run.result["outputs"]["s3"] == "three"


async def test_claim_is_exclusive(auth_headers):
    run_id = await _make_run(_tid(auth_headers), THREE_STEPS)
    async with SessionLocal() as db:
        first = await queue.claim(db, "worker-A:1", lease_seconds=30)
    async with SessionLocal() as db:
        second = await queue.claim(db, "worker-B:2", lease_seconds=30)
    assert first == run_id
    assert second is None, "a live-leased run must not be claimable by a second worker"


async def test_dead_worker_lease_expires_and_second_worker_resumes(auth_headers):
    """Worker A claims + completes s1, then 'crashes' (lease left in the past).
    Worker B must requeue the expired run and resume from s2 without re-running s1."""
    run_id = await _make_run(_tid(auth_headers), THREE_STEPS)

    # ── Worker A claims and completes step s1, then dies mid-run ──
    async with SessionLocal() as db:
        assert await queue.claim(db, "worker-A:1", lease_seconds=30) == run_id
        db.add(RunEvent(run_id=run_id, type="step_completed", node="s1",
                        payload={"content": "one", "ok": True, "tool": "shell"}))
        await db.commit()
    # simulate the crash: the lease is now stale (heartbeat stopped)
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        run.lease_expires_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        await db.commit()

    # ── Worker B ticks: requeues the expired run, claims it, resumes ──
    claimed = await run_worker.claim_and_run("worker-B:2", lease_seconds=30)
    assert claimed == run_id

    run = await _run(run_id)
    assert run.status == "completed", run.error
    assert run.worker_id is None  # lease released after completion

    starts = [e.node for e in await _events(run_id) if e.type == "step_started"]
    assert starts.count("s1") == 0, "completed step re-executed after crash"
    assert starts.count("s2") == 1 and starts.count("s3") == 1
    assert run.result["outputs"]["s3"] == "three"


async def test_requeue_ignores_live_lease(auth_headers):
    run_id = await _make_run(_tid(auth_headers), THREE_STEPS)
    async with SessionLocal() as db:
        assert await queue.claim(db, "worker-A:1", lease_seconds=30) == run_id
    async with SessionLocal() as db:
        assert await queue.requeue_expired(db) == 0  # fresh lease must be left alone
    assert (await _run(run_id)).status == "running"


async def test_spawn_runs_under_a_lease_and_survives_as_durable(auth_headers):
    """The API fast path (spawn) executes in-process but under the durable lease."""
    run_id = await _make_run(_tid(auth_headers), THREE_STEPS)
    engine.spawn(run_id)
    from app.core import engine as _e
    await _e.wait_all(timeout=15)
    # give the supervise task a moment to release the lease after completion
    import asyncio
    for _ in range(50):
        run = await _run(run_id)
        if run.status == "completed" and run.worker_id is None:
            break
        await asyncio.sleep(0.05)
    run = await _run(run_id)
    assert run.status == "completed"
    assert run.result["outputs"]["s3"] == "three"
