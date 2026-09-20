"""enterprise GA: db-backed login throttling shared across instances

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if insp.has_table("login_attempts"):
        return  # create_all may have beaten us to it
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("ip", sa.String(64), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("ok", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_login_attempts_ip", "login_attempts", ["ip"])
    op.create_index("ix_login_attempts_email", "login_attempts", ["email"])
    op.create_index("ix_login_attempts_at", "login_attempts", ["at"])


def downgrade() -> None:
    op.drop_index("ix_login_attempts_at", table_name="login_attempts")
    op.drop_index("ix_login_attempts_email", table_name="login_attempts")
    op.drop_index("ix_login_attempts_ip", table_name="login_attempts")
    op.drop_table("login_attempts")
