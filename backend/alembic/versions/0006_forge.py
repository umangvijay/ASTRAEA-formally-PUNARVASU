"""phase 6: forge tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forge_candidates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("module", sa.String(30), nullable=False, server_default="core"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="proposed", index=True),
        sa.Column("score_before", sa.Float(), nullable=True),
        sa.Column("score_after", sa.Float(), nullable=True),
    )
    op.create_table(
        "forge_champions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("capability", sa.String(60), nullable=False, unique=True, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=True),
        sa.Column("model_path", sa.String(300), nullable=True),
        sa.Column("score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "forge_eval_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("capability", sa.String(60), nullable=False, index=True),
        sa.Column("variant", sa.String(120), nullable=False),
        sa.Column("passed", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("promoted", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("forge_eval_runs")
    op.drop_table("forge_champions")
    op.drop_table("forge_candidates")
