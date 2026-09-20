"""Retention sweeper: bounded self-observation (audit HIGH-3).

The platform records its own traffic; without TTLs every telemetry table grows
unbounded and the approval queue drowns in self-generated runs.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select

from app.core.models import Run, RunEvent
from app.db import SessionLocal
from app.pulse.models import Anomaly, MetricPoint
from app.sentinel.models import GuardrailEvent
from app.shield.models import SecurityEvent
from app.shared import retention


async def test_sweep_prunes_old_telemetry_and_keeps_fresh(app):
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    async with SessionLocal() as db:
        db.add(MetricPoint(tenant_id="t-ret", service="svc", ts=old,
                           request_rate=1.0, error_rate=0.0, p95_latency=1.0, cpu=1.0))
        db.add(MetricPoint(tenant_id="t-ret", service="svc",
                           request_rate=1.0, error_rate=0.0, p95_latency=1.0, cpu=1.0))
        db.add(Anomaly(tenant_id="t-ret", service="svc", detected_at=old,
                       score=0.5, metrics={}, evidence={}))
        db.add(SecurityEvent(tenant_id="t-ret", host="h", event="login_failure", ts=old))
        db.add(GuardrailEvent(tenant_id="t-ret", direction="input", rule_name="r",
                              action="flag", count=1, sample="s", created_at=old))
        await db.commit()

    summary = await retention.sweep()

    assert summary["metric_points"] >= 1
    assert summary["anomalies"] >= 1
    assert summary["security_events"] >= 1
    assert summary["guardrail_events"] >= 1
    async with SessionLocal() as db:
        left = (await db.execute(
            select(func.count()).select_from(MetricPoint)
            .where(MetricPoint.tenant_id == "t-ret")
        )).scalar()
    assert left == 1  # the fresh point survives


async def test_stale_approval_runs_are_expired(app):
    """A run parked at an approval gate forever leaks queue attention — the
    sweeper auto-fails it after the retention window."""
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    async with SessionLocal() as db:
        run = Run(tenant_id="t-ret", goal="await forever", workflow=[], origin_module="medic",
                  status="awaiting_approval", created_at=old, updated_at=old)
        db.add(run)
        await db.commit()
        run_id = run.id

    summary = await retention.sweep()
    assert summary["expired_runs"] >= 1
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        assert run.status == "failed"
        assert "expired" in (run.error or "")


async def test_fresh_approval_runs_are_untouched(app):
    async with SessionLocal() as db:
        run = Run(tenant_id="t-ret", goal="still deciding", workflow=[], origin_module="medic",
                  status="awaiting_approval")
        db.add(run)
        await db.commit()
        run_id = run.id

    await retention.sweep()
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        assert run.status == "awaiting_approval"  # approval may legitimately take days


async def test_run_events_of_terminal_runs_are_pruned(app):
    """Run events are the replay substrate — only terminal runs may lose them."""
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    async with SessionLocal() as db:
        done = Run(tenant_id="t-ret", goal="g", workflow=[], origin_module="medic",
                   status="completed", created_at=old, updated_at=old)
        parked = Run(tenant_id="t-ret", goal="g", workflow=[], origin_module="medic",
                     status="awaiting_approval", created_at=old, updated_at=old)
        db.add_all([done, parked])
        await db.flush()
        db.add(RunEvent(run_id=done.id, type="step_completed", node="triage", created_at=old))
        db.add(RunEvent(run_id=parked.id, type="step_completed", node="triage", created_at=old))
        await db.commit()
        done_id, parked_id = done.id, parked.id

    summary = await retention.sweep()
    assert summary["run_events"] >= 1
    async with SessionLocal() as db:
        left = (await db.execute(select(RunEvent).where(RunEvent.run_id.in_([done_id, parked_id]))
                                 )).scalars().all()
    assert {e.run_id for e in left} == {parked_id}  # parked run keeps its history
