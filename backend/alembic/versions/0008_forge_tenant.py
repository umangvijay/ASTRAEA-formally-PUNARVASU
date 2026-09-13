"""phase 7: forge tenant scoping

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("forge_candidates",
                  sa.Column("tenant_id", sa.String(36), nullable=True))
    op.create_index("ix_forge_candidates_tenant_id", "forge_candidates", ["tenant_id"])
    op.add_column("forge_eval_runs",
                  sa.Column("tenant_id", sa.String(36), nullable=True))
    op.create_index("ix_forge_eval_runs_tenant_id", "forge_eval_runs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_forge_eval_runs_tenant_id", table_name="forge_eval_runs")
    op.drop_column("forge_eval_runs", "tenant_id")
    op.drop_index("ix_forge_candidates_tenant_id", table_name="forge_candidates")
    op.drop_column("forge_candidates", "tenant_id")
