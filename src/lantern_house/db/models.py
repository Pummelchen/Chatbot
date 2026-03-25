# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from lantern_house.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorldState(Base):
    __tablename__ = "world_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    active_scene_key: Mapped[str] = mapped_column(String(100), nullable=False)
    current_story_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    emotional_temperature: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    reveal_pressure: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unresolved_questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    archived_threads: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class HouseState(Base):
    __tablename__ = "house_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_key: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, default="primary"
    )
    capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    occupied_rooms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    vacancy_pressure: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cash_on_hand: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hourly_burn_rate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payroll_due_in_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    repair_backlog: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inspection_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    guest_tension: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weather_pressure: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    staff_fatigue: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reputation_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    active_pressures: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class StoryGravityState(Base):
    __tablename__ = "story_gravity_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_key: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, default="primary"
    )
    north_star_objective: Mapped[str] = mapped_column(Text, nullable=False)
    central_tension: Mapped[str] = mapped_column(Text, nullable=False)
    core_tensions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    active_axes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    dormant_threads: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    drift_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reentry_priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    clip_priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    fandom_priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    recap_focus: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    manager_guardrails: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    public_facts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class StoryObject(Base):
    __tablename__ = "story_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    state_json: Mapped[dict] = mapped_column("state", JSON, default=dict, nullable=False)
    significance: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class TimelineFact(Base):
    __tablename__ = "timeline_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_slug: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    related_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    object_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    object_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="runtime")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ObjectPossession(Base):
    __tablename__ = "object_possessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    object_name: Mapped[str] = mapped_column(String(150), nullable=False)
    holder_character_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location_name: Mapped[str] = mapped_column(String(150), nullable=False, default="")
    possession_status: Mapped[str] = mapped_column(String(30), nullable=False, default="room")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class CanonFact(Base):
    __tablename__ = "canon_facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fact_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    fact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    cultural_background: Mapped[str] = mapped_column(String(120), nullable=False)
    public_persona: Mapped[str] = mapped_column(Text, nullable=False)
    hidden_wound: Mapped[str] = mapped_column(Text, nullable=False)
    long_term_desire: Mapped[str] = mapped_column(Text, nullable=False)
    private_fear: Mapped[str] = mapped_column(Text, nullable=False)
    family_expectations: Mapped[str] = mapped_column(Text, nullable=False)
    conflict_style: Mapped[str] = mapped_column(Text, nullable=False)
    privacy_boundaries: Mapped[str] = mapped_column(Text, nullable=False)
    value_instincts: Mapped[str] = mapped_column(Text, nullable=False)
    emotional_expression: Mapped[str] = mapped_column(Text, nullable=False)
    message_style: Mapped[str] = mapped_column(Text, nullable=False)
    ensemble_role: Mapped[str] = mapped_column(String(120), nullable=False)
    secrets_summary: Mapped[str] = mapped_column(Text, nullable=False)
    humor_style: Mapped[str] = mapped_column(Text, nullable=False)
    color: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class CharacterState(Base):
    __tablename__ = "character_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id"), unique=True, nullable=False
    )
    current_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id"), nullable=True
    )
    emotional_state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    active_goals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    stress_level: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    romance_heat: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    knowledge_flags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    last_spoke_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    silence_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("character_a_id", "character_b_id", name="uq_relationship_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_a_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), nullable=False)
    character_b_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), nullable=False)
    trust_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    desire_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    suspicion_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    obligation_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    last_shift_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Secret(Base):
    __tablename__ = "secrets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    holder_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    secret_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    exposure_stage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reveal_guardrail: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class StoryArc(Base):
    __tablename__ = "story_arcs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    arc_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    stage_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reveal_ladder: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    unresolved_questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    payoff_window: Mapped[str] = mapped_column(String(100), nullable=False)
    pressure_score: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class SceneState(Base):
    __tablename__ = "scene_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    emotional_temperature: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    mystery_pressure: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    romance_pressure: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    comedic_pressure: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.id"), nullable=True)
    active_character_slugs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    current_hour_bucket: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)


