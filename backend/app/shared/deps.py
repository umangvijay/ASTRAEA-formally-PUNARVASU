"""FastAPI dependencies: DB session + current user."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import jwt as pyjwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal
from app.core.models import User
from app.shared.security import decode_access_token


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
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
