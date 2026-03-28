# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
"""add chronology graph, voice fingerprints, guest circulation, and hot-patch canary runs

Revision ID: 20260328_0009
Revises: 20260326_0008
Create Date: 2026-03-28 10:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260328_0009"
down_revision = "20260326_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chronology_graph_nodes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("node_key", sa.String(length=150), nullable=False),
        sa.Column("node_type", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_key"),
    )
    op.create_table(
        "chronology_graph_edges",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_key", sa.String(length=150), nullable=False),
        sa.Column("predicate", sa.String(length=50), nullable=False),
        sa.Column("object_key", sa.String(length=150), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "contradiction_status",
            sa.String(length=20),
            nullable=False,
            server_default="clean",
        ),
        sa.Column("supporting_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="runtime"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "voice_fingerprints",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("character_slug", sa.String(length=100), nullable=False),
        sa.Column("signature_line", sa.Text(), nullable=False),
        sa.Column(
            "cadence_profile",
            sa.String(length=60),
            nullable=False,
            server_default="balanced",
        ),
        sa.Column("conflict_tone", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("affection_tone", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("humor_markers", sa.JSON(), nullable=False),
        sa.Column("lexical_markers", sa.JSON(), nullable=False),
        sa.Column("taboo_markers", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("character_slug"),
    )
    op.create_table(
        "guest_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("guest_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("pressure_tags", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("hook", sa.Text(), nullable=False),
        sa.Column("linked_location_slug", sa.String(length=100), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("guest_key"),
    )
    op.create_table(
        "hot_patch_canary_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("changed_files", sa.JSON(), nullable=False),
        sa.Column("checks", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("hot_patch_canary_runs")
    op.drop_table("guest_profiles")
    op.drop_table("voice_fingerprints")
    op.drop_table("chronology_graph_edges")
    op.drop_table("chronology_graph_nodes")
