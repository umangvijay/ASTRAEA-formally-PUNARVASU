"""AES-256-GCM vault: tenant secrets encrypted at rest.

Key material: ASTRAEA_VAULT_KEY (hex/base64 32 bytes) or derived from the JWT
secret via scrypt (deterministic per deployment). Plaintext is never stored and
never returned except by the explicit reveal endpoint — which writes to the
security audit log every time.
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_KEY: bytes | None = None


def _persisted_key_secret() -> str:
    """A stable secret for deployments without a real JWT secret: a random key
    persisted once in the data dir. Deriving from the per-process ephemeral
    dev secret destroyed every stored secret on every restart."""
    path = settings.data_dir / "vault.key"
    try:
        if path.exists():
            material = path.read_text().strip()
            if material:
                return material
        import secrets as _secrets

        material = _secrets.token_hex(32)
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(material)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return material
    except OSError:
        # unwritable data dir (read-only fs): previous behaviour — derive from
        # whatever jwt secret exists — rather than failing every vault op
        return settings.jwt_secret or "astraea-vault-fallback"


def _master_key() -> bytes:
    global _KEY
    if _KEY is None:
        provided = os.environ.get("ASTRAEA_VAULT_KEY", "")
        if provided:
            raw = provided.strip()
            try:
                key = bytes.fromhex(raw)
                if len(key) != 32:
                    raise ValueError
            except ValueError:
                key = base64.b64decode(raw + "=" * (-len(raw) % 4))
            if len(key) != 32:
                raise ValueError("ASTRAEA_VAULT_KEY must decode to 32 bytes")
            _KEY = key
        else:
            secret = settings.jwt_secret
            if not secret or secret.startswith("ephemeral-"):
                secret = _persisted_key_secret()
            _KEY = hashlib.scrypt(
                secret.encode(), salt=b"astraea-vault-v1",
                n=2**14, r=8, p=1, dklen=32,
            )
    return _KEY


def encrypt(plaintext: str) -> str:
    """Returns 'nonce_hex:ciphertext_hex' (GCM tag included)."""
    nonce = os.urandom(12)
    ct = AESGCM(_master_key()).encrypt(nonce, plaintext.encode(), None)
    return f"{nonce.hex()}:{ct.hex()}"


def decrypt(blob: str) -> str:
    nonce_hex, ct_hex = blob.split(":", 1)
    return AESGCM(_master_key()).decrypt(bytes.fromhex(nonce_hex), bytes.fromhex(ct_hex), None).decode()
