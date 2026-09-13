"""phase 5: vaani voice tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vaani_bookings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("customer_name", sa.String(120), nullable=False),
        sa.Column("service", sa.String(120), nullable=False),
        sa.Column("scheduled_for", sa.String(120), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("run_id", sa.String(36), nullable=True),
    )
    op.create_table(
        "vaani_transcripts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("turns", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("latencies", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("outcome", sa.String(30), nullable=False, server_default="completed"),
    )


def downgrade() -> None:
    op.drop_table("vaani_transcripts")
    op.drop_table("vaani_bookings")
