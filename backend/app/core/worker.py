"""Durable run worker (Milestone 2).

Claims runs off the queue and executes them while heartbeating the lease, so a crash
releases the run for another worker. Two entry points share one supervised-execution
core:

- `supervise(run_id)`  — the in-process fast path used by `engine.spawn` (API, detectors).
- `claim_and_run()`    — the pull loop a standalone/background worker runs.

Either way the run holds a lease with a live heartbeat; if this process dies, the lease
expires and `requeue_expired` (run by every worker tick) hands the run to someone else.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from app.config import settings
from app.core import engine, queue
from app.db import SessionLocal

logger = logging.getLogger("core.worker")


async def _heartbeat_loop(run_id: str, wid: str, lease_seconds: int, stop: asyncio.Event) -> None:
    interval = max(1.0, lease_seconds / 3)
    while not stop.is_set():
        try:
            async with SessionLocal() as db:
                alive = await queue.heartbeat(db, run_id, wid, lease_seconds)
            if not alive:
                logger.warning("run %s lease lost by worker %s — stopping heartbeat",
                               run_id[:8], wid)
                return
        except Exception:  # noqa: BLE001 — heartbeat is best-effort; execution continues
            logger.warning("heartbeat error for run %s", run_id[:8], exc_info=True)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval)


async def _run_leased(run_id: str, wid: str, lease_seconds: int) -> None:
    """Execute an already-leased run with a concurrent heartbeat, then release the lease."""
    stop = asyncio.Event()
    hb = asyncio.create_task(_heartbeat_loop(run_id, wid, lease_seconds, stop))
    try:
        await engine.execute(run_id)
    finally:
        stop.set()
        with contextlib.suppress(Exception):
            await hb
        async with SessionLocal() as db:
            await queue.release(db, run_id, wid)


async def supervise(run_id: str, *, lease_seconds: int | None = None) -> None:
    """In-process fast path: lease THIS run to us, then run it under a heartbeat."""
    lease_seconds = lease_seconds or settings.run_lease_seconds
    wid = queue.worker_id()
    async with SessionLocal() as db:
        await queue.lease_run(db, run_id, wid, lease_seconds)
    await _run_leased(run_id, wid, lease_seconds)


async def claim_and_run(wid: str | None = None, lease_seconds: int | None = None) -> str | None:
    """One worker tick: requeue crashed runs, claim one, run it. Returns the run id or None."""
    wid = wid or queue.worker_id()
    lease_seconds = lease_seconds or settings.run_lease_seconds
    async with SessionLocal() as db:
        await queue.requeue_expired(db)
        run_id = await queue.claim(db, wid, lease_seconds)
    if run_id is None:
        return None
    await _run_leased(run_id, wid, lease_seconds)
    return run_id


async def run_worker(stop: asyncio.Event | None = None, *, poll_interval: float | None = None,
                     lease_seconds: int | None = None) -> None:
    """Long-lived pull loop. Cancel via the `stop` event (graceful) or task cancellation."""
    stop = stop or asyncio.Event()
    poll_interval = poll_interval or settings.run_worker_poll_seconds
    wid = queue.worker_id()
    logger.info("run worker %s started (lease=%ss)", wid, lease_seconds or settings.run_lease_seconds)
    try:
        while not stop.is_set():
            try:
                claimed = await claim_and_run(wid, lease_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — one bad run must not kill the loop
                logger.exception("worker %s loop error", wid)
                claimed = None
            if claimed is None:
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=poll_interval)
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("run worker %s stopped", wid)
