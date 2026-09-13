"""Password hashing: Argon2id (primary) with transparent scrypt upgrade path,
plus JWT handling.

Existing scrypt hashes verify exactly as before; on successful login they are
re-hashed to Argon2id (one-time, automatic).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import os

import jwt

from app.config import settings

_N, _R, _P, _DKLEN = 2**14, 8, 1, 32  # scrypt params (~16MB memory cost per hash)

try:  # Argon2id — memory-hard, GPU-resistant, the 2026 default
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, InvalidHashError

    _argon = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)  # 64MB
    _ARGON = True
except ImportError:  # pragma: no cover — argon2-cffi ships in requirements
    _ARGON = False


def hash_password(password: str) -> str:
    if _ARGON:
        return _argon.hash(password)
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def needs_rehash(stored: str) -> bool:
    """True when the stored hash is legacy (scrypt) and should be upgraded."""
    return _ARGON and not stored.startswith("$argon2")


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2"):
        try:
            return _argon.verify(stored, password)
        except (VerifyMismatchError, InvalidHashError, ValueError):
            return False
    try:
        algo, n, r, p, salt_hex, dk_hex = stored.split("$")
        if algo != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p),
            dklen=len(bytes.fromhex(dk_hex)),
        )
        return hmac.compare_digest(dk, bytes.fromhex(dk_hex))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, tenant_id: str, role: str | None = None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.access_token_expire_minutes),
        "jti": os.urandom(8).hex(),
    }
    if role:
        payload["role"] = role
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError on invalid/expired tokens."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
