"""Enterprise-GA hardening tests: shared bus envelope contract, DB-backed login
throttling shared across "instances", durable artifact store round-trip and
fallback, and atomic run terminal-state commits (the soak-found window)."""

from __future__ import annotations

import asyncio
import json

import pytest

from app.config import settings
from app.db import SessionLocal
from app.shared import artifacts, bus


# ── bus: envelope compaction + single-process fallback ─────────────────────
def test_bus_compact_event_keeps_identity_fields():
    event = {"kind": "llm_delta", "run_id": "r1", "tenant_id": "t1",
             "ts": "2026-09-19T00:00:00", "id": 42, "payload": {"text": "x" * 9000}}
    compact = bus.compact_event(event)
    assert compact["truncated"] is True
    assert compact["run_id"] == "r1" and compact["kind"] == "llm_delta"
    assert len(json.dumps(compact)) < 200


async def test_bus_publish_delivers_locally():
    q = bus.subscribe("run:test-bus")
    try:
        await bus.publish("run:test-bus", {"kind": "step_started", "run_id": "r1"})
        payload = q.get_nowait()
        assert json.loads(payload)["kind"] == "step_started"
    finally:
        bus.unsubscribe("run:test-bus", q)


def test_bus_dispatch_remote_skips_self_and_foreign_ok():
    q = bus.subscribe("run:remote-test")
    try:
        # our own instance id → ignored (already dispatched locally)
        bus._dispatch_remote(json.dumps(
            {"o": bus._INSTANCE_ID, "t": "run:remote-test", "e": '{"kind":"mine"}'}))
        with pytest.raises(asyncio.QueueEmpty):
            q.get_nowait()
        # a remote instance → dispatched into our local queues
        bus._dispatch_remote(json.dumps(
            {"o": "other-instance", "t": "run:remote-test", "e": '{"kind":"theirs"}'}))
        assert json.loads(q.get_nowait())["kind"] == "theirs"
    finally:
        bus.unsubscribe("run:remote-test", q)


async def test_bus_start_shared_is_noop_on_sqlite():
    assert bus.start_shared() is False  # tests run on sqlite; no listener starts
    await bus.stop_shared()  # idempotent stop is safe even when never started


# ── auth: throttling lives in the DB, shared across instances ──────────────
async def test_login_lockout_is_db_backed(client):
    """5 failures → 423 with retry hint; the counter is in login_attempts, so a
    second 'instance' (a fresh process reading the same DB) sees the same lock."""
    from sqlalchemy import func, select

    from app.core.models import LoginAttempt

    payload = {"email": "ga-lock@example.com", "password": "wrong-password-1"}
    statuses = []
    for _ in range(6):
        resp = await client.post("/api/auth/login", json=payload)
        statuses.append(resp.status_code)
    assert statuses[:5] == [401] * 5, "first 5 failures are plain auth failures"
    assert statuses[5] == 423, "6th attempt hits the lockout"

    async with SessionLocal() as db:
        count = (await db.execute(
            select(func.count()).select_from(LoginAttempt).where(
                LoginAttempt.email == payload["email"])
        )).scalar_one()
    assert count >= 5, "the lockout state lives in the DB, not process memory"


async def test_successful_login_clears_failure_window(client):
    email = "ga-recover@example.com"
    await client.post("/api/auth/register", json={
        "email": email, "password": "right-password-1", "full_name": "Re Cover"})
    for _ in range(4):  # below threshold
        await client.post("/api/auth/login", json={"email": email, "password": "nope-12345"})
    ok = await client.post("/api/auth/login", json={"email": email, "password": "right-password-1"})
    assert ok.status_code == 200
    # failures were cleared by the success: 4 more wrong tries still not locked
    for _ in range(4):
        await client.post("/api/auth/login", json={"email": email, "password": "nope-12345"})
    still_ok_shape = await client.post("/api/auth/login", json={"email": email, "password": "nope-12345"})
    assert still_ok_shape.status_code == 401, "success reset the lockout window"


async def test_attempt_cleanup_prunes_expired_rows(client):
    import datetime as dt

    from sqlalchemy import delete

    from app.api.auth import _cleanup_old_attempts
    from app.core.models import LoginAttempt

    async with SessionLocal() as db:
        await db.execute(delete(LoginAttempt))  # isolate
        db.add_all([
            LoginAttempt(ip="1.1.1.1", email="old@test.local", ok=False,
                         at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)),
            LoginAttempt(ip="1.1.1.1", email="new@test.local", ok=False),
        ])
        await db.commit()
        removed = await _cleanup_old_attempts(db)
        assert removed == 1


# ── artifacts: local backend round-trip (GCS path needs a bucket) ──────────
async def test_artifact_write_read_roundtrip_local():
    ref = artifacts.write_text("medic/test-run.patch", "+ fix\n")
    assert artifacts.backend_name() == "local"
    assert ref.endswith("medic/test-run.patch")
    assert artifacts.read_text(ref) == "+ fix\n"


async def test_artifact_read_missing_returns_none():
    assert artifacts.read_text("does/not/exist.json") is None


def test_artifact_gcs_degrades_to_local_when_client_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "artifact_bucket", "some-bucket", raising=False)
    monkeypatch.setattr("app.shared.artifacts._gcs_client", lambda: None)
    ref = artifacts.write_text("forge/champion.json", "{}")
    assert ref.startswith("/")  # local fallback path, still a real reference


# ── engine: terminal state + terminal event commit atomically ──────────────
async def test_completed_run_always_has_terminal_event(app, auth_headers, client):
    """Soak found a window: status='completed' committed before the
    run_completed event. Readers must never see one without the other."""
    from sqlalchemy import select

    from app.core.models import Run, RunEvent

    resp = await client.post("/api/runs", headers=auth_headers, json={
        "goal": "atomic terminal commit probe",
        "workflow": [{"name": "note", "type": "loom_write",
                      "title": "probe", "content": "x"}]})
    assert resp.status_code == 201
    run_id = resp.json()["id"]
    for _ in range(100):  # poll hard — the window is exactly what we hunt
        detail = (await client.get(f"/api/runs/{run_id}", headers=auth_headers)).json()
        status = detail["run"]["status"]
        has_terminal = any(e["type"] == "run_completed" for e in detail["events"])
        if status == "completed":
            assert has_terminal, "completed run visible without its terminal event"
            break
        assert not has_terminal or status in ("running", "completed")
        await asyncio.sleep(0.05)
    else:
        pytest.fail("run never completed")

    async with SessionLocal() as db:
        events = (await db.execute(
            select(RunEvent.type).where(RunEvent.run_id == run_id))).scalars().all()
        run = await db.get(Run, run_id)
    assert run.status == "completed" and "run_completed" in events
