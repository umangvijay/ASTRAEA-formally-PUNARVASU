"""The durable run engine — the reason the platform is called Astraea ("return of the light").

Properties:
- Event-sourced: a run IS its `run_events` rows. Status is always reconstructable.
- Crash-proof: a killed process leaves `running` rows; startup marks them `interrupted`
  and resume continues exactly after the last completed step.
- Human gates: `approval` steps park the run as `awaiting_approval` — across restarts,
  across days — until /approve or /resume decides.
- Live: every event is committed AND published to the in-memory bus for SSE clients.

Workflows are plain JSON stored on the run — data, not code (anti-hardcoding §4.1).
Step types: llm | tool | loom_write | approval.
"""

from __future__ import annotations

import asyncio
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Run, RunEvent
from app.core.tools import run_tool
from app.db import SessionLocal
from app.loom import service as loom
from app.sentinel.llm import complete
from app.shared.bus import publish

_RUNNING: set[str] = set()
_TASKS: set[asyncio.Task] = set()  # strong refs — fire-and-forget tasks must not be GC'd mid-run

VALID_STEP_TYPES = {"llm", "tool", "loom_write", "approval"}


def validate_workflow(steps: list[dict]) -> list[dict]:
    if not steps or not isinstance(steps, list):
        raise ValueError("workflow must be a non-empty list of steps")
    seen = set()
    for idx, step in enumerate(steps):
        if not isinstance(step, dict) or step.get("type") not in VALID_STEP_TYPES:
            raise ValueError(f"step {idx}: unknown or missing type ({VALID_STEP_TYPES})")
        name = step.get("name") or f"step_{idx}"
        if name in seen:
            raise ValueError(f"duplicate step name '{name}'")
        seen.add(name)
        if step["type"] == "tool" and not step.get("tool"):
            raise ValueError(f"step '{name}': tool steps need a 'tool'")
    return [{**step, "name": step.get("name") or f"step_{idx}"} for idx, step in enumerate(steps)]


