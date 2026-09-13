"""SHIELD tables: security events, DB-driven rules, ATT&CK techniques, incidents, attack graph."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    ts: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    host: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    event: Mapped[str] = mapped_column(String(40), nullable=False)  # login_failure|login_success|process_exec|connection|data_transfer
    user: Mapped[str | None] = mapped_column(String(60), nullable=True)
    src_ip: Mapped[str | None] = mapped_column(String(45), nullable=True, index=True)
    dst_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    dst_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    process: Mapped[str | None] = mapped_column(Text, nullable=True)
    bytes_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")


class AttackTechnique(Base):
    """MITRE ATT&CK reference data — techniques are looked up from rules, never hardcoded in logic."""

    __tablename__ = "attack_techniques"

    id: Mapped[str] = mapped_column(String(12), primary_key=True)  # T1110 …
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    tactic: Mapped[str] = mapped_column(String(60), nullable=False)  # Credential Access, Discovery…
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")


class ShieldRule(Base):
    """Detection rules ARE data: thresholds and technique mapping live in the DB, editable per tenant."""

    __tablename__ = "shield_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    event_types: Mapped[list[Any]] = mapped_column(JSON, nullable=False)  # which events feed this rule
    threshold: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)  # e.g. {"count": 5, "window_s": 60}
    technique_id: Mapped[str] = mapped_column(String(12), ForeignKey("attack_techniques.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, server_default="high")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")


class ShieldIncident(Base):
    __tablename__ = "shield_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), index=True)
    detected_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    host: Mapped[str] = mapped_column(String(60), nullable=False)
    attacker_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    severity: Mapped[str] = mapped_column(String(12), nullable=False, server_default="high")
    rule_hits: Mapped[list[Any]] = mapped_column(JSON, nullable=False, server_default="[]")
    techniques: Mapped[list[Any]] = mapped_column(JSON, nullable=False, server_default="[]")
    narrative: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    attack_graph: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")
    containment: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="open", index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ShieldGraphNode(Base):
    __tablename__ = "shield_graph_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(Integer, ForeignKey("shield_incidents.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # attacker|host|user|external
    label: Mapped[str] = mapped_column(String(120), nullable=False)


class ShieldGraphEdge(Base):
    __tablename__ = "shield_graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    incident_id: Mapped[int] = mapped_column(Integer, ForeignKey("shield_incidents.id"), index=True)
    src: Mapped[str] = mapped_column(String(120), nullable=False)
    dst: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)  # attacked|logged_in|scanned|exfiltrated|beaconed
    technique_id: Mapped[str | None] = mapped_column(String(12), nullable=True)
