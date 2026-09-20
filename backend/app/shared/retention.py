"""Retention sweeper — the platform watches itself, so every telemetry table needs a TTL.

Without one, self-observation fills the disk in days (2.2M security_events + 556k
metric_points in a single audit day) and buries the user's real approval queue under
self-generated incidents. Every threshold is env-tunable (ASTRAEA_RETENTION_*); nothing
here is hardcoded per the spec's anti-hardcoding rule.

Deletes are batched (LIMIT-subquery) so no single statement holds sqlite's write
lock long enough to starve user requests.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

from sqlalchemy import delete, select, update

from app.config import settings
from app.core.models import Run, RunEvent
from app.db import SessionLocal
from app.pulse.models import Anomaly, LogRecord, MetricPoint
from app.sentinel.models import GuardrailEvent
from app.shield.models import SecurityEvent

logger = logging.getLogger("shared.retention")

_loop_task: asyncio.Task | None = None

_TERMINAL_RUN_STATUSES = ("completed", "failed", "interrupted")


def _cutoff(days: int) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)


async def _exec(stmt, *, commit: bool = False):
    async with SessionLocal() as db:
        result = await db.execute(stmt)
        if commit:
            await db.commit()
        return result


async def _batched_delete(table, where, *, batch: int | None = None) -> int:
    """Delete matching rows in bounded batches; returns rows removed."""
    step = max(100, batch or settings.retention_batch_size)
    budget = max(step, settings.retention_max_rows_per_sweep)
    removed = 0
    floor_id = 0
    while removed < budget:
        ids = (
            await _exec(
                select(table.id).where(where, table.id > floor_id).order_by(table.id).limit(step)
            )
        ).scalars().all()
        if not ids:
            break
        await _exec(delete(table).where(table.id.in_(ids)), commit=True)
        removed += len(ids)
        floor_id = ids[-1]
        if len(ids) < step:
            break
    if removed:
        logger.info("retention: pruned %d row(s) from %s",
                    removed, getattr(table, "__tablename__", table))
    return removed


async def expire_stale_approvals() -> int:
    """Runs parked at an approval gate forever are not durability — they are a leak of
    queue attention. Auto-fail after retention_approval_days (default 7) so the user's
    decision list stays honest. The run's events remain for replay."""
    days = max(1, settings.retention_approval_days)
    async with SessionLocal() as db:
        result = await db.execute(
            update(Run)
            .where(Run.status == "awaiting_approval", Run.updated_at < _cutoff(days))
            .values(
                status="failed",
                error=f"expired: approval not granted within {days} day(s) — run again to re-request",
            )
        )
        await db.commit()
    if result.rowcount:
        logger.warning("retention: expired %d approval-gated run(s) older than %d day(s)",
                       result.rowcount, days)
    return result.rowcount


async def sweep() -> dict[str, int]:
    """One retention pass over every append-heavy table."""
    if not settings.retention_enabled:
        return {}

    summary: dict[str, int] = {}

    metric_cutoff = _cutoff(max(1, settings.retention_metric_days))
    summary["metric_points"] = await _batched_delete(MetricPoint, MetricPoint.ts < metric_cutoff)
    summary["log_records"] = await _batched_delete(LogRecord, LogRecord.ts < metric_cutoff)

    anomaly_cutoff = _cutoff(max(1, settings.retention_anomaly_days))
    summary["anomalies"] = await _batched_delete(Anomaly, Anomaly.detected_at < anomaly_cutoff)

    security_cutoff = _cutoff(max(1, settings.retention_security_days))
    summary["security_events"] = await _batched_delete(
        SecurityEvent, SecurityEvent.ts < security_cutoff)
    summary["guardrail_events"] = await _batched_delete(
        GuardrailEvent, GuardrailEvent.created_at < security_cutoff)

    # Run events are the run engine's replay substrate — only prune those whose run
    # is terminal (nothing will ever resume from them) and old.
    event_cutoff = _cutoff(max(1, settings.retention_run_event_days))
    candidate_run_ids = (
        await _exec(
            select(RunEvent.run_id)
            .where(RunEvent.created_at < event_cutoff)
            .distinct()
            .limit(settings.retention_max_rows_per_sweep)
        )
    ).scalars().all()
    pruned_events = 0
    for chunk_start in range(0, len(candidate_run_ids), 500):
        chunk = candidate_run_ids[chunk_start:chunk_start + 500]
        done_ids = (
            await _exec(
                select(Run.id).where(
                    Run.id.in_(chunk), Run.status.in_(_TERMINAL_RUN_STATUSES)
                )
            )
        ).scalars().all()
        if not done_ids:
            continue
        pruned_events += await _batched_delete(RunEvent, RunEvent.run_id.in_(done_ids))
    summary["run_events"] = pruned_events

    summary["expired_runs"] = await expire_stale_approvals()
    return summary


async def loop() -> None:
    while True:
        try:
            summary = await sweep()
            if any(summary.values()):
                logger.info("retention sweep: %s", summary)
        except Exception:  # noqa: BLE001 — retention must never take the API down
            logger.exception("retention sweep failed")
        await asyncio.sleep(max(300, settings.retention_interval_seconds))


def start() -> None:
    global _loop_task
    if _loop_task is None or _loop_task.done():
        _loop_task = asyncio.get_running_loop().create_task(loop())
        logger.info("retention sweeper on (every %ss)",
                    max(300, settings.retention_interval_seconds))


def stop() -> None:
    global _loop_task
    if _loop_task:
        _loop_task.cancel()
        _loop_task = None
