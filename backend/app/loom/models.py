"""LOOM tables: the shared context fabric. Everything the platform learns, stored once, stamped."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LoomItem(Base):
    """A provenance-stamped artifact. origin_module answers 'where was this born';
    LoomUsage rows answer 'where has this been used since'."""

    __tablename__ = "loom_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    origin_module: Mapped[str] = mapped_column(String(30), nullable=False)  # shield|medic|vaani|…
    origin_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # artifact|incident|note|summary|…
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")
    share_with: Mapped[list[Any]] = mapped_column(JSON, nullable=False, server_default="[]")  # [] = all modules
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LoomUsage(Base):
    """Stamped on every read: 'module X used item Y at time Z'."""

    __tablename__ = "loom_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(String(36), ForeignKey("loom_items.id"), index=True)
    module: Mapped[str] = mapped_column(String(30), nullable=False)
    used_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SharingRule(Base):
    """The sharing matrix: may module X read LOOM context? Missing row = allowed (default-open)."""

    __tablename__ = "sharing_rules"
    __table_args__ = (UniqueConstraint("tenant_id", "module", name="uq_tenant_module"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    module: Mapped[str] = mapped_column(String(30), nullable=False)
    may_read: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")


class OrgProfile(Base):
    """Filled ONCE, read by every module: company, stack, services, compliance needs."""

    __tablename__ = "org_profiles"

    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), primary_key=True
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
