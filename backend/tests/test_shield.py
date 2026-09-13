"""SHIELD gate: 5/5 lab attacks detected with correct ATT&CK mapping, FP drill <10%,
containment honored by the lab, postmortems into LOOM (visible to MEDIC)."""

from __future__ import annotations

import asyncio
import json
import random

import pytest
from sqlalchemy import select

from app.core import engine
from app.core.models import Run
from app.db import SessionLocal
from app.loom.models import LoomItem
from app.shield import detector, lab
from app.shield.detector import evaluate_rules
from app.shield.models import SecurityEvent, ShieldIncident, ShieldRule
from app.shared.security import decode_access_token


def _tid(auth_headers) -> str:
    return decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]


@pytest.fixture(autouse=True)
def _clear_lab_state():
    lab.BLOCKED_IPS.clear()
    lab.LOCKED_USERS.clear()
    yield
    lab.BLOCKED_IPS.clear()
    lab.LOCKED_USERS.clear()


async def _ingest(tenant_id: str, events: list[dict]) -> None:
    async with SessionLocal() as db:
        for e in events:
            db.add(SecurityEvent(
                tenant_id=tenant_id, host=e["host"], event=e["event"], user=e.get("user"),
                src_ip=e.get("src_ip"), dst_ip=e.get("dst_ip"), dst_port=e.get("dst_port"),
                external=bool(e.get("external")), process=e.get("process"),
                bytes_out=int(e.get("bytes_out", 0)),
            ))
        await db.commit()


async def _wait_for(predicate, timeout=8.0, interval=0.2):
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if await predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def _run_in_status(run_id: str, expected: str) -> bool:
    return (await _status(run_id)) == expected


async def _status(run_id: str) -> str | None:
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        return run.status if run else None


def test_rule_evaluator_unit():
    rules = [{"name": "brute-force-login-failures", "event_types": ["login_failure"],
              "threshold": {"evaluator": "count_per_src", "count": 5, "window_s": 60},
              "technique_id": "T1110", "severity": "high", "enabled": True}]
    events = [{"host": "web-1", "event": "login_failure", "user": "admin",
               "src_ip": "1.2.3.4", "ts": 1000 + i} for i in range(5)]
    assert len(evaluate_rules(events, rules)) == 1
    events_short = events[:4]
    assert evaluate_rules(events_short, rules) == []  # below threshold → no hit


def test_sentinel_block_maps_to_execution():
    rules = [{"name": "suspicious-process-execution", "event_types": ["process_exec"],
              "threshold": {"evaluator": "process_pattern",
                            "patterns": ["base64 -d", "/tmp/", "curl http://", "sentinel.block"]},
              "technique_id": "T1059", "severity": "high", "enabled": True}]
    events = [{"host": "astraea-api", "event": "process_exec",
               "process": "sentinel.block:prompt-injection", "src_ip": "9.9.9.9", "ts": 1}]
    hits = evaluate_rules(events, rules)
    assert len(hits) == 1
    assert hits[0]["technique_id"] == "T1059"


EXPECTED = {
    "brute_force": {"T1110", "T1078"},
    "lateral_movement": {"T1046"},
    "malicious_process": {"T1059"},
    "data_exfil": {"T1041"},
    "c2_beacon": {"T1071.001"},
}


async def test_five_scenarios_detected_mapped_contained(app, auth_headers):
    tenant_id = _tid(auth_headers)
    target = None

    for scenario, expected in EXPECTED.items():
        events = lab.scenario_events(scenario, target)
        await _ingest(tenant_id, events)
        incidents = await detector.detect_once(tenant_id)
        assert incidents, f"{scenario}: no incident detected"
        incident = next(
            i for i in incidents
            if i.host == (events[0]["host"] if scenario not in ("lateral_movement",) else "web-1")
        )
        mapped = {t["id"] for t in incident.techniques}
        assert expected & mapped, f"{scenario}: expected {expected}, got {mapped}"
        assert incident.run_id, f"{scenario}: run not spawned"

        run_id = incident.run_id
        assert await _wait_for(lambda: _run_in_status(run_id, "awaiting_approval"))

        await engine.approve(run_id, True, note="contain it")
        assert await _wait_for(lambda: _run_in_status(run_id, "completed"))

        async with SessionLocal() as db:
            inc = await db.get(ShieldIncident, incident.id)
            assert inc.status == "contained"
            assert inc.containment and inc.containment["applied"]
            # postmortem in LOOM, stamped FROM SHIELD
            item = (await db.execute(
                select(LoomItem).where(LoomItem.origin_run_id == run_id))).scalar_one()
            assert item.origin_module == "shield"
            assert item.kind == "incident"

    # containment had real effects on the lab
    assert lab.ATTACKER_IP in lab.BLOCKED_IPS
    # MEDIC sees the SHIELD postmortems through LOOM
    from app.loom import service as loom

    async with SessionLocal() as db:
        medic_ctx = await loom.context_for(db, tenant_id, "medic", limit=40)
    incidents_in_ctx = [i for i in medic_ctx if i["kind"] == "incident"]
    assert incidents_in_ctx and all("FROM SHIELD" == i["provenance"]["from"] for i in incidents_in_ctx)


async def test_benign_drill_false_positives_under_10_percent(app, auth_headers):
    tenant_id = _tid(auth_headers)
    # benign baseline first (healthy services + rules seeded) — the drill must stay quiet
    from app.shield.models import ShieldRule

    async with SessionLocal() as db:
        rules = (
            (await db.execute(
                select(ShieldRule).where(ShieldRule.enabled.is_(True))
            )).scalars().all()
        )
        rule_dicts = [{"name": r.name, "event_types": r.event_types, "threshold": r.threshold,
                       "technique_id": r.technique_id, "severity": r.severity, "enabled": r.enabled}
                      for r in rules]
        assert rule_dicts, "shield rules not seeded"

    random.seed(42)
    flagged = 0
    windows = 2880  # 24h of 30s windows
    base = 1_700_000_000
    for w in range(windows):
        events = lab.benign_window(now=base + w * 30)
        if evaluate_rules(events, rule_dicts):
            flagged += 1
    fp_rate = flagged / windows
    assert fp_rate < 0.10, f"false positive rate {fp_rate:.1%} breaches the 10% gate"
