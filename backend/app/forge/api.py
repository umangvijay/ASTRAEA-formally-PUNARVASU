"""FORGE API: failures, candidates, champion, eval history + trigger endpoints.

Scoping: candidates, eval history and failure mining are per-tenant. The
champion for a capability is global-by-design (one shared, measured best).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.forge import eval as forge_eval
from app.forge.models import ForgeCandidate, ForgeChampion, ForgeEvalRun
from app.model_forge.serving import available as model_available, champion_path
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/forge", tags=["forge"])


@router.get("/overview")
async def overview(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    champion = (
        (await db.execute(select(ForgeChampion).where(ForgeChampion.capability == forge_eval.CAPABILITY)))
        .scalar_one_or_none()
    )
    candidates = (
        (await db.execute(
            select(ForgeCandidate)
            .where(or_(ForgeCandidate.tenant_id == user.tenant_id,
                       ForgeCandidate.tenant_id.is_(None)))  # own + system proposals
            .order_by(desc(ForgeCandidate.id)).limit(20)
        ))
        .scalars().all()
    )
    history = (
        (await db.execute(
            select(ForgeEvalRun).where(
                ForgeEvalRun.capability == forge_eval.CAPABILITY,
                or_(ForgeEvalRun.tenant_id == user.tenant_id,
                    ForgeEvalRun.tenant_id.is_(None)),
            )
            .order_by(desc(ForgeEvalRun.id)).limit(30)
        )).scalars().all()
    )
    mining = await forge_eval.mine_failures(db, tenant_id=user.tenant_id)
    raw_path = champion.model_path if champion else None
    if raw_path in (None, "", "0"):
        raw_path = champion_path() or None
    return {
        "champion": {
            "capability": champion.capability, "kind": champion.kind,
            "score": champion.score, "model_path": raw_path,
            "scope": "global",
        } if champion else None,
        "model_forge": {"trained_model_available": model_available(),
                        "path": champion_path() or None},
        "candidates": [{"id": c.id, "source": c.source, "kind": c.kind, "status": c.status,
                        "reason": c.reason, "score_before": c.score_before,
                        "score_after": c.score_after} for c in candidates],
        "eval_history": [{"id": r.id, "variant": r.variant, "passed": r.passed,
                          "total": r.total, "score": r.score, "promoted": r.promoted,
                          "ran_at": str(r.ran_at)} for r in reversed(history)],
        "failure_mining": mining,
        "eval_task_count": settings.forge_eval_size,
    }


class CandidateIn(BaseModel):
    kind: str  # prompt-variant | model
    prompt_template: str | None = None
    reason: str = ""


@router.post("/candidates", status_code=201)
async def add_candidate(payload: CandidateIn, user=Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    cand = await forge_eval.propose_candidate(
        db, source="manual", kind=payload.kind, tenant_id=user.tenant_id,
        payload={"prompt_template": payload.prompt_template} if payload.kind == "prompt-variant" else {},
        reason=payload.reason,
    )
    return {"id": cand.id, "status": cand.status}


class EvalIn(BaseModel):
    candidate_id: int | None = None
    kind: str  # prompt-variant | model
    prompt_template: str | None = None
    variant_name: str = "candidate"


@router.post("/eval")
async def run_eval(payload: EvalIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Evaluate a variant on the verifiable SQL suite; promotion is automatic ONLY on
    measured improvement (champion + git commit updated then). LLM usage is metered
    to the calling tenant."""
    if payload.kind == "model" and not model_available():
        raise HTTPException(status_code=409, detail="model-forge weights not provisioned — "
                             "run: python -m app.model_forge.train")
    candidate = await db.get(ForgeCandidate, payload.candidate_id) if payload.candidate_id else None
    if candidate is not None and candidate.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="candidate not found")
    eval_run = await forge_eval.run_eval(
        db, variant_kind=payload.kind,
        payload={"prompt_template": payload.prompt_template},
        variant_name=payload.variant_name,
        tenant_id=user.tenant_id,
    )
    verdict = await forge_eval.promote_if_better(
        db, eval_run=eval_run, candidate=candidate, kind=payload.kind,
        payload={"prompt_template": payload.prompt_template,
                 "model_path": settings.forge_model_path if payload.kind == "model" else None},
    )
    return {"eval_run_id": eval_run.id, "passed": eval_run.passed, "total": eval_run.total,
            "score": eval_run.score, **verdict}
