"""SENTINEL tables: editable guardrail rules (data, not code), events, usage metering."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
# Import the FK target so `tenants` is registered on Base.metadata even when the
# sentinel models/pipeline are imported in isolation (bug #7 — NoReferencedTableError).
from app.core.models import Tenant  # noqa: E402,F401


class GuardrailRule(Base):
    """Rules ARE data: pattern/scope/action live in the DB and are editable per tenant via the console."""

    __tablename__ = "guardrail_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True, index=True
    )  # NULL = global default rule
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    pattern: Mapped[str] = mapped_column(Text, nullable=False)  # regex
    scope: Mapped[str] = mapped_column(String(10), nullable=False, server_default="both")  # input|output|both
    action: Mapped[str] = mapped_column(String(10), nullable=False, server_default="redact")  # block|redact|flag
    replacement: Mapped[str] = mapped_column(String(60), nullable=False, server_default="[REDACTED]")
    severity: Mapped[str] = mapped_column(String(12), nullable=False, server_default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GuardrailEvent(Base):
    __tablename__ = "guardrail_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # input|output
    rule_name: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    sample: Mapped[str] = mapped_column(String(160), nullable=False, server_default="")  # already-redacted snippet
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latency_ms: Mapped[float] = mapped_column(nullable=False, server_default="0")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class UsageCounter(Base):
    """Per-tenant monthly token/request metering — quota enforcement lives here."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("tenant_id", "period", name="uq_tenant_period"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    blocked: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)


Index("ix_ge_tenant_created", GuardrailEvent.tenant_id, GuardrailEvent.created_at)