class Beat(Base):
    __tablename__ = "beats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scene_state.id"), nullable=False)
    beat_type: Mapped[str] = mapped_column(String(50), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    significance: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    due_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StrategicBrief(Base):
    __tablename__ = "strategic_briefs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    model_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    current_north_star_objective: Mapped[str] = mapped_column(Text, nullable=False)
    viewer_value_thesis: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    arc_priority_ranking: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    danger_of_drift_score: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    cliffhanger_urgency: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    romance_urgency: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    mystery_urgency: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    house_pressure_priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    audience_rollout_priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    dormant_threads_to_revive: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reveals_allowed_soon: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reveals_forbidden_for_now: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    next_one_hour_intention: Mapped[str] = mapped_column(Text, nullable=False)
    next_six_hour_intention: Mapped[str] = mapped_column(Text, nullable=False)
    next_twenty_four_hour_intention: Mapped[str] = mapped_column(Text, nullable=False)
    next_hour_focus: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    next_six_hours: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recap_priorities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    fan_theory_potential: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    clip_generation_potential: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    reentry_clarity_priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    quote_worthiness: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    betrayal_value: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    daily_uniqueness: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    fandom_discussion_value: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    recommendations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    risk_alerts: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    house_pressure_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    audience_rollout_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    manager_biases: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    simulation_ranking: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class HousePressure(Base):
    __tablename__ = "house_pressures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_key: Mapped[str] = mapped_column(String(50), nullable=False, default="primary")
    signal_slug: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    intensity: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_move: Mapped[str] = mapped_column(Text, nullable=False)
    source_metric: Mapped[str] = mapped_column(String(80), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ManagerDirective(Base):
    __tablename__ = "manager_directives"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scene_state.id"), nullable=True)
    tick_no: Mapped[int] = mapped_column(Integer, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    desired_developments: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    reveal_budget: Mapped[int] = mapped_column(Integer, nullable=False)
    emotional_temperature: Mapped[int] = mapped_column(Integer, nullable=False)
    active_character_slugs: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    speaker_weights: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    per_character: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    thought_pulse: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    pacing_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    continuity_watch: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    unresolved_questions_to_push: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recentering_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick_no: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scene_state.id"), nullable=True)
    speaker_character_id: Mapped[int | None] = mapped_column(
        ForeignKey("characters.id"), nullable=True
    )
    speaker_slug: Mapped[str | None] = mapped_column(String(100), nullable=True)
    speaker_label: Mapped[str] = mapped_column(String(150), nullable=False)
    message_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    hidden_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ThoughtPulse(Base):
    __tablename__ = "thought_pulses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tick_no: Mapped[int] = mapped_column(Integer, nullable=False)
    character_id: Mapped[int] = mapped_column(ForeignKey("characters.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_directive_id: Mapped[int | None] = mapped_column(
        ForeignKey("manager_directives.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ExtractedEvent(Base):
    __tablename__ = "extracted_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    significance: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    affects_arc_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    affects_relationships: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Summary(Base):
    __tablename__ = "summaries"
    __table_args__ = (
        UniqueConstraint("summary_window", "bucket_end_at", name="uq_summary_window_bucket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    summary_window: Mapped[str] = mapped_column(String(20), nullable=False)
    bucket_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_highlights: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RolloutRequest(Base):
    __tablename__ = "rollout_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    change_id: Mapped[str] = mapped_column(String(120), nullable=False)
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    directives: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RolloutBeat(Base):
    __tablename__ = "rollout_beats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rollout_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("rollout_requests.id"), nullable=True
    )
    beat_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    beat_type: Mapped[str] = mapped_column(String(50), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    significance: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SimulationLabRun(Base):
    __tablename__ = "simulation_lab_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="god-ai")
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    turns_per_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    winner_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    systemic_risks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recommended_focus: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class StrategyRanking(Base):
    __tablename__ = "strategy_rankings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    simulation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("simulation_lab_runs.id"), nullable=True
    )
    strategic_brief_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategic_briefs.id"), nullable=True
    )
    strategy_key: Mapped[str] = mapped_column(String(100), nullable=False)
    rank_order: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    next_hour_focus: Mapped[str] = mapped_column(Text, nullable=False)
    six_hour_path: Mapped[str] = mapped_column(Text, nullable=False)
    value_profile: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class HourlyProgressLedger(Base):
    __tablename__ = "hourly_progress_ledger"
    __table_args__ = (UniqueConstraint("bucket_start_at", name="uq_hourly_progress_bucket"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    meaningful_progressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trust_shift_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    desire_shift_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_shift_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    debt_shift_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    power_shift_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    loyalty_shift_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contract_met: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dominant_axis: Mapped[str] = mapped_column(String(40), default="none", nullable=False)
    blockers: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recommended_push: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ProgrammingGridSlot(Base):
    __tablename__ = "programming_grid_slots"
    __table_args__ = (
        UniqueConstraint(
            "horizon",
            "slot_key",
            "window_start_at",
            name="uq_programming_grid_slot_window",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horizon: Mapped[str] = mapped_column(String(20), nullable=False)
    slot_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    target_axis: Mapped[str] = mapped_column(String(40), nullable=False, default="mixed")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="planned")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    notes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    window_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class PublicTurnReview(Base):
    __tablename__ = "public_turn_reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    speaker_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, default="accepted")
    critic_score: Mapped[int] = mapped_column(Integer, nullable=False)
    repair_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    repair_actions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    quote_worthiness: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    clip_value: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    fandom_discussion_value: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    novelty: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CanonCourtFinding(Base):
    __tablename__ = "canon_court_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="warning")
    action: Mapped[str] = mapped_column(String(30), nullable=False, default="allow")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class CanonCapsule(Base):
    __tablename__ = "canon_capsules"
    __table_args__ = (UniqueConstraint("window_key", name="uq_canon_capsule_window"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    window_key: Mapped[str] = mapped_column(String(20), nullable=False)
    headline: Mapped[str] = mapped_column(String(220), nullable=False, default="")
    state_of_play: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    key_clues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    relationship_fault_lines: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    active_pressures: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    unresolved_questions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    protected_truths: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recap_hooks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ContinuityFlag(Base):
    __tablename__ = "continuity_flags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    flag_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    related_entity: Mapped[str | None] = mapped_column(String(150), nullable=True)
    related_message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HighlightPackage(Base):
    __tablename__ = "highlight_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    speaker_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    alternate_titles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    hook_line: Mapped[str] = mapped_column(Text, nullable=False)
    quote_line: Mapped[str] = mapped_column(Text, nullable=False)
    summary_blurb: Mapped[str] = mapped_column(Text, nullable=False)
    ship_angle: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    theory_angle: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    conflict_axis: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    recommended_clip_seconds: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    source_window_minutes: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class MonetizationPackage(Base):
    __tablename__ = "monetization_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    highlight_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True
    )
    speaker_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    primary_title: Mapped[str] = mapped_column(String(220), nullable=False)
    alternate_titles: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    short_title_options: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    hook_line: Mapped[str] = mapped_column(Text, nullable=False)
    quote_line: Mapped[str] = mapped_column(Text, nullable=False)
    summary_blurb: Mapped[str] = mapped_column(Text, nullable=False)
    recap_blurb: Mapped[str] = mapped_column(Text, nullable=False)
    chapter_label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    comment_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ship_angle: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    theory_angle: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    betrayal_angle: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    faction_labels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    recommended_clip_start_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    recommended_clip_end_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=25
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class BroadcastAssetPackage(Base):
    __tablename__ = "broadcast_asset_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    monetization_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True
    )
    speaker_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_title: Mapped[str] = mapped_column(String(220), nullable=False)
    hook_line: Mapped[str] = mapped_column(Text, nullable=False)
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    long_description: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    chapter_markers: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    clip_manifest: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    ship_labels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    theory_labels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    faction_labels: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    comment_seed: Mapped[str] = mapped_column(Text, nullable=False)
    asset_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class DormantThreadRegistry(Base):
    __tablename__ = "dormant_thread_registry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="world-memory")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="dormant")
    heat: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_revived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class RecapQualityScore(Base):
    __tablename__ = "recap_quality_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    summary_id: Mapped[int | None] = mapped_column(ForeignKey("summaries.id"), nullable=True)
    summary_window: Mapped[str] = mapped_column(String(20), nullable=False)
    bucket_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usefulness: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    clarity: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    theory_value: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    emotional_readability: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_hook_strength: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    issues: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ClipValueScore(Base):
    __tablename__ = "clip_value_scores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    strategic_brief_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategic_briefs.id"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    clip_value: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    quote_value: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    betrayal_value: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    romance_intensity: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    mystery_progression: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    novelty: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    daily_uniqueness: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class FandomSignalCandidate(Base):
    __tablename__ = "fandom_signal_candidates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"), nullable=True)
    strategic_brief_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategic_briefs.id"), nullable=True
    )
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(150), nullable=False)
    intensity: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ViewerSignal(Base):
    __tablename__ = "viewer_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    signal_key: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(180), nullable=False)
    intensity: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    sentiment: Mapped[str] = mapped_column(String(30), nullable=False, default="mixed")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="operator")
    retention_impact: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class SoakAuditRun(Base):
    __tablename__ = "soak_audit_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    horizons_hours: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    progression_miss_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    drift_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    strategy_lock_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recap_decay_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clip_drought_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ship_stagnation_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unresolved_overload_risk: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommended_direction: Mapped[str] = mapped_column(Text, nullable=False)
    audit_notes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    candidate_pressure: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class OpsTelemetry(Base):
    __tablename__ = "ops_telemetry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    runtime_status: Mapped[str] = mapped_column(String(20), nullable=False)
    phase: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    degraded_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    load_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    average_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checkpoint_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recap_age_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strategy_age_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drift_risk: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progression_contract_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    restart_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_strategy: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    auto_remediations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class RunState(Base):
    __tablename__ = "run_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    runtime_key: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, default="primary"
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")
    last_tick_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_checkpoint_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_public_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_manager_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_recap_hour: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_thought_pulse_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    degraded_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
