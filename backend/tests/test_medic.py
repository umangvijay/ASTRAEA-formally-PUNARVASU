"""MEDIC gate: 10 random faults → detected, correct service in top-3 ≥7/10, patch applied.

Runs the whole chain WITHOUT demo services or LLM keys — proving the evidence-computed
fallback path (statistical ranking, never canned) end-to-end through the durable engine.
"""

from __future__ import annotations

import asyncio
import json
import random

import pytest
from sqlalchemy import select

from app.core import engine
from app.core.models import Run
from app.db import SessionLocal
from app.pulse import detector
from app.pulse.models import Anomaly, FaultInjection
from app.shared.security import decode_access_token

NORMAL = {"request_rate": 10.0, "error_rate": 0.5, "p95_latency": 80.0, "cpu": 25.0}
FAULT_SHAPES = {
    "error_storm": {"request_rate": 10.0, "error_rate": 40.0, "p95_latency": 90.0, "cpu": 30.0},
    "latency_spike": {"request_rate": 9.0, "error_rate": 1.0, "p95_latency": 900.0, "cpu": 30.0},
    "memory_leak": {"request_rate": 5.0, "error_rate": 2.0, "p95_latency": 120.0, "cpu": 90.0},
    "dependency_failure": {"request_rate": 8.0, "error_rate": 25.0, "p95_latency": 400.0, "cpu": 35.0},
    "config_drift": {"request_rate": 8.0, "error_rate": 8.0, "p95_latency": 500.0, "cpu": 30.0},
}
SERVICES = ["checkout", "payments", "inventory"]
KINDS = list(FAULT_SHAPES)


def _tid(auth_headers) -> str:
    return decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]


async def _status(run_id: str) -> str | None:
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        return run.status if run else None


async def _run_in_status(run_id: str, expected: str) -> bool:
    return (await _status(run_id)) == expected


async def _wait_for(predicate, timeout=8.0, interval=0.2):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def test_ten_random_faults_gate(client, auth_headers):
    tenant_id = _tid(auth_headers)
    random.seed()  # genuinely random — the gate must hold for any draw
    hits, detected = 0, 0

    for round_no in range(10):
        service = random.choice(SERVICES)
        kind = random.choice(KINDS)

        # ── chaos: record the fault (the API does this against live services) ──
        async with SessionLocal() as db:
            db.add(FaultInjection(tenant_id=tenant_id, service=service, kind=kind))
            await db.commit()

        # ── baseline then fault telemetry, as the demo services would emit ──
        for _ in range(40):
            await _feed(client, auth_headers, service, NORMAL)
        for _ in range(6):
            await _feed(client, auth_headers, service, FAULT_SHAPES[kind])

        # ── detector tick: the MTTD clock stops here ──
        anomalies = await detector.detect_once(tenant_id)
        assert anomalies, f"round {round_no}: fault on {service}/{kind} was NOT detected"
        assert anomalies[0].service == service

        # ── MEDIC run spawned through the core engine; wait for the human gate ──
        async with SessionLocal() as db:
            anomaly = await db.get(Anomaly, anomalies[0].id)
            run_id = anomaly.run_id
        assert run_id, "medic run was not spawned"
        assert await _wait_for(
            lambda: _run_in_status(run_id, "awaiting_approval")
        ), f"round {round_no}: run never reached the approval gate"

        # ── the human approves; fix executes ──
        await engine.approve(run_id, True, note="gate ok")
        assert await _wait_for(lambda: _run_in_status(run_id, "completed"))

        # ── score: correct service inside top-3 hypotheses ──
        async with SessionLocal() as db:
            run = await db.get(Run, run_id)
            investigation = json.loads(run.result["outputs"]["investigate"])
            top3 = [h["service"] for h in investigation["hypotheses"][:3]]
        detected += 1
        if service in top3:
            hits += 1

        # ── auto-recovery: the service heals, telemetry returns to normal ──
        for _ in range(30):
            await _feed(client, auth_headers, service, NORMAL)

    assert detected == 10
    accuracy = hits / detected
    assert accuracy >= 0.7, f"top-3 accuracy {accuracy:.0%} below the 70% gate"

    # ── benchmark endpoint reports the same numbers ──
    bench = (await client.get("/api/pulse/benchmark", headers=auth_headers)).json()
    assert bench["faults_injected"] == 10
    assert bench["detected"] == 10
    assert bench["mttd_seconds_avg"] is not None


async def _feed(client, auth_headers, service, shape):
    noisy = {k: v + random.uniform(-0.4, 0.4) for k, v in shape.items()}
    resp = await client.post(
        "/api/pulse/ingest", headers=auth_headers,
        json={"type": "metrics", "service": service, "metrics": noisy},
    )
    assert resp.status_code == 200


def _run_status(run_id: str) -> str | None:
    async def inner():
        async with SessionLocal() as db:
            run = await db.get(Run, run_id)
            return run.status if run else None
    return inner()
