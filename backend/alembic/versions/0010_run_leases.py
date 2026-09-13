"""milestone 2: durable run queue lease columns on runs

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not insp.has_table("runs"):
        return
    cols = {c["name"] for c in insp.get_columns("runs")}
    if "worker_id" not in cols:
        op.add_column("runs", sa.Column("worker_id", sa.String(80), nullable=True))
    if "lease_expires_at" not in cols:
        op.add_column("runs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    if "heartbeat_at" not in cols:
        op.add_column("runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    indexes = {i["name"] for i in insp.get_indexes("runs")}
    if "ix_runs_lease_expires_at" not in indexes:
        op.create_index("ix_runs_lease_expires_at", "runs", ["lease_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_runs_lease_expires_at", table_name="runs")
    op.drop_column("runs", "heartbeat_at")
    op.drop_column("runs", "lease_expires_at")
    op.drop_column("runs", "worker_id")
