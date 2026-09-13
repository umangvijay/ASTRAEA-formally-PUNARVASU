"""Security audit trail helper — one call, never raises, never blocks the caller."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AuditLog

logger = logging.getLogger("audit")


async def audit(db: AsyncSession, *, tenant_id: str | None = None,
                user_id: str | None = None, action: str,
                detail: str = "", ip: str | None = None) -> None:
    try:
        db.add(AuditLog(tenant_id=tenant_id, user_id=user_id, action=action,
                        detail=detail[:1000], ip=ip))
        await db.commit()
    except Exception:  # noqa: BLE001 — audit must never break the request path
        logger.exception("audit write failed for %s", action)
