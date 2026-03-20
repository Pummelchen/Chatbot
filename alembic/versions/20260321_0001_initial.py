"""initial schema

Revision ID: 20260321_0001
Revises:
Create Date: 2026-03-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260321_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("active_scene_key", sa.String(length=100), nullable=False),
        sa.Column("current_story_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("emotional_temperature", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("reveal_pressure", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("archived_threads", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("public_facts", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "canon_facts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fact_key", sa.String(length=150), nullable=False),
        sa.Column("fact_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("fact_key"),
    )

    op.create_table(
        "characters",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=False),
        sa.Column("public_persona", sa.Text(), nullable=False),
        sa.Column("hidden_wound", sa.Text(), nullable=False),
        sa.Column("long_term_desire", sa.Text(), nullable=False),
        sa.Column("private_fear", sa.Text(), nullable=False),
        sa.Column("message_style", sa.Text(), nullable=False),
        sa.Column("ensemble_role", sa.String(length=120), nullable=False),
        sa.Column("secrets_summary", sa.Text(), nullable=False),
        sa.Column("humor_style", sa.Text(), nullable=False),
        sa.Column("color", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "story_arcs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("arc_type", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("stage_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reveal_ladder", sa.JSON(), nullable=False),
        sa.Column("unresolved_questions", sa.JSON(), nullable=False),
        sa.Column("payoff_window", sa.String(length=100), nullable=False),
        sa.Column("pressure_score", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "run_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("runtime_key", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="idle"),
        sa.Column("last_tick_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_public_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_manager_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_recap_hour", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_thought_pulse_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("degraded_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("runtime_key"),
    )

    op.create_table(
        "scene_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scene_key", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("emotional_temperature", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("mystery_pressure", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("romance_pressure", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("comedic_pressure", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("active_character_slugs", sa.JSON(), nullable=False),
        sa.Column("current_hour_bucket", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("scene_key"),
    )

    op.create_table(
        "character_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column(
            "current_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True
        ),
        sa.Column("emotional_state", sa.JSON(), nullable=False),
        sa.Column("active_goals", sa.JSON(), nullable=False),
        sa.Column("stress_level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("romance_heat", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("knowledge_flags", sa.JSON(), nullable=False),
        sa.Column("last_spoke_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("silence_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("character_id"),
    )

    op.create_table(
        "story_objects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("significance", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "relationships",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("character_a_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("character_b_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("trust_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("desire_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suspicion_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("obligation_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("last_shift_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("character_a_id", "character_b_id", name="uq_relationship_pair"),
    )

    op.create_table(
        "secrets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "holder_character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=True
        ),
        sa.Column("secret_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("exposure_stage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reveal_guardrail", sa.Text(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "beats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scene_state.id"), nullable=False),
        sa.Column("beat_type", sa.String(length=50), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="planned"),
        sa.Column("significance", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("due_by", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "manager_directives",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scene_state.id"), nullable=True),
        sa.Column("tick_no", sa.Integer(), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("desired_developments", sa.JSON(), nullable=False),
        sa.Column("reveal_budget", sa.Integer(), nullable=False),
        sa.Column("emotional_temperature", sa.Integer(), nullable=False),
        sa.Column("active_character_slugs", sa.JSON(), nullable=False),
        sa.Column("speaker_weights", sa.JSON(), nullable=False),
        sa.Column("per_character", sa.JSON(), nullable=False),
        sa.Column("thought_pulse", sa.JSON(), nullable=False),
        sa.Column("pacing_actions", sa.JSON(), nullable=False),
        sa.Column("continuity_watch", sa.JSON(), nullable=False),
        sa.Column("unresolved_questions_to_push", sa.JSON(), nullable=False),
        sa.Column("recentering_hint", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tick_no", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scene_state.id"), nullable=True),
        sa.Column(
            "speaker_character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=True
        ),
        sa.Column("speaker_slug", sa.String(length=100), nullable=True),
        sa.Column("speaker_label", sa.String(length=150), nullable=False),
        sa.Column("message_kind", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("hidden_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )

    op.create_table(
        "thought_pulses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("tick_no", sa.Integer(), nullable=False),
        sa.Column("character_id", sa.Integer(), sa.ForeignKey("characters.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "source_directive_id",
            sa.Integer(),
            sa.ForeignKey("manager_directives.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "extracted_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "source_message_id", sa.BigInteger(), sa.ForeignKey("messages.id"), nullable=True
        ),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("significance", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("affects_arc_slug", sa.String(length=120), nullable=True),
        sa.Column("affects_relationships", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "summaries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("summary_window", sa.String(length=20), nullable=False),
        sa.Column("bucket_end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_highlights", sa.JSON(), nullable=False),
        sa.Column("generated_by", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("summary_window", "bucket_end_at", name="uq_summary_window_bucket"),
    )

    op.create_table(
        "continuity_flags",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("flag_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("related_entity", sa.String(length=150), nullable=True),
        sa.Column(
            "related_message_id", sa.BigInteger(), sa.ForeignKey("messages.id"), nullable=True
        ),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("continuity_flags")
    op.drop_table("summaries")
    op.drop_table("extracted_events")
    op.drop_table("thought_pulses")
    op.drop_table("messages")
    op.drop_table("manager_directives")
    op.drop_table("beats")
    op.drop_table("secrets")
    op.drop_table("relationships")
    op.drop_table("story_objects")
    op.drop_table("character_state")
    op.drop_table("scene_state")
    op.drop_table("run_state")
    op.drop_table("story_arcs")
    op.drop_table("characters")
    op.drop_table("canon_facts")
    op.drop_table("locations")
    op.drop_table("world_state")
