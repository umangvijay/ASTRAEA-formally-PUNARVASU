"""Core runtime gate: approval gates, crash recovery with replay, graceful failures, LOOM artifacts."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.config import settings
from app.core import engine
from app.core.models import Run, RunEvent
from app.db import SessionLocal
from app.shared.security import decode_access_token


def _tid(auth_headers) -> str:
    return decode_access_token(auth_headers["Authorization"].removeprefix("Bearer "))["tid"]
from app.loom.models import LoomItem


async def _make_run(tenant_id: str, goal: str, steps: list[dict]) -> str:
    async with SessionLocal() as db:
        run = Run(tenant_id=tenant_id, goal=goal, workflow=engine.validate_workflow(steps),
                  origin_module="console")
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


APPROVAL_WORKFLOW = [
    {"name": "prepare", "type": "tool", "tool": "shell", "args": {"command": "echo prepared-on-host"}},
    {"name": "gate", "type": "approval", "prompt": "Apply the change?"},
    {"name": "finish", "type": "tool", "tool": "shell", "args": {"command": "echo finished"}},
    {"name": "remember", "type": "loom_write", "title": "Approved change",
     "summary": "human approved", "content": "{prepare} / {finish}", "kind": "artifact"},
]


async def test_approval_gate_parks_then_completes(auth_headers):
    tenant_id = _tid(auth_headers)
    run_id = await _make_run(tenant_id, "apply the approved change", APPROVAL_WORKFLOW)

    await engine.execute(run_id)
    run = await _run(run_id)
    assert run.status == "awaiting_approval"
    types = [e.type for e in await _events(run_id)]
    assert "approval_required" in types
    assert "run_completed" not in types

    result = await engine.approve(run_id, True, note="ship it")
    assert result["status"] == "approved"
    run = await _run(run_id)
    assert run.status == "completed"
    assert "prepared-on-host" in run.result["outputs"]["prepare"]

    # the loom_write step produced a provenance-stamped item tied to this run
    async with SessionLocal() as db:
        item = (await db.execute(select(LoomItem).where(LoomItem.origin_run_id == run_id))).scalar_one()
        assert item.origin_module == "console"
        assert "prepared-on-host" in item.payload["content"]


async def test_rejection_fails_run_at_gate(auth_headers):
    tenant_id = _tid(auth_headers)
    run_id = await _make_run(tenant_id, "apply the change", APPROVAL_WORKFLOW)
    await engine.execute(run_id)
    await engine.approve(run_id, False, note="not today")
    run = await _run(run_id)
    assert run.status == "failed"
    assert "rejected at approval gate 'gate'" in run.error


async def test_crash_recovery_resumes_without_rework(auth_headers):
    tenant_id = _tid(auth_headers)
    steps = [
        {"name": "s1", "type": "tool", "tool": "shell", "args": {"command": "echo one"}},
        {"name": "s2", "type": "tool", "tool": "shell", "args": {"command": "echo two"}},
        {"name": "s3", "type": "tool", "tool": "shell", "args": {"command": "echo three"}},
    ]
    run_id = await _make_run(tenant_id, "three steps", steps)

    # ── simulate a healthy partial run, then a violent process death ──
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        run.status = "running"
        await db.commit()
        event = RunEvent(run_id=run_id, type="step_completed", node="s1",
                         payload={"content": "one", "ok": True, "tool": "shell"})
        db.add(event)
        await db.commit()

    # ── new process: startup sweep marks it interrupted ──
    assert await engine.recover_orphans() >= 1
    assert (await _run(run_id)).status == "interrupted"

    # ── resume: s1 must NOT re-run; s2/s3 run once each ──
    await engine.execute(run_id)
    run = await _run(run_id)
    assert run.status == "completed"
    events = await _events(run_id)
    starts = [e.node for e in events if e.type == "step_started"]
    assert starts.count("s1") == 0, "completed step was re-executed after crash"
    assert starts.count("s2") == 1 and starts.count("s3") == 1
    assert any(e.type == "run_resumed" for e in events)
    assert run.result["outputs"]["s3"] == "three"


async def test_unknown_tool_fails_run_gracefully(auth_headers):
    tenant_id = _tid(auth_headers)
    run_id = await _make_run(tenant_id, "use a bogus tool", [
        {"name": "boom", "type": "tool", "tool": "definitely_not_a_tool", "args": {}},
    ])
    await engine.execute(run_id)
    run = await _run(run_id)
    assert run.status == "failed"
    assert "unknown tool" in run.error
    assert any(e.type == "step_failed" for e in await _events(run_id))


async def test_llm_step_without_providers_fails_with_clear_error(auth_headers, monkeypatch):
    import app.model_forge.serving as mf_serving

    monkeypatch.setattr(mf_serving, "available", lambda: False)
    monkeypatch.setattr(mf_serving, "base_available", lambda: False)
    monkeypatch.setattr(settings, "gemini_api_key", "")
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(settings, "ollama_base_url", "")
    tenant_id = _tid(auth_headers)
    run_id = await _make_run(tenant_id, "research something", [
        {"name": "research", "type": "llm", "prompt": "research {goal}"},
    ])
    await engine.execute(run_id)
    run = await _run(run_id)
    assert run.status == "failed"
    assert "provider" in run.error.lower()


async def test_shell_rlimit_timeout_is_recorded(auth_headers):
    tenant_id = _tid(auth_headers)
    run_id = await _make_run(tenant_id, "sleep too long", [
        {"name": "slow", "type": "tool", "tool": "shell",
         "args": {"command": "sleep 30", "timeout": 1}},
        {"name": "after", "type": "tool", "tool": "shell", "args": {"command": "echo survived"}},
    ])
    await engine.execute(run_id)
    run = await _run(run_id)
    assert run.status == "completed"  # timeout is a recorded tool result, not a crash
    assert "timeout" in run.result["outputs"]["slow"]
    assert run.result["outputs"]["after"] == "survived"
