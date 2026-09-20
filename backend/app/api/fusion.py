"""FUSION workspace API — the cross-module timeline.

Merges, per tenant: run events, pulse anomalies, shield incidents and loom
artifacts into one newest-first realtime feed. Provenance is carried on every
entry (module + link), so the console shows who did what without guessing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Run, RunEvent
from app.loom.models import LoomItem
from app.pulse.models import Anomaly
from app.shield.models import ShieldIncident
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/fusion", tags=["fusion"])

EVENT_LABELS = {
    "run_started": "started working",
    "run_resumed": "resumed where it stopped",
    "run_completed": "finished the job",
    "run_failed": "hit an error",
    "run_interrupted": "was interrupted",
    "approval_required": "needs your decision",
    "approval_granted": "you approved",
    "approval_denied": "you rejected",
    "step_failed": "a step failed",
}

# what each workflow node actually DID, in plain words
NODE_LABELS = {
    "collect": "collected a machine report",
    "remember": "saved it to shared memory",
    "prepare": "prepared the change",
    "finish": "applied the change",
    "research": "did the research",
    "triage": "gathered telemetry evidence",
    "investigate": "ranked root-cause hypotheses",
    "reproduce": "reproduced the fault in a sandbox",
    "fix": "applied the fix",
    "correlate": "correlated the attack into a narrative",
    "graph": "built the attack graph",
    "contain": "applied containment",
    "book": "confirmed the booking",
    "operate": "worked the browser task",
    "gate": "waits for your approval",
}

MILESTONES = {"run_started", "run_resumed", "run_completed", "run_failed",
              "run_interrupted", "approval_required", "approval_granted",
              "approval_denied", "step_failed"}


def _stamp(kind: str, module: str, title: str, detail: str, ts, link: str | None) -> dict:
    return {"kind": kind, "module": module, "title": title, "detail": detail,
            "ts": str(ts), "link": link}


@router.get("/timeline")
async def timeline(limit: int = 40, user=Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)) -> dict:
    limit = min(limit, 100)
    out: list[dict] = []

    rows = (
        (await db.execute(
            select(RunEvent, Run)
            .join(Run, RunEvent.run_id == Run.id)
            .where(Run.tenant_id == user.tenant_id)
            .order_by(desc(RunEvent.id))
            .limit(limit)
        ))
        .all()
    )
    for ev, run in rows:
        if ev.type not in MILESTONES:
            continue  # step chatter stays in the run's own page — the timeline shows milestones
        label = EVENT_LABELS.get(ev.type, ev.type)
        detail = ""
        if ev.type == "approval_required":
            detail = str(ev.payload.get("prompt", ""))[:140] if ev.payload else "review and decide"
        elif ev.type in ("step_failed", "run_failed", "run_interrupted"):
            detail = str((ev.payload or {}).get("error", (ev.payload or {}).get("reason", "")))[:140]
        elif ev.type == "run_started":
            names = [st.get("name") for st in (run.workflow or []) if isinstance(st, dict)]
            human = [NODE_LABELS.get(n, n) for n in names]
            detail = "plan: " + " → ".join(human[:4])
        title = f"{run.goal[:76]} — {label}"
        out.append({**_stamp(ev.type, run.origin_module, title, detail, ev.created_at,
                             f"/console/runs/{run.id}"),
                    "attention": ev.type == "approval_required"})

    for a in (
        await db.execute(
            select(Anomaly).where(Anomaly.tenant_id == user.tenant_id)
            .order_by(desc(Anomaly.id)).limit(limit)
        )
    ).scalars().all():
        out.append(_stamp("anomaly", "medic",
                          f"Anomaly on {a.service} (score {a.score})",
                          f"drift in {a.evidence.get('drifted', '?')} "
                          f"({a.evidence.get('drift_sigma', '?')}σ)", a.detected_at,
                          f"/console/runs/{a.run_id}" if a.run_id else "/console/medic"))

    for i in (
        await db.execute(
            select(ShieldIncident).where(ShieldIncident.tenant_id == user.tenant_id)
            .order_by(desc(ShieldIncident.id)).limit(limit)
        )
    ).scalars().all():
        techs = ", ".join(t.get("id", "") for t in (i.techniques or []))
        out.append(_stamp("incident", "shield",
                          f"{i.severity} incident on {i.host}",
                          f"ATT&CK {techs}" if techs else i.narrative[:120],
                          i.detected_at,
                          f"/console/runs/{i.run_id}" if i.run_id else "/console/shield"))

    for item in (
        await db.execute(
            select(LoomItem).where(LoomItem.tenant_id == user.tenant_id)
            .order_by(desc(LoomItem.id)).limit(limit)
        )
    ).scalars().all():
        out.append(_stamp("loom", item.origin_module,
                          f"{item.kind}: {item.title[:80]}",
                          (item.summary or "")[:140], item.created_at, "/console/loom"))

    # attention items first (that is the entire point of the flag), newest
    # first within each group — the old key inverted this and sank them.
    out.sort(key=lambda e: (e.get("attention", False), e["ts"]), reverse=True)
    return {"timeline": out[:limit]}
