"""The detector: Isolation Forest over each service's multivariate telemetry window.

Learns its baseline from live data (no thresholds hardcoded — the drift guard is a
statistical z-score against the service's OWN recent history). On anomaly: persists
Anomaly, marks the fault-injection detected (benchmark clock stops), publishes to the
bus, and spawns a durable MEDIC run through the core engine.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time

import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy import delete, select

from app.config import settings
from app.core import engine
from app.core.models import Run
from app.db import SessionLocal
from app.pulse.models import Anomaly, FaultInjection, MetricPoint, PulseState
from app.pulse.store import METRIC_COLUMNS, get_store
from app.shared.bus import publish

logger = logging.getLogger("pulse.detector")

_loop_task: asyncio.Task | None = None


async def _self_series_has_open_fault(db, tenant_id: str, service: str) -> bool:
    """True when a chaos fault is live on the self-observation series (MTTD demo)."""
    fault = (
        await db.execute(
            select(FaultInjection.id)
            .where(
                FaultInjection.tenant_id == tenant_id,
                FaultInjection.service == service,
                FaultInjection.detected_at.is_(None),
            )
            .limit(1)
        )
    ).first()
    return fault is not None


async def detect_once(tenant_id: str) -> list[Anomaly]:
    """One detection tick across every service that has live telemetry."""
    anomalies: list[Anomaly] = []
    async with SessionLocal() as db:
        store = get_store(db)
        rows = (
            await db.execute(
                select(MetricPoint.service)
                .where(MetricPoint.tenant_id == tenant_id)
                .group_by(MetricPoint.service)
            )
        ).all()
        services = sorted({r[0] for r in rows})

        # The platform's own live series (astraea-api) must not page MEDIC on its
        # own traffic bursts — that feedback loop (anomaly → run → LLM calls →
        # more traffic → more anomalies) generated 5.8k parked runs and 671MB of
        # events in one audit day. The self-series only pages when a chaos fault
        # is actually injected on it (the MTTD benchmark demo).
        from app.pulse.live import SERVICE as SELF_SERVICE

        for service in services:
            if service == SELF_SERVICE and not await _self_series_has_open_fault(db, tenant_id, service):
                continue
            window = await store.window(tenant_id, service, limit=120)
            if len(window) < 40:
                continue  # not enough live history to have learned a baseline yet

            data = np.array([[p[c] for c in METRIC_COLUMNS] for p in window])
            recent = data[-6:]
            baseline = data[-60:-6] if len(data) >= 60 else data[:-6]

            model = IsolationForest(n_estimators=100, contamination=0.08, random_state=7)
            # train ONLY on pre-recent history — training on the contaminated window
            # teaches the model that the fault is normal (late/missed detections)
            train = baseline if len(baseline) >= 20 else data[:-3]
            model.fit(train)
            score = float(model.decision_function(recent[-1].reshape(1, -1))[0])
            # majority vote across the last 3 live points — one noisy frame can't
            # page a human, and slow burns (memory leaks) still trip it
            votes = model.predict(recent[-3:])
            is_outlier = bool((votes == -1).sum() >= 2)

            b_mean, b_std = baseline.mean(axis=0), baseline.std(axis=0) + 1e-6
            zscores = {
                c: round(float((recent[:, i].mean() - b_mean[i]) / b_std[i]), 2)
                for i, c in enumerate(METRIC_COLUMNS)
            }
            drifted = max(zscores.items(), key=lambda kv: abs(kv[1]))
            significant = abs(drifted[1]) >= settings.anomaly_drift_sigma

            # A constant-emitting service (zero-variance baseline) gives the forest
            # nothing to rank — it scores every point 0.0 and votes "inlier" even
            # for a massive drift. There the z-score against the service's OWN
            # flatlined history is the detector: any deviation is the signal.
            degenerate = bool((baseline.std(axis=0) < 1e-9).any())
            if degenerate:
                is_outlier = significant

            if not (is_outlier and significant and score < 0):
                if not (degenerate and significant):
                    continue

            state = (
                await db.execute(
                    select(PulseState).where(
                        PulseState.tenant_id == tenant_id, PulseState.service == service
                    )
                )
            ).scalar_one_or_none()
            if state is None:
                state = PulseState(tenant_id=tenant_id, service=service, last_baseline={})
                db.add(state)
                await db.flush()
            now = dt.datetime.now(dt.timezone.utc)
            last = state.last_anomaly_at
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=dt.timezone.utc)  # sqlite returns naive UTC
            if last and (now - last).total_seconds() < settings.anomaly_cooldown_seconds:
                # cooldown: don't spawn a new page — but a NEW fault on this host is still
                # attributed to the open incident (the benchmark clock must not fake a miss)
                open_fault = (
                    await db.execute(
                        select(FaultInjection)
                        .where(FaultInjection.tenant_id == tenant_id,
                               FaultInjection.service == service,
                               FaultInjection.detected_at.is_(None))
                        .order_by(FaultInjection.id.desc())
                    )
                ).scalars().first()
                if open_fault:
                    open_fault.detected_at = now
                    await db.commit()
                continue  # one incident = one page
            state.last_anomaly_at = now
            state.healthy = False

            logs = await store.logs(tenant_id, service, limit=8)
            deploys = await store.deploys(tenant_id, service, limit=3)
            anomaly = Anomaly(
                tenant_id=tenant_id, service=service, score=round(score, 4),
                metrics={c: round(float(recent[-1][i]), 2) for i, c in enumerate(METRIC_COLUMNS)},
                evidence={"zscores": zscores, "drifted": drifted[0], "drift_sigma": drifted[1],
                          "recent_logs": logs, "recent_deploys": deploys, "window_points": len(window)},
            )
            db.add(anomaly)
            await db.flush()

            fault = (
                await db.execute(
                    select(FaultInjection)
                    .where(FaultInjection.tenant_id == tenant_id,
                           FaultInjection.service == service,
                           FaultInjection.detected_at.is_(None))
                    .order_by(FaultInjection.id.desc())
                )
            ).scalars().first()
            if fault:
                fault.detected_at = now
                fault.anomaly_id = anomaly.id

            await db.commit()
            await db.refresh(anomaly)

            # Every persisted anomaly must carry its run: if the workflow fails to
            # build, remove the orphan instead of leaving a runless incident behind.
            try:
                run_id = await _create_medic_run(db, anomaly)
                await db.commit()
            except Exception:
                await db.rollback()
                logger.exception("detector: MEDIC run spawn failed — removing orphan anomaly %s",
                                 anomaly.id)
                try:
                    async with SessionLocal() as cleanup:
                        await cleanup.execute(delete(Anomaly).where(Anomaly.id == anomaly.id))
                        await cleanup.commit()
                except Exception:  # noqa: BLE001 — cleanup is best-effort
                    logger.exception("detector: orphan anomaly cleanup failed")
                continue

            anomalies.append(anomaly)

            await publish(f"pulse:{tenant_id}", {
                "kind": "anomaly", "anomaly_id": anomaly.id, "service": service,
                "score": anomaly.score, "drifted": drifted[0], "drift_sigma": drifted[1],
            })
            engine.spawn(run_id)

            # ── Record MTTD benchmark if this was a chaos-injected fault ────────
            if fault and fault.injected_at:
                try:
                    from app.shared.benchmarks import record as record_benchmark
                    injected = fault.injected_at
                    if injected.tzinfo is None:
                        injected = injected.replace(tzinfo=dt.timezone.utc)
                    mttd_s = (now - injected).total_seconds()
                    await record_benchmark(
                        db, "medic", "mttd_seconds", mttd_s,
                        tenant_id=tenant_id,
                        metadata={"service": service, "fault_id": fault.id, "anomaly_id": anomaly.id},
                    )
                except Exception:  # noqa: BLE001 — benchmark recording is best-effort
                    pass
    return anomalies


async def _create_medic_run(db, anomaly: Anomaly) -> str:
    """MEDIC's durable workflow — created in the detector's session, executed by the engine."""
    steps = engine.validate_workflow([
        {"name": "triage", "type": "tool", "tool": "medic.triage", "args": {"anomaly_id": anomaly.id}},
        {"name": "investigate", "type": "tool", "tool": "medic.investigate", "args": {"triage": "{triage}"}},
        {"name": "reproduce", "type": "tool", "tool": "medic.reproduce", "args": {"investigation": "{investigate}"}},
        {"name": "gate", "type": "approval",
         "prompt": "Review the MEDIC investigation above. Approve to generate and apply the fix."},
        {"name": "fix", "type": "tool", "tool": "medic.patch",
         "args": {"investigation": "{investigate}", "reproduce": "{reproduce}"}},
        {"name": "record", "type": "loom_write", "kind": "incident",
         "title": "Incident: {goal}", "summary": "auto-recorded by MEDIC",
         "content": "{investigate}", "share_with": ["shield", "operator", "vaani", "forge"]},
    ])
    run = Run(
        tenant_id=anomaly.tenant_id,
        goal=f"Diagnose and fix {anomaly.service} anomaly (drift in {anomaly.evidence.get('drifted')})",
        workflow=steps, origin_module="medic",
    )
    db.add(run)
    await db.flush()  # generates run.id now — the anomaly keeps a real link
    anomaly.run_id = run.id
    return run.id


async def loop() -> None:
    """The detector heartbeat — MTTD is bounded by this interval (default 10s).
    Honors the tenant's SOLO/FUSION switch: MEDIC only analyzes tenants where
    it is active. Shared memory (LOOM) is unaffected by the switch."""
    while True:
        try:
            from app.shared.workspace import module_active

            async with SessionLocal() as db:
                tenants = (await db.execute(
                    select(MetricPoint.tenant_id).distinct()
                )).scalars().all()
            for tenant_id in tenants:
                async with SessionLocal() as db:
                    if not await module_active(db, tenant_id, "medic"):
                        continue
                await detect_once(tenant_id)
        except Exception:  # noqa: BLE001 — the heartbeat must survive anything
            logger.exception("detector tick failed")
        await asyncio.sleep(settings.detector_interval_seconds)


def start() -> None:
    global _loop_task
    if _loop_task is None or _loop_task.done():
        _loop_task = asyncio.get_running_loop().create_task(loop())


def stop() -> None:
    global _loop_task
    if _loop_task:
        _loop_task.cancel()
        _loop_task = None