def _render(value, mapping: dict[str, str]):
    if isinstance(value, dict):
        return {k: _render(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_render(v, mapping) for v in value]
    if isinstance(value, str):
        # allow hyphens in step names, e.g. {build-image} (bug #11)
        return re.sub(r"\{([\w-]+)\}", lambda m: mapping.get(m.group(1), m.group(0)), value)
    return value


def _render_step(step: dict, ctx: dict[str, dict], run: Run) -> dict:
    mapping: dict[str, str] = {"goal": run.goal}
    for node, out in ctx.items():
        mapping[node] = str(out.get("content", "")) if isinstance(out, dict) else str(out)
    completed = [n for n in ctx if isinstance(ctx.get(n), dict) and "content" in ctx[n]]
    mapping["last"] = str(ctx[completed[-1]].get("content", "")) if completed else ""
    return {k: _render(v, mapping) for k, v in step.items()}


async def _emit(db: AsyncSession, run: Run, event_type: str, node: str | None = None,
                payload: dict | None = None, tokens_in: int = 0, tokens_out: int = 0) -> None:
    event = RunEvent(run_id=run.id, type=event_type, node=node, payload=payload,
                     tokens_in=tokens_in, tokens_out=tokens_out)
    db.add(event)
    await db.commit()
    await db.refresh(event)
    await publish(f"run:{run.id}", {
        "id": event.id, "type": event_type, "node": node, "payload": payload,
        "run_status": run.status, "at": str(event.created_at),
    })


async def _load_ctx(db: AsyncSession, run_id: str) -> tuple[dict[str, dict], set[str]]:
    events = (
        (await db.execute(
            select(RunEvent).where(RunEvent.run_id == run_id).order_by(RunEvent.id)
        ))
        .scalars()
        .all()
    )
    ctx: dict[str, dict] = {}
    granted: set[str] = set()
    for e in events:
        if e.type == "step_completed" and e.node:
            ctx[e.node] = e.payload or {}
        if e.type == "approval_granted" and e.node:
            granted.add(e.node)
    return ctx, granted


async def _run_step(db: AsyncSession, run: Run, step: dict, ctx: dict[str, dict]) -> dict:
    step = _render_step(step, ctx, run)
    kind = step["type"]

    if kind == "llm":
        prompt = step.get("prompt") or run.goal
        messages = [
            {"role": "system",
             "content": step.get("system", "You are a precise operations agent. Do exactly what is asked, nothing more.")},
            {"role": "user", "content": str(prompt)},
        ]

        node = step.get("name") or "llm"

        async def on_delta(delta: str) -> None:
            # real-time tokens to every subscribed console — bus-only, not persisted
            await publish(f"run:{run.id}", {
                "type": "llm_delta", "node": node, "payload": {"text": delta},
            })

        out = await complete(db, run.tenant_id, messages, model=step.get("model"),
                             origin_module=run.origin_module, run_id=run.id,
                             on_delta=on_delta)
        return {"content": out["content"], "provider": out["provider"], "model": out["model"],
                "usage": out["usage"], "guardrails": out["guardrails"]}

    if kind == "tool":
        tool = step["tool"]
        args = step.get("args") or {}
        if not isinstance(args, dict):
            raise ValueError("tool args must be an object")
        result = await run_tool(db, run, tool, args)
        return {"content": str(result.get("output", "")), "ok": result.get("ok", True),
                "tool": tool}

    if kind == "loom_write":
        item = await loom.write_item(
            db, run.tenant_id,
            origin_module=run.origin_module,
            origin_run_id=run.id,
            kind=str(step.get("kind", "artifact")),
            title=str(step.get("title", f"Output of {run.goal[:60]}")),
            summary=str(step.get("summary", "")),
            payload={"content": str(step.get("content", "{last}"))},
            share_with=list(step.get("share_with", [])),
        )
        return {"content": f"loom item {item.id} created ({item.kind})", "item_id": item.id}

    raise ValueError(f"step type '{kind}' is not executable")


async def _execute(run_id: str) -> None:
    if run_id in _RUNNING:
        return
    _RUNNING.add(run_id)
    try:
        async with SessionLocal() as db:
            run = await db.get(Run, run_id)
            if run is None or run.status in ("completed", "failed"):
                return
            ctx, granted = await _load_ctx(db, run_id)
            resumed = bool(ctx) or bool(granted)

            run.status = "running"
            await db.commit()
            if not resumed:
                await _emit(db, run, "run_started",
                            payload={"goal": run.goal, "origin_module": run.origin_module,
                                     "steps": [s.get("name") for s in run.workflow]})
            else:
                await _emit(db, run, "run_resumed", payload={"completed_steps": sorted(ctx.keys())})

            for step in run.workflow:
                name = step["name"]
                if name in ctx:
                    continue
                if step["type"] == "approval":
                    if name in granted:
                        continue
                    run.status = "awaiting_approval"
                    await db.commit()
                    await _emit(db, run, "approval_required", node=name,
                                payload={"prompt": str(step.get("prompt", "Approve this step?"))})
                    return  # parked — durable across restarts

                await _emit(db, run, "step_started", node=name, payload={"type": step["type"]})
                try:
                    out = await _run_step(db, run, step, ctx)
                except Exception as exc:  # noqa: BLE001 — engine must record, never crash silent
                    run.status = "failed"
                    run.error = str(exc)[:800]
                    await db.commit()
                    await _emit(db, run, "step_failed", node=name, payload={"error": str(exc)[:500]})
                    await _emit(db, run, "run_failed", payload={"error": str(exc)[:500]})
                    return
                ctx[name] = out
                usage = out.get("usage", {}) if isinstance(out, dict) else {}
                await _emit(db, run, "step_completed", node=name, payload=out,
                            tokens_in=int(usage.get("tokens_in", 0)),
                            tokens_out=int(usage.get("tokens_out", 0)))

            run.status = "completed"
            run.result = {
                "outputs": {n: (o.get("content") if isinstance(o, dict) else o) for n, o in ctx.items()},
            }
            await db.commit()
            await _emit(db, run, "run_completed", payload={"steps": sorted(ctx.keys())})
    finally:
        _RUNNING.discard(run_id)


def spawn(run_id: str) -> None:
    """Fire-and-forget execution (API path).

    Runs in-process for immediate latency, but under a durable lease + heartbeat
    (via `worker.supervise`) so a crash releases the run for another worker to
    resume — no longer a bare `asyncio.create_task` with no recovery story."""
    from app.core.worker import supervise  # local import breaks the engine<->worker cycle

    task = asyncio.get_running_loop().create_task(supervise(run_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


async def wait_all(timeout: float = 15.0) -> None:
    """Wait for in-flight run tasks (teardown/drain helper)."""
    import time as _t

    deadline = _t.time() + timeout
    while _RUNNING and _t.time() < deadline:
        await asyncio.sleep(0.05)


async def execute(run_id: str) -> None:
    """Awaited execution (tests, recovery sweeps)."""
    await _execute(run_id)


async def approve(run_id: str, approved: bool, note: str | None = None) -> dict:
    if not approved:
        return await reject(run_id, note)
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        if run is None:
            raise ValueError("run not found")
        if run.status != "awaiting_approval":
            raise ValueError(f"run is not awaiting approval (status={run.status})")
        _, granted = await _load_ctx(db, run_id)
        pending = next(
            (s["name"] for s in run.workflow
             if s["type"] == "approval" and s["name"] not in granted),
            None,
        )
        if pending is None:
            raise ValueError("no pending approval step found")
        await _emit(db, run, "approval_granted", node=pending, payload={"note": note or ""})
    await _execute(run_id)
    return {"status": "approved", "node": pending}


async def reject(run_id: str, note: str | None = None) -> dict:
    async with SessionLocal() as db:
        run = await db.get(Run, run_id)
        if run is None or run.status != "awaiting_approval":
            raise ValueError("run is not awaiting approval")
        _, granted = await _load_ctx(db, run_id)
        pending = next(
            (s["name"] for s in run.workflow
             if s["type"] == "approval" and s["name"] not in granted),
            None,
        )
        run.status = "failed"
        run.error = f"rejected at approval gate '{pending}': {note or 'no reason given'}"
        await db.commit()
        await _emit(db, run, "approval_denied", node=pending, payload={"note": note or ""})
        await _emit(db, run, "run_failed", payload={"error": run.error})
        return {"status": "rejected", "node": pending}


async def recover_orphans() -> int:
    """Startup sweep: in-process executors no longer exist → 'running' becomes 'interrupted'.
    'awaiting_approval' is deliberately LEFT ALONE — gates persist across restarts."""
    count = 0
    async with SessionLocal() as db:
        runs = (
            (await db.execute(select(Run).where(Run.status == "running"))).scalars().all()
        )
        for run in runs:
            run.status = "interrupted"
            await db.commit()
            await _emit(db, run, "run_interrupted",
                        payload={"reason": "process died mid-run — resume to continue"})
            count += 1
    return count
