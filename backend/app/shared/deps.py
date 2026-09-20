"""FastAPI dependencies: DB session + current user."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.core.models import Tenant, User
from app.shared.security import decode_access_token


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def _user_for_api_key(db: AsyncSession, api_key: str) -> User:
    """Resolve a tenant API key (X-API-Key) to the tenant's owner account.

    The console tells users a generated key works "platform-wide" — so every
    JWT-gated route accepts it too, authenticated as the tenant's first user.
    """
    from app.sentinel.deps import hash_api_key

    tenant = (
        await db.execute(select(Tenant).where(Tenant.api_key_hash == hash_api_key(api_key)))
    ).scalar_one_or_none()
    if tenant is None:
        raise HTTPException(status_code=401, detail="Unknown API key")
    user = (
        await db.execute(
            select(User)
            .where(User.tenant_id == tenant.id)
            .order_by(User.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="API key has no user account")
    return user


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    api_key = request.headers.get("X-API-Key", "")
    if api_key:
        return await _user_for_api_key(db, api_key)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = auth.removeprefix("Bearer ").strip()
    try:
        payload = decode_access_token(token)
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = (
        await db.execute(select(User).where(User.id == payload.get("sub")))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user
