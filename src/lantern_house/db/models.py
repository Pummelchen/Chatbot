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
    viewer_value_thesis: Mapped[str] = mapped_column(Text, nullable=False)
    urgency: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_hour_focus: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    next_six_hours: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
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

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    summary_window: Mapped[str] = mapped_column(String(20), nullable=False)
    bucket_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_highlights: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_by: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
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
