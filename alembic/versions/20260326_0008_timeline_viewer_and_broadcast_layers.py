# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
"""add timeline tracking, viewer signals, and broadcast asset packaging

Revision ID: 20260326_0008
Revises: 20260325_0007
Create Date: 2026-03-26 12:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260326_0008"
down_revision = "20260325_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "timeline_facts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fact_type", sa.String(length=40), nullable=False),
        sa.Column("subject_slug", sa.String(length=100), nullable=False, server_default=""),
        sa.Column("related_slug", sa.String(length=100), nullable=True),
        sa.Column("location_slug", sa.String(length=100), nullable=True),
        sa.Column("location_name", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("object_slug", sa.String(length=100), nullable=True),
        sa.Column("object_name", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="runtime"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "object_possessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("object_slug", sa.String(length=100), nullable=False),
        sa.Column("object_name", sa.String(length=150), nullable=False),
        sa.Column("holder_character_slug", sa.String(length=100), nullable=True),
        sa.Column("location_slug", sa.String(length=100), nullable=True),
        sa.Column("location_name", sa.String(length=150), nullable=False, server_default=""),
        sa.Column("possession_status", sa.String(length=30), nullable=False, server_default="room"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_slug"),
    )
    op.create_table(
        "viewer_signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("signal_key", sa.String(length=150), nullable=False),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=180), nullable=False),
        sa.Column("intensity", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("sentiment", sa.String(length=30), nullable=False, server_default="mixed"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False, server_default="operator"),
        sa.Column("retention_impact", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("signal_key"),
    )
    op.create_table(
        "broadcast_asset_packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("monetization_message_id", sa.BigInteger(), nullable=True),
        sa.Column("speaker_slug", sa.String(length=100), nullable=False),
        sa.Column("asset_title", sa.String(length=220), nullable=False),
        sa.Column("hook_line", sa.Text(), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=False),
        sa.Column("long_description", sa.JSON(), nullable=False),
        sa.Column("chapter_markers", sa.JSON(), nullable=False),
        sa.Column("clip_manifest", sa.JSON(), nullable=False),
        sa.Column("ship_labels", sa.JSON(), nullable=False),
        sa.Column("theory_labels", sa.JSON(), nullable=False),
        sa.Column("faction_labels", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("comment_seed", sa.Text(), nullable=False),
        sa.Column("asset_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["monetization_message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("broadcast_asset_packages")
    op.drop_table("viewer_signals")
    op.drop_table("object_possessions")
    op.drop_table("timeline_facts")
