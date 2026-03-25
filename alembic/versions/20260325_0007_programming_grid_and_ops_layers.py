# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
"""add programming grid, canon court, monetization packages, and ops telemetry

Revision ID: 20260325_0007
Revises: 20260324_0006
Create Date: 2026-03-25 17:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260325_0007"
down_revision = "20260324_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "programming_grid_slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("horizon", sa.String(length=20), nullable=False),
        sa.Column("slot_key", sa.String(length=80), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("target_axis", sa.String(length=40), nullable=False, server_default="mixed"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "horizon",
            "slot_key",
            "window_start_at",
            name="uq_programming_grid_slot_window",
        ),
    )
    op.create_table(
        "canon_court_findings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("issue_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="warning"),
        sa.Column("action", sa.String(length=30), nullable=False, server_default="allow"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "monetization_packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("highlight_message_id", sa.Integer(), nullable=True),
        sa.Column("speaker_slug", sa.String(length=100), nullable=False),
        sa.Column("primary_title", sa.String(length=220), nullable=False),
        sa.Column("alternate_titles", sa.JSON(), nullable=False),
        sa.Column("short_title_options", sa.JSON(), nullable=False),
        sa.Column("hook_line", sa.Text(), nullable=False),
        sa.Column("quote_line", sa.Text(), nullable=False),
        sa.Column("summary_blurb", sa.Text(), nullable=False),
        sa.Column("recap_blurb", sa.Text(), nullable=False),
        sa.Column("chapter_label", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("comment_prompt", sa.Text(), nullable=False, server_default=""),
        sa.Column("ship_angle", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("theory_angle", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("betrayal_angle", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("faction_labels", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("recommended_clip_start_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommended_clip_end_seconds", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["highlight_message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ops_telemetry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("runtime_status", sa.String(length=20), nullable=False),
        sa.Column("phase", sa.String(length=50), nullable=False, server_default="unknown"),
        sa.Column("degraded_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("load_tier", sa.String(length=20), nullable=False, server_default="low"),
        sa.Column("average_latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checkpoint_age_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recap_age_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strategy_age_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drift_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "progression_contract_open",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("restart_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_strategy", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("auto_remediations", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ops_telemetry")
    op.drop_table("monetization_packages")
    op.drop_table("canon_court_findings")
    op.drop_table("programming_grid_slots")
