"""Trajectory memory: successful OPERATOR tasks are remembered in LOOM and replayed
(similarly-scored goals) — the 'skill library' that makes repeat tasks cheap."""

from __future__ import annotations


from sqlalchemy.ext.asyncio import AsyncSession

from app.loom import service as loom


def _tokens(text: str) -> set[str]:
    import re

    return {t.lower() for t in re.findall(r"[a-zA-Z0-9]+", text or "")}


async def save(db: AsyncSession, tenant_id: str, *, origin_run_id: str | None, goal: str,
               url: str, actions: list[dict]) -> str:
    """Persist a successful trajectory, stamped with OPERATOR provenance."""
    item = await loom.write_item(
        db, tenant_id,
        origin_module="operator",
        origin_run_id=origin_run_id,
        kind="trajectory",
        title=f"Trajectory: {goal[:80]}",
        summary=f"verified success on {url}",
        payload={"goal_tokens": sorted(_tokens(goal)), "url": url, "actions": actions},
        share_with=["operator", "forge"],
    )
    return item.id


async def retrieve(db: AsyncSession, tenant_id: str, goal: str, *, min_overlap: float = 0.6) -> dict | None:
    """Best matching past trajectory by goal-token overlap (computed, not canned)."""
    items = await loom.context_for(db, tenant_id, "operator", limit=60)
    goal_toks = _tokens(goal)
    best, best_score = None, 0.0
    for item in items:
        if item["kind"] != "trajectory":
            continue
        past_toks = set((item["payload"] or {}).get("goal_tokens", []))
        if not past_toks:
            continue
        overlap = len(goal_toks & past_toks) / max(1, len(goal_toks | past_toks))
        if overlap > best_score:
            best, best_score = item, overlap
    if best and best_score >= min_overlap:
        return {"trajectory_id": best["id"], "overlap": round(best_score, 2),
                "url": best["payload"].get("url"), "actions": best["payload"].get("actions", [])}
    return None