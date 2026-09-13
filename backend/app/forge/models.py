"""FORGE tables: failure candidates, champions, eval history — the self-evolution ledger."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ForgeCandidate(Base):
    """A proposed improvement: mined from real failures, evaluated, promoted or rejected."""

    __tablename__ = "forge_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # owner; NULL = legacy/system row
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # failure-mining | model-forge | manual
    kind: Mapped[str] = mapped_column(String(20), nullable=False)    # prompt-variant | model | tool-config
    module: Mapped[str] = mapped_column(String(30), nullable=False, server_default="core")
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)  # e.g. {"prompt_template": "..."}
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="proposed", index=True)
    score_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_after: Mapped[float | None] = mapped_column(Float, nullable=True)


class ForgeChampion(Base):
    """The current best variant per capability. Exactly one active champion per name."""

    __tablename__ = "forge_champions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    capability: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)  # e.g. sql-writer
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ForgeEvalRun(Base):
    """Timestamped eval results — the week-over-week improvement chart's data."""

    __tablename__ = "forge_eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ran_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)  # owner; NULL = legacy/system row
    capability: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    variant: Mapped[str] = mapped_column(String(120), nullable=False)
    passed: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    promoted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, server_default="{}")
