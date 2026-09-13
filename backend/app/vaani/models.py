"""VAANI voice models: bookings (the durable actions) and call transcripts."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class VaaniBooking(Base):
    __tablename__ = "vaani_bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    service: Mapped[str] = mapped_column(String(120), nullable=False)
    scheduled_for: Mapped[str] = mapped_column(String(120), nullable=False)  # natural language time
    notes: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class VaaniTranscript(Base):
    __tablename__ = "vaani_transcripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    turns: Mapped[list[Any]] = mapped_column(JSON, nullable=False, server_default="[]")
    latencies: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")
    outcome: Mapped[str] = mapped_column(String(30), nullable=False, server_default="completed")
