"""PULSE tables: telemetry, anomalies, chaos bookkeeping (for the MTTD/accuracy benchmark)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MetricPoint(Base):
    __tablename__ = "metric_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    service: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    request_rate: Mapped[float] = mapped_column(Float, nullable=False)
    error_rate: Mapped[float] = mapped_column(Float, nullable=False)   # percent
    p95_latency: Mapped[float] = mapped_column(Float, nullable=False)  # ms
    cpu: Mapped[float] = mapped_column(Float, nullable=False)          # percent


class LogRecord(Base):
    __tablename__ = "log_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    service: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    level: Mapped[str] = mapped_column(String(10), nullable=False, server_default="INFO")
    message: Mapped[str] = mapped_column(Text, nullable=False)


class DeployEvent(Base):
    """Deploys/config changes — the correlation signal for 'what changed 12 minutes ago?'."""

    __tablename__ = "deploy_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    service: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    kind: Mapped[str] = mapped_column(String(30), nullable=False, server_default="deploy")
    description: Mapped[str] = mapped_column(Text, nullable=False)


class Anomaly(Base):
    __tablename__ = "anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    service: Mapped[str] = mapped_column(String(60), nullable=False)
    detected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    score: Mapped[float] = mapped_column(Float, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)   # snapshot
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)  # z-scores, logs
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)   # medic run once spawned


class FaultInjection(Base):
    """Chaos bookkeeping — powers the MTTD / top-3 accuracy benchmark. Never shown to agents."""

    __tablename__ = "fault_injections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    service: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    injected_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    detected_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    anomaly_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PulseState(Base):
    """Detector bookkeeping (baselines, cooldowns) — per tenant/service."""

    __tablename__ = "pulse_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    service: Mapped[str] = mapped_column(String(60), nullable=False)
    last_anomaly_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_baseline: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")
    healthy: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
