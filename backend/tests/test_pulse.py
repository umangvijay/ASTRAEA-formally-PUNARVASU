"""PULSE gate: ingest, series, and anomaly detection with learned baselines."""

from __future__ import annotations

import random

import pytest

from app.pulse import detector
from app.pulse.models import Anomaly, FaultInjection
from app.db import SessionLocal

NORMAL = {"request_rate": 10.0, "error_rate": 0.5, "p95_latency": 80.0, "cpu": 25.0}
FAULT_SHAPES = {
    "error_storm": {"request_rate": 10.0, "error_rate": 40.0, "p95_latency": 90.0, "cpu": 30.0},
    "latency_spike": {"request_rate": 9.0, "error_rate": 1.0, "p95_latency": 900.0, "cpu": 30.0},
    "memory_leak": {"request_rate": 5.0, "error_rate": 2.0, "p95_latency": 120.0, "cpu": 90.0},
    "dependency_failure": {"request_rate": 8.0, "error_rate": 25.0, "p95_latency": 400.0, "cpu": 35.0},
    "config_drift": {"request_rate": 8.0, "error_rate": 8.0, "p95_latency": 500.0, "cpu": 30.0},
}


async def _ingest(client, auth_headers, service, metrics):
    resp = await client.post(
        "/api/pulse/ingest", headers=auth_headers,
        json={"type": "metrics", "service": service, "metrics": metrics},
    )
    assert resp.status_code == 200


def test_live_platform_snapshot_has_sre_columns():
    from app.pulse.live import snapshot
    from app.pulse.store import METRIC_COLUMNS

    m = snapshot()
    assert set(METRIC_COLUMNS) <= set(m)
    assert m["p95_latency"] >= 0


async def test_ingest_and_series(client, auth_headers):
    m = {**NORMAL, "request_rate": 10.0 + random.uniform(-1, 1)}
    await _ingest(client, auth_headers, "checkout", m)
    series = (await client.get("/api/pulse/series/checkout", headers=auth_headers)).json()
    assert len(series["points"]) == 1
    assert abs(series["points"][0]["error_rate"] - m["error_rate"]) < 0.01


async def test_chaos_falls_back_to_live_platform(client, auth_headers, monkeypatch):
    import httpx as _hx

    from app.demo import services as _demo

    async def _unreachable(service, path):
        raise _hx.ConnectError("no demo services in this environment")

    monkeypatch.setattr(_demo, "_call_service", _unreachable)
    resp = await client.post("/api/pulse/chaos", headers=auth_headers, json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "astraea-api"
    assert body["fault"]
    assert body["auto_recover_s"] >= 1


async def test_detector_flags_drift_and_stops_the_mttd_clock(client, auth_headers, app, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "anomaly_cooldown_seconds", 60)
    tenant_id = _tid(auth_headers)
    # open fault (as the chaos API would record it)
    async with SessionLocal() as db:
        db.add(FaultInjection(tenant_id=tenant_id, service="checkout", kind="error_storm"))
        await db.commit()

    # learn a baseline: 40 calm points
    for _ in range(40):
        await _ingest(client, auth_headers, "checkout", {
            k: v + random.uniform(-0.4, 0.4) for k, v in NORMAL.items()})
    # then the storm hits: 6 anomalous points
    for _ in range(6):
        await _ingest(client, auth_headers, "checkout", {
            k: v + random.uniform(-2, 2) for k, v in FAULT_SHAPES["error_storm"].items()})

    anomalies = await detector.detect_once(tenant_id)
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a.service == "checkout"
    assert a.evidence["drifted"] == "error_rate"
    assert abs(a.evidence["drift_sigma"]) >= 3.0

    # benchmark clock stopped + cooldown prevents re-paging
    async with SessionLocal() as db:
        fault = (await db.execute(
            __import__("sqlalchemy").select(FaultInjection)
            .where(FaultInjection.tenant_id == tenant_id))).scalars().first()
        assert fault.detected_at is not None and fault.anomaly_id == a.id
    again = await detector.detect_once(tenant_id)
    assert again == []


async def test_healthy_services_stay_quiet(client, auth_headers):
    for _ in range(45):
        for svc in ("payments", "inventory"):
            await _ingest(client, auth_headers, svc, {
                k: v + random.uniform(-0.5, 0.5) for k, v in NORMAL.items()})
    assert await detector.detect_once(_tid(auth_headers)) == []


def _tid(auth_headers) -> str:
    from app.shared.security import decode_access_token

    return decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]


_SELF_SERIES = "astraea-api"


async def _seed_self_series(tenant_id: str, *, storm: bool) -> None:
    """40+ points of a flatline baseline followed by an obvious burst — pre-gate,
    the degenerate-baseline path in detect_once treated this as a real incident."""
    from app.pulse.models import MetricPoint

    async with SessionLocal() as db:
        for _ in range(34):
            db.add(MetricPoint(tenant_id=tenant_id, service=_SELF_SERIES, **NORMAL))
        for _ in range(6):
            db.add(MetricPoint(tenant_id=tenant_id, service=_SELF_SERIES,
                               **(FAULT_SHAPES["error_storm"] if storm else NORMAL)))
        await db.commit()


async def test_self_series_never_pages_without_open_chaos(app):
    """Audit HIGH-3: the platform watching itself must not spawn MEDIC runs for its
    own traffic bursts. astraea-api only pages when a chaos fault is open on it."""
    from sqlalchemy import select as _select

    tenant_id = "tenant-self-obs"
    await _seed_self_series(tenant_id, storm=True)

    assert await detector.detect_once(tenant_id) == []
    async with SessionLocal() as db:
        rows = (await db.execute(
            _select(Anomaly).where(Anomaly.tenant_id == tenant_id))).scalars().all()
    assert rows == []


async def test_self_series_pages_when_a_chaos_fault_is_open(app):
    """The gate opens only for a live fault on the self-series — the MTTD benchmark
    demo keeps working, and every persisted anomaly carries its run."""
    from sqlalchemy import select as _select

    tenant_id = "tenant-self-obs-fault"
    async with SessionLocal() as db:
        db.add(FaultInjection(tenant_id=tenant_id, service=_SELF_SERIES, kind="error_storm"))
        await db.commit()
    await _seed_self_series(tenant_id, storm=True)

    anomalies = await detector.detect_once(tenant_id)
    assert len(anomalies) == 1
    assert anomalies[0].service == _SELF_SERIES
    assert anomalies[0].run_id  # no runless anomalies (audit MEDIUM)
    async with SessionLocal() as db:
        rows = (await db.execute(
            _select(Anomaly).where(Anomaly.tenant_id == tenant_id))).scalars().all()
    assert len(rows) == 1 and rows[0].run_id == anomalies[0].run_id
