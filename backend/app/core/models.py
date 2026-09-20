"""Core tables: tenancy + users (Phase 0) + durable run engine tables (Phase 1)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _uid() -> str:
    return str(uuid.uuid4())


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    plan: Mapped[str] = mapped_column(String(30), nullable=False, server_default="free")
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)  # sha256 of pvu_… key
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, server_default="owner")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # guest accounts expire; null = permanent


# ── durable run engine ─────────────────────────────────────────────


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    workflow: Mapped[list[Any]] = mapped_column(JSON, nullable=False)  # ordered steps
    origin_module: Mapped[str] = mapped_column(String(30), nullable=False, server_default="console")
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="queued", index=True
    )  # queued|running|awaiting_approval|completed|failed|interrupted
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ── durable distributed queue (Milestone 2) ──
    # A worker CLAIMS a run (worker_id + lease_expires_at), HEARTBEATs while it runs,
    # and RELEASEs on terminal/parked states. A dead worker's lease expires and any
    # other worker re-claims the run, resuming from the last completed event.
    worker_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    heartbeat_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RunEvent(Base):
    """Append-only. The run IS this table — state is always reconstructable from events."""

    __tablename__ = "run_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("runs.id"), index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tokens_in: Mapped[int] = mapped_column(nullable=False, server_default="0", default=0)
    tokens_out: Mapped[int] = mapped_column(nullable=False, server_default="0", default=0)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Workflow(Base):
    """Stored workflow templates — data, not code (anti-hardcoding rule §4.1)."""

    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    needs_llm: Mapped[bool] = mapped_column(nullable=False, server_default="0")
    steps: Mapped[list[Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class VaultItem(Base):
    """Encrypted secret (AES-256-GCM, key derived from ASTRAEA_VAULT_KEY).
    Plaintext never leaves the reveal endpoint, and every reveal is audited."""

    __tablename__ = "vault_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uid)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)  # nonce_hex:ct_hex (GCM)
    share_with: Mapped[list[Any]] = mapped_column(JSON, nullable=False, server_default="[]")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditLog(Base):
    """Security audit trail: logins, reveals, approvals, rule changes, chaos, attacks."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ts: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TenantModule(Base):
    """Per-tenant SOLO/FUSION switch: which product modules' agents are active.
    LOOM memory is ALWAYS shared — activating a module later restores everything
    the other modules learned. No rows = FUSION (all active)."""

    __tablename__ = "tenant_modules"

    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), primary_key=True)
    module: Mapped[str] = mapped_column(String(30), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")


class LoginAttempt(Base):
    """DB-backed login throttling — the source of truth is shared, so every
    instance behind the load balancer sees the same window and lockout state
    (the old in-process dicts reset per instance and per restart)."""

    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ip: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
