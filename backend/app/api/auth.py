"""Auth + tenancy. Registering creates a personal tenant — every user owns their data from minute one."""

from __future__ import annotations

import datetime as dt
import re
import time
from collections import deque

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models import Tenant, User
from app.shared.deps import get_current_user, get_db
from app.shared.audit import audit
from app.shared.security import create_access_token, hash_password, needs_rehash, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# naive in-process limiter, upgraded: sliding window per IP + per-email lockout
_login_attempts: dict[str, deque[float]] = {}
_failed_logins: dict[str, tuple[int, float]] = {}  # key(email|ip) -> (count, locked_until)
_LOCK_THRESHOLD = 5
_LOCK_SECONDS = 900  # 15 minutes


def _rate_ok(client_ip: str) -> bool:
    now = time.time()
    window = _login_attempts.setdefault(client_ip, deque())
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= 10:
        return False
    window.append(now)
    return True


def _locked(email: str, ip: str) -> tuple[bool, int]:
    """Escalating lockout on repeated failures for the same email+IP pair."""
    key = f"{email}|{ip}"
    count, locked_until = _failed_logins.get(key, (0, 0.0))
    now = time.time()
    if locked_until > now:
        return True, int(locked_until - now)
    return False, 0


def _record_failure(email: str, ip: str) -> None:
    key = f"{email}|{ip}"
    count, _ = _failed_logins.get(key, (0, 0.0))
    count += 1
    locked_until = time.time() + _LOCK_SECONDS if count >= _LOCK_THRESHOLD else 0.0
    _failed_logins[key] = (count, locked_until)


def _clear_failures(email: str, ip: str) -> None:
    _failed_logins.pop(f"{email}|{ip}", None)


def _user_out(user: User, tenant: Tenant) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "tenant": {"id": tenant.id, "name": tenant.name},
    }


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


@router.post("/register", status_code=201)
async def register(payload: RegisterIn, db: AsyncSession = Depends(get_db)) -> dict:
    email = payload.email.lower().strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=422, detail="Invalid email")
    pw = payload.password
    if (len(pw) < 8 or not re.search(r"[A-Za-z]", pw)
            or not re.search(r"\d", pw)):
        raise HTTPException(status_code=422,
                            detail="Password needs 8+ characters with letters and numbers")

    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    first_name = payload.full_name.strip().split()[0]
    tenant = Tenant(name=f"{first_name}'s Workspace")
    user = User(
        tenant_id=tenant.id,  # set after tenant flush below
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
    )
    db.add(tenant)
    await db.flush()
    user.tenant_id = tenant.id
    db.add(user)
    await db.commit()
    await db.refresh(tenant)

    return {
        "access_token": create_access_token(user.id, tenant.id),
        "user": _user_out(user, tenant),
    }


@router.post("/login")
async def login(request: Request, payload: LoginIn, db: AsyncSession = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    if not _rate_ok(ip):
        await audit(db, action="login.rate_limited", detail=payload.email, ip=ip)
        raise HTTPException(status_code=429, detail="Too many attempts — wait a minute")

    email = payload.email.lower().strip()
    locked, retry_in = _locked(email, ip)
    if locked:
        await audit(db, action="login.locked_out", detail=email, ip=ip)
        raise HTTPException(
            status_code=423,
            detail=f"Account temporarily locked after repeated failures — try in {max(retry_in // 60, 1)} min",
        )

    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    # constant-ish behaviour: same error whether email or password is wrong
    if user is None or not verify_password(payload.password, user.password_hash):
        _record_failure(email, ip)
        await audit(db, action="login.failed", detail=email, ip=ip)
        if user is not None:
            from app.shield import live as shield_live
            await shield_live.record(
                user.tenant_id, event="login_failure", user=email, src_ip=ip,
                process="auth.login",
            )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # transparent upgrade: legacy scrypt hash → Argon2id
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)

    _clear_failures(email, ip)
    user.last_login_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()
    tenant = await db.get(Tenant, user.tenant_id)
    await audit(db, tenant_id=user.tenant_id, user_id=user.id,
                action="login.success", detail=email, ip=ip)
    from app.shield import live as shield_live
    await shield_live.record(
        user.tenant_id, event="login_success", user=email, src_ip=ip,
        process="auth.login",
    )

    return {
        "access_token": create_access_token(user.id, user.tenant_id, user.role),
        "user": _user_out(user, tenant),
    }


@router.get("/me")
async def me(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict:
    tenant = await db.get(Tenant, user.tenant_id)
    return {"user": _user_out(user, tenant)}


import secrets as _secrets
import datetime as _dt


@router.post("/guest", status_code=201)
async def guest_session(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """A time-boxed guest workspace: full platform for 30 minutes, then the token dies."""
    import uuid as _uuid

    guest_id = f"guest-{_secrets.token_hex(4)}"
    now = _dt.datetime.now(_dt.timezone.utc)
    tenant = Tenant(name=f"{guest_id} (guest)")
    user = User(
        tenant_id=tenant.id,  # set after flush below
        email=f"{guest_id}@guest.local",
        password_hash=hash_password(_secrets.token_hex(16)),  # unguessable; guest never logs back in
        full_name=f"{guest_id} (guest)",
        role="guest",
        expires_at=now + _dt.timedelta(minutes=31),  # outlives the token slightly; watchdog reaps later
    )
    db.add(tenant)
    await db.flush()
    user.tenant_id = tenant.id
    db.add(user)
    await db.commit()
    await db.refresh(tenant)

    ip = request.client.host if request.client else "unknown"
    from app.shield import live as shield_live
    await shield_live.record(
        tenant.id, event="login_success", user=user.email, src_ip=ip,
        process="auth.guest",
    )
    now2 = _dt.datetime.now(_dt.timezone.utc)
    import jwt as _jwt
    from app.config import settings as _s

    token = _jwt.encode(
        {"sub": user.id, "tid": tenant.id, "iat": now2,
         "exp": now2 + _dt.timedelta(minutes=30), "role": "guest"},
        _s.jwt_secret, algorithm=_s.jwt_algorithm,
    )
    return {"access_token": token, "guest": True, "expires_in_minutes": 30,
            "user": {"id": user.id, "email": user.email, "full_name": user.full_name,
                     "role": "guest", "tenant": {"id": tenant.id, "name": tenant.name}}}
