"""LOOM API: items, module context (with usage stamping), sharing matrix, org profile."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.loom import service
from app.loom.models import LoomItem, LoomUsage
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/loom", tags=["loom"])


def _module_or_console(x_module: str | None) -> str:
    module = (x_module or "console").lower().strip()
    if module not in service.KNOWN_MODULES:
        raise HTTPException(status_code=422, detail=f"unknown module '{module}'")
    return module


class ItemIn(BaseModel):
    kind: str = Field(default="note", max_length=30)
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=4000)
    payload: dict[str, Any] = Field(default_factory=dict)
    share_with: list[str] = Field(default_factory=list)  # empty = share with all modules


@router.post("/items", status_code=201)
async def create_item(payload: ItemIn, x_module: str | None = Header(default=None),
                      user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    origin = _module_or_console(x_module)
    item = await service.write_item(
        db, user.tenant_id, origin_module=origin, kind=payload.kind, title=payload.title,
        summary=payload.summary, payload=payload.payload, share_with=payload.share_with,
    )
    return service.item_out(item, used_by=[])


@router.get("/items")
async def list_items(kind: str | None = None, origin: str | None = None, limit: int = 100,
                     user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    q = select(LoomItem).where(LoomItem.tenant_id == user.tenant_id)
    if kind:
        q = q.where(LoomItem.kind == kind)
    if origin:
        q = q.where(LoomItem.origin_module == origin)
    rows = (await db.execute(q.order_by(LoomItem.created_at.desc(), LoomItem.id.desc())
                             .limit(min(limit, 300)))).scalars().all()
    out = []
    for item in rows:
        used_by = sorted(set((await db.execute(
            select(LoomUsage.module).where(LoomUsage.item_id == item.id).distinct()
        )).scalars().all()))
        out.append(service.item_out(item, used_by))
    return {"items": out}


@router.get("/search")
async def search(q: str = Query(..., min_length=2, max_length=500), limit: int = 8,
                 user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Semantic search over shared memory (vector DB) — provenance-stamped hits."""
    hits = await service.semantic_search(db, user.tenant_id, q, k=min(limit, 25))
    return {"query": q, "hits": hits}


@router.get("/context")
async def context(module: str = Query(...), limit: int = 50,
                  user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """What a given module sees right now — reads are stamped as USED BY <module>."""
    module = _module_or_console(module)
    items = await service.context_for(db, user.tenant_id, module, limit=limit)
    return {"module": module, "items": items}


@router.get("/sharing")
async def get_sharing(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"matrix": await service.sharing_matrix(db, user.tenant_id)}


class SharingPatch(BaseModel):
    module: str
    may_read: bool


@router.patch("/sharing")
async def patch_sharing(payload: SharingPatch, user=Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    module = _module_or_console(payload.module)
    state = await service.set_sharing(db, user.tenant_id, module, payload.may_read)
    return {"matrix": {**await service.sharing_matrix(db, user.tenant_id)}}


@router.get("/profile")
async def get_profile(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return {"profile": await service.org_profile(db, user.tenant_id)}


class ProfileIn(BaseModel):
    content: dict[str, Any]


@router.put("/profile")
async def put_profile(payload: ProfileIn, user=Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    return {"profile": await service.put_org_profile(db, user.tenant_id, payload.content)}
