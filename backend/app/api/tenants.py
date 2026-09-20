"""Tenant API keys — how modules and external tools authenticate to SENTINEL's proxy."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.sentinel.deps import generate_api_key, hash_api_key
from app.shared.deps import get_current_user, get_db

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


class ApiKeyOut(BaseModel):
    api_key: str
    note: str = "store this now — it is shown only once"


@router.post("/me/api-key", response_model=ApiKeyOut)
async def rotate_api_key(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException

    from app.core.models import Tenant

    # rotating the tenant key silently breaks every existing SENTINEL client —
    # that decision belongs to owners/admins, not to guests or members
    if user.role not in ("owner", "admin", "superadmin"):
        raise HTTPException(status_code=403, detail="owner or admin role required")
    tenant = await db.get(Tenant, user.tenant_id)
    key = generate_api_key()
    tenant.api_key_hash = hash_api_key(key)
    await db.commit()
    return ApiKeyOut(api_key=key)


@router.get("/me/api-key")
async def peek_api_key(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.core.models import Tenant

    tenant = await db.get(Tenant, user.tenant_id)
    masked = f"pvu_****{tenant.api_key_hash[-4:]}" if tenant.api_key_hash else None
    return {"api_key_masked": masked, "configured": tenant.api_key_hash is not None}


@router.get("/admin/overview")
async def admin_overview(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Role-gated: only admin / superadmin see the fleet view."""
    from sqlalchemy import func as _f, select as _select

    from app.core.models import Run, Tenant, User

    if user.role not in ("admin", "superadmin"):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="admin role required")
    tenants_n = (await db.execute(_select(_f.count()).select_from(Tenant))).scalar_one()
    users_n = (await db.execute(_select(_f.count()).select_from(User))).scalar_one()
    runs_n = (await db.execute(_select(_f.count()).select_from(Run))).scalar_one()
    latest = (
        await db.execute(_select(User.email, User.role, User.created_at)
                         .order_by(User.created_at.desc()).limit(10))
    ).all()
    return {"tenants": tenants_n, "users": users_n, "runs": runs_n,
            "recent_users": [{"email": e, "role": r, "created": str(c)} for e, r, c in latest]}
