# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
"""add daily life, payoff debt, shadow replay, and youtube adapter state

Revision ID: 20260329_0010
Revises: 20260328_0009
Create Date: 2026-03-29 09:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260329_0010"
down_revision = "20260328_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_life_schedule_slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slot_key", sa.String(length=120), nullable=False),
        sa.Column(
            "horizon_key",
            sa.String(length=40),
            nullable=False,
            server_default="current-day",
        ),
        sa.Column("participant_slug", sa.String(length=100), nullable=True),
        sa.Column("participant_name", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("role_type", sa.String(length=40), nullable=False, server_default="resident"),
        sa.Column("location_slug", sa.String(length=100), nullable=True),
        sa.Column("location_name", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(length=60), nullable=False, server_default="household"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("window_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slot_key", "window_start_at", name="uq_daily_life_schedule_slot_window"),
    )
    op.create_table(
        "payoff_debt_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("debt_key", sa.String(length=150), nullable=False),
        sa.Column("debt_type", sa.String(length=60), nullable=False),
        sa.Column("subject", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payoff_class", sa.String(length=40), nullable=False, server_default="beat"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("linked_character_slug", sa.String(length=100), nullable=True),
        sa.Column("due_window", sa.String(length=40), nullable=False, server_default="soon"),
        sa.Column("heat", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("urgency", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("freshness_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("last_touched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("debt_key"),
    )
    op.create_table(
        "youtube_adapter_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("state_key", sa.String(length=50), nullable=False, server_default="primary"),
        sa.Column("last_harvest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_offsets", sa.JSON(), nullable=False),
        sa.Column("normalized_counts", sa.JSON(), nullable=False),
        sa.Column("active_themes", sa.JSON(), nullable=False),
        sa.Column("ship_heat", sa.JSON(), nullable=False),
        sa.Column("theory_heat", sa.JSON(), nullable=False),
        sa.Column("retention_alerts", sa.JSON(), nullable=False),
        sa.Column("clip_spikes", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_key"),
    )
    op.create_table(
        "shadow_replay_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("changed_files", sa.JSON(), nullable=False),
        sa.Column("compared_turns", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("regression_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("regressions", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("shadow_replay_runs")
    op.drop_table("youtube_adapter_state")
    op.drop_table("payoff_debt_items")
    op.drop_table("daily_life_schedule_slots")
