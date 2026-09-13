"""Public + community endpoints: contact messages, blog (auth-gated writes)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.loom.models import LoomItem
from app.shared.deps import get_current_user, get_db

router = APIRouter(tags=["public"])


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    message: str = Field(min_length=5, max_length=4000)


@router.post("/api/contact", status_code=201)
async def contact(payload: ContactIn, db: AsyncSession = Depends(get_db)):
    from app.core.models import Tenant, User
    from app.loom import service as loom

    founder = (
        await db.execute(select(User).where(User.email == "founder@astraea.local"))
    ).scalar_one_or_none()
    if founder is None:
        tenant = Tenant(name="Astraea HQ")
        db.add(tenant)
        await db.flush()
        db.add(User(tenant_id=tenant.id, email="founder@astraea.local",
                    password_hash="", full_name="Umang Vijay", role="superadmin"))
        await db.flush()
        tid = tenant.id
    else:
        tid = founder.tenant_id

    await loom.write_item(
        db, tid, origin_module="contact", kind="message",
        title=f"Message from {payload.name}", summary=payload.message[:200],
        payload={"name": payload.name, "email": payload.email, "message": payload.message},
    )
    return {"sent": True}


class BlogIn(BaseModel):
    title: str = Field(min_length=5, max_length=200)
    body: str = Field(min_length=20, max_length=50000)
    tags: list[str] = Field(default_factory=list)


@router.get("/api/blog")
async def blog_list(limit: int = 20, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(LoomItem).where(LoomItem.kind == "blog")
            .order_by(desc(LoomItem.created_at)).limit(min(limit, 100))
        )
    ).scalars().all()
    return {"posts": [{
        "id": p.id, "title": p.title, "summary": p.summary,
        "body": (p.payload or {}).get("body", ""),
        "tags": (p.payload or {}).get("tags", []),
        "author": p.origin_module, "created_at": str(p.created_at),
    } for p in rows]}


@router.post("/api/blog", status_code=201)
async def blog_create(payload: BlogIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.loom import service as loom

    item = await loom.write_item(
        db, user.tenant_id, origin_module=f"blog:{user.email}", kind="blog",
        title=payload.title, summary=payload.body[:200],
        payload={"body": payload.body, "tags": payload.tags},
    )
    return {"id": item.id, "title": payload.title}
