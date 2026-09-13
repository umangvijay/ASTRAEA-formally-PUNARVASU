"""phase 2: pulse telemetry tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_points",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service", sa.String(60), nullable=False, index=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("request_rate", sa.Float(), nullable=False),
        sa.Column("error_rate", sa.Float(), nullable=False),
        sa.Column("p95_latency", sa.Float(), nullable=False),
        sa.Column("cpu", sa.Float(), nullable=False),
    )
    op.create_table(
        "log_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service", sa.String(60), nullable=False, index=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("level", sa.String(10), nullable=False, server_default="INFO"),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_table(
        "deploy_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service", sa.String(60), nullable=False, index=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("kind", sa.String(30), nullable=False, server_default="deploy"),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "anomalies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service", sa.String(60), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
    )
    op.create_table(
        "fault_injections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service", sa.String(60), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("injected_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anomaly_id", sa.Integer(), nullable=True),
    )
    op.create_table(
        "pulse_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("service", sa.String(60), nullable=False),
        sa.Column("last_anomaly_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_baseline", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("healthy", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )


def downgrade() -> None:
    op.drop_table("pulse_state")
    op.drop_table("fault_injections")
    op.drop_table("anomalies")
    op.drop_table("deploy_events")
    op.drop_table("log_records")
    op.drop_table("metric_points")
