"""VAULT API — encrypted secrets per tenant + the security audit trail viewer."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import AuditLog, VaultItem
from app.shared.audit import audit
from app.shared.deps import get_current_user, get_db
from app.shared import vault

router = APIRouter(tags=["vault"])


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


class SecretIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    secret: str = Field(min_length=1, max_length=8000)
    share_with: list[str] = Field(default_factory=list)


@router.get("/api/vault")
async def list_secrets(user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Names and metadata only — plaintext requires the reveal endpoint."""
    rows = (
        (await db.execute(
            select(VaultItem).where(VaultItem.tenant_id == user.tenant_id)
            .order_by(desc(VaultItem.created_at))
        ))
        .scalars()
        .all()
    )
    return {"items": [{"id": v.id, "name": v.name, "share_with": v.share_with,
                       "created_at": str(v.created_at)} for v in rows]}


@router.post("/api/vault", status_code=201)
async def create_secret(payload: SecretIn, request: Request,
                        user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    existing = (
        await db.execute(
            select(VaultItem).where(
                VaultItem.tenant_id == user.tenant_id, VaultItem.name == payload.name
            )
        )
    ).scalar_one_or_none()
    blob = vault.encrypt(payload.secret)
    if existing:
        existing.ciphertext = blob
        existing.share_with = payload.share_with
        await db.commit()
        item = existing
    else:
        item = VaultItem(
            tenant_id=user.tenant_id, name=payload.name, ciphertext=blob,
            share_with=payload.share_with, created_by=user.id,
        )
        db.add(item)
        await db.commit()
        await db.refresh(item)
    await audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="vault.store", detail=payload.name, ip=_ip(request))
    return {"id": item.id, "name": item.name, "updated": existing is not None}


@router.post("/api/vault/{item_id}/reveal")
async def reveal_secret(item_id: str, request: Request,
                        user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Deliberately explicit: decrypting a secret is a first-class audited action."""
    item = await db.get(VaultItem, item_id)
    if item is None or item.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="secret not found")
    try:
        value = vault.decrypt(item.ciphertext)
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="decryption failed (vault key changed?)")
    await audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="vault.reveal", detail=item.name, ip=_ip(request))
    return {"id": item.id, "name": item.name, "secret": value}


@router.delete("/api/vault/{item_id}", status_code=204)
async def delete_secret(item_id: str, request: Request,
                        user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(VaultItem, item_id)
    if item is None or item.tenant_id != user.tenant_id:
        raise HTTPException(status_code=404, detail="secret not found")
    await db.delete(item)
    await db.commit()
    await audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="vault.delete", detail=item.name, ip=_ip(request))
    # 204 must carry no body — a JSON body here breaks strict clients
    return Response(status_code=204)


@router.get("/api/security/audit")
async def audit_trail(limit: int = 100, user=Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    rows = (
        (await db.execute(
            select(AuditLog).where(AuditLog.tenant_id == user.tenant_id)
            .order_by(desc(AuditLog.id)).limit(min(limit, 500))
        ))
        .scalars()
        .all()
    )
    return {"events": [{"id": a.id, "ts": str(a.ts), "action": a.action,
                        "detail": a.detail, "ip": a.ip} for a in rows]}
