"""SENTINEL auth: tenant resolution via per-tenant API key (X-API-Key) or user JWT."""

from __future__ import annotations

import hashlib

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.models import Tenant
from app.shared.deps import get_db


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    import secrets

    return f"pvu_{secrets.token_hex(16)}"


async def get_tenant_by_key(request: Request, db: AsyncSession = Depends(get_db)) -> Tenant:
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        from sqlalchemy import select

        tenant = (
            await db.execute(
                select(Tenant).where(Tenant.api_key_hash == hash_api_key(api_key))
            )
        ).scalar_one_or_none()
        if tenant is None:
            raise HTTPException(status_code=401, detail="Unknown API key")
        return tenant

    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = pyjwt.decode(
                auth.removeprefix("Bearer ").strip(),
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
        except pyjwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        tenant = await db.get(Tenant, payload.get("tid"))
        if tenant is None:
            raise HTTPException(status_code=401, detail="Tenant not found")
        return tenant

    raise HTTPException(status_code=401, detail="Provide X-API-Key or Bearer token")
