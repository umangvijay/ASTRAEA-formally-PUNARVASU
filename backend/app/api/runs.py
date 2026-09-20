"""Runs API: create, list, inspect, approve, resume — plus the live SSE event stream."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import engine
from app.core.engine import validate_workflow
from app.core.models import Run, RunEvent, Workflow
from app.loom import service as loom_svc
from app.shared.bus import sse_format, subscribe, unsubscribe
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/runs", tags=["runs"])

MAX_EVENTS_REPLAY = 500


def _run_out(run: Run) -> dict:
    return {
        "id": run.id,
        "goal": run.goal,
        "origin_module": run.origin_module,
        "status": run.status,
        "workflow": run.workflow,
        "result": run.result,
        "error": run.error,
        "created_at": str(run.created_at),
        "updated_at": str(run.updated_at),
    }


def _event_out(e: RunEvent) -> dict:
    return {"id": e.id, "type": e.type, "node": e.node, "payload": e.payload,
            "tokens_in": e.tokens_in, "tokens_out": e.tokens_out, "at": str(e.created_at)}


class RunIn(BaseModel):
    goal: str = Field(min_length=3, max_length=2000)
    workflow_id: str | None = None
    workflow: list[dict] | None = None
    share_outputs: bool = True


@router.post("", status_code=201)
async def create_run(payload: RunIn, x_module: str | None = Header(default=None),
                     user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    module = (x_module or "console").lower().strip()
    if module not in loom_svc.KNOWN_MODULES:
        raise HTTPException(status_code=422, detail=f"unknown module '{module}'")

    if payload.workflow_id:
        wf = await db.get(Workflow, payload.workflow_id)
        if wf is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        steps = wf.steps
    elif payload.workflow:
        steps = payload.workflow
    else:
        raise HTTPException(status_code=422, detail="provide workflow_id or workflow")

    try:
        steps = validate_workflow(steps)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    share = ["shield", "medic", "operator", "vaani", "forge"] if payload.share_outputs else []
    for step in steps:
        if step["type"] == "loom_write" and step.get("share_with") is None:
            step["share_with"] = share

    run = Run(tenant_id=user.tenant_id, goal=payload.goal, workflow=steps, origin_module=module)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    engine.spawn(run.id)  # live execution starts now; the response returns immediately
    return _run_out(run)


@router.get("")
async def list_runs(limit: int = 30, user=Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):
    rows = (
        (await db.execute(
            select(Run).where(Run.tenant_id == user.tenant_id)
            .order_by(Run.created_at.desc(), Run.id.desc()).limit(min(limit, 100))
        ))
        .scalars()
        .all()
    )
    return {"runs": [_run_out(r) for r in rows]}


@router.get("/workflows")
async def list_workflows(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Workflow).order_by(Workflow.name))).scalars().all()
    return {"workflows": [
        {"id": w.id, "name": w.name, "description": w.description,
         "needs_llm": w.needs_llm, "steps": w.steps}
        for w in rows
    ]}


@router.get("/{run_id}")
async def get_run(run_id: str, since: int = 0, user=Depends(get_current_user),
                  db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="run not found")
    events = (
        (await db.execute(
            select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.id > since)
            .order_by(RunEvent.id).limit(MAX_EVENTS_REPLAY)
        ))
        .scalars()
        .all()
    )
    return {"run": _run_out(run), "events": [_event_out(e) for e in events]}


@router.get("/{run_id}/stream")
async def stream_run(run_id: str, request: Request, since: int = 0,
                     user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="run not found")

    topic = f"run:{run_id}"
    # subscribe BEFORE the backlog query: an event committed between the
    # backlog SELECT and subscribe() used to fall through both paths and be
    # lost to this client. Duplicate delivery is prevented with a seen-id set.
    queue = subscribe(topic)
    backlog = (
        (await db.execute(
            select(RunEvent).where(RunEvent.run_id == run_id, RunEvent.id > since)
            .order_by(RunEvent.id).limit(MAX_EVENTS_REPLAY)
        ))
        .scalars()
        .all()
    )

    async def gen():
        try:
            seen = 0
            for e in backlog:
                seen = e.id
                yield sse_format(_json(_event_out(e)))
            yield sse_format('{"type": "caught_up"}')
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    # skip anything already replayed from the backlog
                    if isinstance(payload, dict) and payload.get("id") and payload["id"] <= seen:
                        continue
                    yield sse_format(payload)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe(topic, queue)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _json(obj) -> str:
    import json

    return json.dumps(obj, default=str)


class ApprovalIn(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=500)


@router.post("/{run_id}/approve")
async def approve_run(run_id: str, payload: ApprovalIn, user=Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="run not found")
    try:
        return await engine.approve(run_id, payload.approved, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/{run_id}/resume")
async def resume_run(run_id: str, user=Depends(get_current_user),
                     db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, run_id)
    if run is None or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status not in ("interrupted", "queued"):
        raise HTTPException(status_code=409, detail=f"cannot resume a {run.status} run")
    engine.spawn(run_id)
    return {"status": "resuming"}
