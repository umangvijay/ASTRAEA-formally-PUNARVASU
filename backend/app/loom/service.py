"""LOOM service: write-once-provenance-stamped items, context reads that stamp usage back."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.loom.models import LoomItem, LoomUsage, OrgProfile, SharingRule
from app.shared.bus import publish

KNOWN_MODULES = {"medic", "operator", "shield", "vaani", "forge", "model_forge", "console"}


async def write_item(
    db: AsyncSession,
    tenant_id: str,
    *,
    origin_module: str,
    kind: str,
    title: str,
    summary: str = "",
    payload: dict[str, Any] | None = None,
    share_with: list[str] | None = None,
    origin_run_id: str | None = None,
) -> LoomItem:
    item = LoomItem(
        tenant_id=tenant_id,
        origin_module=origin_module,
        origin_run_id=origin_run_id,
        kind=kind,
        title=title,
        summary=summary,
        payload=payload or {},
        share_with=share_with or [],
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # index into vector memory (never blocks or breaks the write)
    try:
        from app.shared import vector

        text = f"{item.title}\n{item.summary}\n{json.dumps(item.payload or {}, default=str)[:2000]}"
        await vector.aindex_item(
            item.id, tenant_id, text,
            {"origin_module": item.origin_module, "kind": item.kind,
             "title": item.title[:200], "share_with": ",".join(item.share_with or [])},
        )
    except Exception:  # noqa: BLE001 — vector memory is best-effort
        pass

    await publish(f"loom:{tenant_id}", {
        "kind": "item_created", "item_id": item.id, "origin_module": origin_module,
        "title": item.title, "item_kind": kind,
    })
    return item


async def semantic_search(db: AsyncSession, tenant_id: str, query: str, *, k: int = 8,
                          module: str | None = None) -> list[dict[str, Any]]:
    """Vector search over shared memory, then provenance-stamp the reads."""
    from app.shared import vector

    raw = await vector.asearch(tenant_id, query, k=k * 2)
    out: list[dict[str, Any]] = []
    for hit in raw:
        item = await db.get(LoomItem, hit["item_id"])
        if item is None or item.tenant_id != tenant_id:
            continue
        if module and not _visible_to(item, module):
            continue
        used_by = sorted(set((await db.execute(
            select(LoomUsage.module).where(LoomUsage.item_id == item.id).distinct()
        )).scalars().all()))
        payload = item_out(item, used_by)
        payload["score"] = hit["score"]
        out.append(payload)
        if len(out) >= k:
            break
    return out


async def may_read(db: AsyncSession, tenant_id: str, module: str) -> bool:
    """Missing rule = allowed (default-open); an explicit False denies."""
    rule = (
        await db.execute(
            select(SharingRule).where(
                SharingRule.tenant_id == tenant_id, SharingRule.module == module
            )
        )
    ).scalar_one_or_none()
    return rule is None or rule.may_read


def _visible_to(item: LoomItem, module: str) -> bool:
    return not item.share_with or module in item.share_with


def item_out(item: LoomItem, used_by: list[str]) -> dict:
    return {
        "id": item.id,
        "origin_module": item.origin_module,
        "origin_run_id": item.origin_run_id,
        "kind": item.kind,
        "title": item.title,
        "summary": item.summary,
        "payload": item.payload,
        "created_at": str(item.created_at),
        "provenance": {"from": f"FROM {item.origin_module.upper()}",
                       "used_by": [f"USED BY {m.upper()}" for m in used_by]},
        "used_by": used_by,
        "share_with": item.share_with,
    }


async def context_for(
    db: AsyncSession, tenant_id: str, module: str, *, limit: int = 50,
    kinds: list[str] | None = None,
) -> list[dict]:
    """The aggregated context a module sees: visible items + usage stamping (the 'USED BY' trail)."""
    if not await may_read(db, tenant_id, module):
        return []

    q = (
        select(LoomItem)
        .where(LoomItem.tenant_id == tenant_id)
        .order_by(LoomItem.created_at.desc(), LoomItem.id.desc())
        .limit(limit * 2)
    )
    if kinds:
        q = q.where(LoomItem.kind.in_(kinds))

    rows = (await db.execute(q)).scalars().all()

    visible = [item for item in rows if _visible_to(item, module)]
    visible = visible[:limit]

    out: list[dict] = []
    for item in visible:
        # stamp THIS read first, so the trail includes whoever is reading right now
        db.add(LoomUsage(item_id=item.id, module=module))
        await db.commit()
        used_by = sorted(set(
            (await db.execute(
                select(LoomUsage.module).where(LoomUsage.item_id == item.id).distinct()
            )).scalars().all()
        ))
        out.append(item_out(item, used_by))
    return out


async def org_profile(db: AsyncSession, tenant_id: str) -> dict:
    row = await db.get(OrgProfile, tenant_id)
    return row.content if row else {}


async def put_org_profile(db: AsyncSession, tenant_id: str, content: dict[str, Any]) -> dict:
    row = await db.get(OrgProfile, tenant_id)
    if row is None:
        row = OrgProfile(tenant_id=tenant_id, content=content)
        db.add(row)
    else:
        row.content = content
    await db.commit()
    await publish(f"loom:{tenant_id}", {"kind": "profile_updated"})
    return row.content


async def sharing_matrix(db: AsyncSession, tenant_id: str) -> dict:
    rows = (
        (
            await db.execute(select(SharingRule).where(SharingRule.tenant_id == tenant_id))
        )
        .scalars()
        .all()
    )
    state = {m: True for m in KNOWN_MODULES}
    for row in rows:
        state[row.module] = row.may_read
    return state


async def set_sharing(db: AsyncSession, tenant_id: str, module: str, may_read: bool) -> dict:
    row = (
        await db.execute(
            select(SharingRule).where(
                SharingRule.tenant_id == tenant_id, SharingRule.module == module
            )
        )
    ).scalar_one_or_none()
    if row is None:
        row = SharingRule(tenant_id=tenant_id, module=module, may_read=may_read)
        db.add(row)
    else:
        row.may_read = may_read
    await db.commit()
    return {module: may_read}
