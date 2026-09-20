"""OPERATOR API: run a single task through the engine, read the benchmark scoreboard."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import engine
from app.core.models import Run
from app.operator import web
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/operator", tags=["operator"])


class TaskIn(BaseModel):
    goal: str = Field(min_length=3, max_length=300)
    url: str = Field(min_length=4, max_length=400)
    success_url_contains: str | None = Field(default=None, max_length=200)
    success_text_contains: str | None = Field(default=None, max_length=200)

    @field_validator("url")
    @classmethod
    def _navigable_url(cls, v: str) -> str:
        # Fail at the API edge, not minutes later inside Playwright — literal
        # private IPs are rejected here by name; the full DNS-resolution guard
        # runs in the runner before any navigation.
        from app.operator.web import assert_public_url

        assert_public_url(v.strip())
        return v.strip()


@router.post("/task", status_code=201)
async def run_task(payload: TaskIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """One browser task as a durable run: execute → verify → (success) remember trajectory.
    An explicit success predicate (URL or text) makes success honest; without one the
    runner reports exactly what it did and why it stopped."""
    args: dict = {"goal": payload.goal, "url": payload.url}
    if payload.success_url_contains:
        args["success_kind"] = "url_contains"
        args["success_value"] = payload.success_url_contains
    elif payload.success_text_contains:
        args["success_kind"] = "content_contains"
        args["success_value"] = payload.success_text_contains
    steps = engine.validate_workflow([
        {"name": "operate", "type": "tool", "tool": "operator.run_task", "args": args},
    ])
    run = Run(tenant_id=user.tenant_id, goal=payload.goal, workflow=steps, origin_module="operator")
    db.add(run)
    await db.commit()
    await db.refresh(run)
    engine.spawn(run.id)
    return {"run_id": run.id, "goal": payload.goal, "status": "queued"}


class ResearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=400)
    max_results: int = Field(default=4, ge=1, le=8)
    synthesize: bool = True


@router.post("/research")
async def research(payload: ResearchIn, user=Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    """Live search + fetch. Each page is the real HTML from that URL — not a template."""
    pack = await web.research(payload.query, max_results=payload.max_results)
    synthesis = None
    if payload.synthesize:
        try:
            from app.sentinel.llm import BlockedByGuardrail, complete
            from app.sentinel.pipeline import scan_text
            from app.sentinel.upstream import ProviderUnavailable

            qscan = await scan_text(db, user.tenant_id, payload.query, "input")
            if qscan.action == "block":
                raise BlockedByGuardrail(list(getattr(qscan, "hits", []) or []))

            excerpts = [
                f"SOURCE {i+1}: {p.get('url')}\nTITLE: {p.get('title')}\n"
                f"{(p.get('text') or p.get('snippet') or '')[:900]}"
                for i, p in enumerate(pack.get("pages") or [])
            ]
            out = await complete(
                db, user.tenant_id,
                [{"role": "user", "content":
                  f"Summarize what these live excerpts say about the question, in 2-3 short sentences. "
f"Stick to facts found in the excerpts and mention which site said what.\n"
                  f"Question: {payload.query}\n\n" + "\n\n".join(excerpts)}],
                origin_module="operator",
                # Retrieved HTML is not a user jailbreak — Layer 1 still redacts PII.
                ml=False,
            )
            synthesis = {"text": out["content"], "provider": out["provider"], "model": out["model"]}
        except ProviderUnavailable:
            synthesis = {"text": None, "degraded": "no_general_llm"}
        except BlockedByGuardrail:
            synthesis = {"text": None, "degraded": "blocked"}
        except Exception:  # noqa: BLE001 — excerpts still returned
            synthesis = {"text": None, "degraded": "synthesis_failed"}

    from app.loom import service as loom

    await loom.write_item(
        db, user.tenant_id, origin_module="operator", origin_run_id=None,
        kind="research", title=f"Web research: {payload.query[:80]}",
        summary=((synthesis or {}).get("text") or "")[:400],
        payload={"query": payload.query, "engine": pack["engine"],
                 "urls": [h.get("url") for h in pack.get("hits", [])]},
        share_with=["medic", "shield", "vaani", "forge"],
    )
    return {**pack, "synthesis": synthesis}


@router.get("/benchmark")
async def benchmark(user=Depends(get_current_user)):
    from app.config import settings

    path = settings.data_dir / "operator_benchmark.json"
    if not path.exists():
        return {"run": False, "summary": None,
                "how": "python -m app.operator.suite  (runs the 20-task web suite)"}
    return {"run": True, "summary": json.loads(path.read_text())}
