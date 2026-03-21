# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
"""add true god-ai governance tables and fields

Revision ID: 20260321_0005
Revises: 20260321_0004
Create Date: 2026-03-21 23:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260321_0005"
down_revision = "20260321_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "story_gravity_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("state_key", sa.String(length=50), nullable=False),
        sa.Column("north_star_objective", sa.Text(), nullable=False),
        sa.Column("central_tension", sa.Text(), nullable=False),
        sa.Column("core_tensions", sa.JSON(), nullable=False),
        sa.Column("active_axes", sa.JSON(), nullable=False),
        sa.Column("dormant_threads", sa.JSON(), nullable=False),
        sa.Column("drift_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reentry_priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("clip_priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("fandom_priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("recap_focus", sa.JSON(), nullable=False),
        sa.Column("manager_guardrails", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_key"),
    )
    op.create_table(
        "house_pressures",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("state_key", sa.String(length=50), nullable=False),
        sa.Column("signal_slug", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=150), nullable=False),
        sa.Column("intensity", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommended_move", sa.Text(), nullable=False),
        sa.Column("source_metric", sa.String(length=80), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rollout_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("change_id", sa.String(length=120), nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=True),
        sa.Column("request_type", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("directives", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rollout_beats",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("rollout_request_id", sa.BigInteger(), nullable=True),
        sa.Column("beat_key", sa.String(length=150), nullable=False),
        sa.Column("beat_type", sa.String(length=50), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("significance", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["rollout_request_id"], ["rollout_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("beat_key"),
    )
    op.create_table(
        "simulation_lab_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("turns_per_hour", sa.Integer(), nullable=False),
        sa.Column("winner_key", sa.String(length=100), nullable=True),
        sa.Column("systemic_risks", sa.JSON(), nullable=False),
        sa.Column("recommended_focus", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "strategy_rankings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("simulation_run_id", sa.BigInteger(), nullable=True),
        sa.Column("strategic_brief_id", sa.Integer(), nullable=True),
        sa.Column("strategy_key", sa.String(length=100), nullable=False),
        sa.Column("rank_order", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("rationale", sa.JSON(), nullable=False),
        sa.Column("next_hour_focus", sa.Text(), nullable=False),
        sa.Column("six_hour_path", sa.Text(), nullable=False),
        sa.Column("value_profile", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["simulation_run_id"], ["simulation_lab_runs.id"]),
        sa.ForeignKeyConstraint(["strategic_brief_id"], ["strategic_briefs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "public_turn_reviews",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("speaker_slug", sa.String(length=100), nullable=False),
        sa.Column("review_status", sa.String(length=20), nullable=False),
        sa.Column("critic_score", sa.Integer(), nullable=False),
        sa.Column("repair_applied", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("repair_actions", sa.JSON(), nullable=False),
        sa.Column("quote_worthiness", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("clip_value", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("fandom_discussion_value", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("novelty", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "dormant_thread_registry",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("thread_key", sa.String(length=150), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("heat", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_revived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_key"),
    )
    op.create_table(
        "recap_quality_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("summary_id", sa.BigInteger(), nullable=True),
        sa.Column("summary_window", sa.String(length=20), nullable=False),
        sa.Column("bucket_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usefulness", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("clarity", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("theory_value", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("emotional_readability", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("next_hook_strength", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["summary_id"], ["summaries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "clip_value_scores",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("strategic_brief_id", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("clip_value", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("quote_value", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("betrayal_value", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("romance_intensity", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("mystery_progression", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("novelty", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("daily_uniqueness", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["strategic_brief_id"], ["strategic_briefs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "fandom_signal_candidates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("message_id", sa.BigInteger(), nullable=True),
        sa.Column("strategic_brief_id", sa.Integer(), nullable=True),
        sa.Column("signal_type", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=150), nullable=False),
        sa.Column("intensity", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
        sa.ForeignKeyConstraint(["strategic_brief_id"], ["strategic_briefs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "strategic_briefs",
        sa.Column("current_north_star_objective", sa.Text(), nullable=True),
    )
    op.add_column("strategic_briefs", sa.Column("arc_priority_ranking", sa.JSON(), nullable=True))
    op.add_column(
        "strategic_briefs",
        sa.Column("danger_of_drift_score", sa.Integer(), nullable=True),
    )
    op.add_column("strategic_briefs", sa.Column("cliffhanger_urgency", sa.Integer(), nullable=True))
    op.add_column("strategic_briefs", sa.Column("romance_urgency", sa.Integer(), nullable=True))
    op.add_column("strategic_briefs", sa.Column("mystery_urgency", sa.Integer(), nullable=True))
    op.add_column(
        "strategic_briefs",
        sa.Column("house_pressure_priority", sa.Integer(), nullable=True),
    )
    op.add_column(
        "strategic_briefs",
        sa.Column("audience_rollout_priority", sa.Integer(), nullable=True),
    )
    op.add_column(
        "strategic_briefs",
        sa.Column("dormant_threads_to_revive", sa.JSON(), nullable=True),
    )
    op.add_column("strategic_briefs", sa.Column("reveals_allowed_soon", sa.JSON(), nullable=True))
    op.add_column(
        "strategic_briefs",
        sa.Column("reveals_forbidden_for_now", sa.JSON(), nullable=True),
    )
    op.add_column(
        "strategic_briefs",
        sa.Column("next_one_hour_intention", sa.Text(), nullable=True),
    )
    op.add_column(
        "strategic_briefs",
        sa.Column("next_six_hour_intention", sa.Text(), nullable=True),
    )
    op.add_column(
        "strategic_briefs",
        sa.Column("next_twenty_four_hour_intention", sa.Text(), nullable=True),
    )
    op.add_column("strategic_briefs", sa.Column("recap_priorities", sa.JSON(), nullable=True))
    op.add_column(
        "strategic_briefs",
        sa.Column("fan_theory_potential", sa.Integer(), nullable=True),
    )
    op.add_column(
        "strategic_briefs",
        sa.Column("clip_generation_potential", sa.Integer(), nullable=True),
    )
    op.add_column(
        "strategic_briefs",
        sa.Column("reentry_clarity_priority", sa.Integer(), nullable=True),
    )
    op.add_column("strategic_briefs", sa.Column("quote_worthiness", sa.Integer(), nullable=True))
    op.add_column("strategic_briefs", sa.Column("betrayal_value", sa.Integer(), nullable=True))
    op.add_column("strategic_briefs", sa.Column("daily_uniqueness", sa.Integer(), nullable=True))
    op.add_column(
        "strategic_briefs",
        sa.Column("fandom_discussion_value", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("strategic_briefs", "fandom_discussion_value")
    op.drop_column("strategic_briefs", "daily_uniqueness")
    op.drop_column("strategic_briefs", "betrayal_value")
    op.drop_column("strategic_briefs", "quote_worthiness")
    op.drop_column("strategic_briefs", "reentry_clarity_priority")
    op.drop_column("strategic_briefs", "clip_generation_potential")
    op.drop_column("strategic_briefs", "fan_theory_potential")
    op.drop_column("strategic_briefs", "recap_priorities")
    op.drop_column("strategic_briefs", "next_twenty_four_hour_intention")
    op.drop_column("strategic_briefs", "next_six_hour_intention")
    op.drop_column("strategic_briefs", "next_one_hour_intention")
    op.drop_column("strategic_briefs", "reveals_forbidden_for_now")
    op.drop_column("strategic_briefs", "reveals_allowed_soon")
    op.drop_column("strategic_briefs", "dormant_threads_to_revive")
    op.drop_column("strategic_briefs", "audience_rollout_priority")
    op.drop_column("strategic_briefs", "house_pressure_priority")
    op.drop_column("strategic_briefs", "mystery_urgency")
    op.drop_column("strategic_briefs", "romance_urgency")
    op.drop_column("strategic_briefs", "cliffhanger_urgency")
    op.drop_column("strategic_briefs", "danger_of_drift_score")
    op.drop_column("strategic_briefs", "arc_priority_ranking")
    op.drop_column("strategic_briefs", "current_north_star_objective")
    op.drop_table("fandom_signal_candidates")
    op.drop_table("clip_value_scores")
    op.drop_table("recap_quality_scores")
    op.drop_table("dormant_thread_registry")
    op.drop_table("public_turn_reviews")
    op.drop_table("strategy_rankings")
    op.drop_table("simulation_lab_runs")
    op.drop_table("rollout_beats")
    op.drop_table("rollout_requests")
    op.drop_table("house_pressures")
    op.drop_table("story_gravity_state")
