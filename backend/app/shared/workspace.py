"""SOLO/FUSION workspace state per tenant.

FUSION (default): every module's agents run. SOLO: exactly one module runs.
Either way LOOM memory is shared — data learned under one module is instantly
available to the next, so adopting another module never means re-doing work.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import TenantModule

MODULES = ("medic", "operator", "shield", "vaani", "forge", "model_forge")


async def active_modules(db: AsyncSession, tenant_id: str) -> dict[str, bool]:
    """Module -> active map. No rows = FUSION (everything active)."""
    rows = (
        (await db.execute(select(TenantModule).where(TenantModule.tenant_id == tenant_id)))
        .scalars()
        .all()
    )
    state = {m: True for m in MODULES}
    for row in rows:
        state[row.module] = row.active
    return state


async def module_active(db: AsyncSession, tenant_id: str, module: str) -> bool:
    if module not in MODULES:
        return False
    row = (
        await db.execute(
            select(TenantModule).where(
                TenantModule.tenant_id == tenant_id, TenantModule.module == module
            )
        )
    ).scalar_one_or_none()
    return row.active if row else True


async def set_mode(db: AsyncSession, tenant_id: str, mode: str,
                   module: str | None = None) -> dict[str, bool]:
    if mode == "fusion":
        rows = (
            (await db.execute(
                select(TenantModule).where(TenantModule.tenant_id == tenant_id)
            ))
            .scalars()
            .all()
        )
        for row in rows:
            row.active = True
        await db.commit()
        return await active_modules(db, tenant_id)
    if mode == "solo":
        if module not in MODULES:
            raise ValueError(f"unknown module '{module}'")
        for m in MODULES:
            row = (
                await db.execute(
                    select(TenantModule).where(
                        TenantModule.tenant_id == tenant_id, TenantModule.module == m
                    )
                )
            ).scalar_one_or_none()
            active = m == module
            if row is None:
                row = TenantModule(tenant_id=tenant_id, module=m, active=active)
                db.add(row)
            else:
                row.active = active
        await db.commit()
        return await active_modules(db, tenant_id)
    raise ValueError(f"unknown mode '{mode}'")
