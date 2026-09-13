"""phase 4: shield tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("host", sa.String(60), nullable=False, index=True),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("user", sa.String(60), nullable=True),
        sa.Column("src_ip", sa.String(45), nullable=True, index=True),
        sa.Column("dst_ip", sa.String(45), nullable=True),
        sa.Column("dst_port", sa.Integer(), nullable=True),
        sa.Column("external", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("process", sa.Text(), nullable=True),
        sa.Column("bytes_out", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_table(
        "attack_techniques",
        sa.Column("id", sa.String(12), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("tactic", sa.String(60), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.create_table(
        "shield_rules",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=True, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("event_types", sa.JSON(), nullable=False),
        sa.Column("threshold", sa.JSON(), nullable=False),
        sa.Column("technique_id", sa.String(12), sa.ForeignKey("attack_techniques.id"), nullable=False),
        sa.Column("severity", sa.String(12), nullable=False, server_default="high"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
    )
    op.create_table(
        "shield_incidents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
        sa.Column("host", sa.String(60), nullable=False),
        sa.Column("attacker_ip", sa.String(45), nullable=True),
        sa.Column("severity", sa.String(12), nullable=False, server_default="high"),
        sa.Column("rule_hits", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("techniques", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("narrative", sa.Text(), nullable=False, server_default=""),
        sa.Column("attack_graph", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("containment", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="open", index=True),
        sa.Column("run_id", sa.String(36), nullable=True),
    )
    op.create_table(
        "shield_graph_nodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("shield_incidents.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
    )
    op.create_table(
        "shield_graph_edges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("incident_id", sa.Integer(), sa.ForeignKey("shield_incidents.id"), nullable=False, index=True),
        sa.Column("src", sa.String(120), nullable=False),
        sa.Column("dst", sa.String(120), nullable=False),
        sa.Column("label", sa.String(60), nullable=False),
        sa.Column("technique_id", sa.String(12), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("shield_graph_edges")
    op.drop_table("shield_graph_nodes")
    op.drop_table("shield_incidents")
    op.drop_table("shield_rules")
    op.drop_table("attack_techniques")
    op.drop_table("security_events")
