# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
"""add hourly ledger, canon capsules, highlight packages, and soak audit runs

Revision ID: 20260324_0006
Revises: 20260321_0005
Create Date: 2026-03-24 12:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260324_0006"
down_revision = "20260321_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hourly_progress_ledger",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bucket_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meaningful_progressions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trust_shift_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("desire_shift_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_shift_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("debt_shift_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("power_shift_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("loyalty_shift_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("contract_met", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dominant_axis", sa.String(length=40), nullable=False, server_default="none"),
        sa.Column("blockers", sa.JSON(), nullable=False),
        sa.Column("recommended_push", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bucket_start_at", name="uq_hourly_progress_bucket"),
    )
    op.create_table(
        "canon_capsules",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("window_key", sa.String(length=20), nullable=False),
        sa.Column("headline", sa.String(length=220), nullable=False, server_default=""),
        sa.Column("state_of_play", sa.JSON(), nullable=False),
        sa.Column("key_clues", sa.JSON(), nullable=False),
        sa.Column("relationship_fault_lines", sa.JSON(), nullable=False),
        sa.Column("active_pressures", sa.JSON(), nullable=False),
        sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("protected_truths", sa.JSON(), nullable=False),
        sa.Column("recap_hooks", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("window_key", name="uq_canon_capsule_window"),
    )
    op.create_table(
        "highlight_packages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("speaker_slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("alternate_titles", sa.JSON(), nullable=False),
        sa.Column("hook_line", sa.Text(), nullable=False),
        sa.Column("quote_line", sa.Text(), nullable=False),
        sa.Column("summary_blurb", sa.Text(), nullable=False),
        sa.Column("ship_angle", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("theory_angle", sa.String(length=160), nullable=False, server_default=""),
        sa.Column("conflict_axis", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("recommended_clip_seconds", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("source_window_minutes", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "soak_audit_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("horizons_hours", sa.JSON(), nullable=False),
        sa.Column("progression_miss_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drift_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strategy_lock_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recap_decay_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clip_drought_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ship_stagnation_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unresolved_overload_risk", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recommended_direction", sa.Text(), nullable=False),
        sa.Column("audit_notes", sa.JSON(), nullable=False),
        sa.Column("candidate_pressure", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("soak_audit_runs")
    op.drop_table("highlight_packages")
    op.drop_table("canon_capsules")
    op.drop_table("hourly_progress_ledger")
