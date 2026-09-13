"""phase 8: benchmarks table for cross-module metrics

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # create_all() on first boot can already have this table; never fail a relaunch.
    bind = op.get_bind()
    if sa.inspect(bind).has_table("benchmarks"):
        return
    op.create_table(
        "benchmarks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("module", sa.String(32), nullable=False, index=True),
        sa.Column("metric", sa.String(64), nullable=False, index=True),
        sa.Column("value", sa.Float, nullable=False),
        sa.Column("metadata_json", sa.Text, nullable=True),
        sa.Column("tenant_id", sa.String(36), nullable=True, index=True),
        sa.Column("recorded_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("benchmarks")
