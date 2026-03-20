from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from lantern_house.domain.enums import EventType, FlagSeverity


class CharacterGoal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    goal: str
    pressure_point: str
    taboo_topics: list[str] = Field(default_factory=list)
    desired_partner: str | None = None


class ThoughtPulseAuthorization(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowed: bool = False
    character_slug: str | None = None
    reason: str | None = None


class ManagerDirectivePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    objective: str
    desired_developments: list[str] = Field(default_factory=list)
    reveal_budget: int = Field(default=1, ge=0, le=3)
    emotional_temperature: int = Field(default=5, ge=1, le=10)
    active_character_slugs: list[str] = Field(default_factory=list)
    speaker_weights: dict[str, float] = Field(default_factory=dict)
    per_character: dict[str, CharacterGoal] = Field(default_factory=dict)
    thought_pulse: ThoughtPulseAuthorization = Field(default_factory=ThoughtPulseAuthorization)
    pacing_actions: list[str] = Field(default_factory=list)
    continuity_watch: list[str] = Field(default_factory=list)
    unresolved_questions_to_push: list[str] = Field(default_factory=list)
    recentering_hint: str | None = None


class RelationshipUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    character_slug: str
    trust_delta: int = Field(default=0, ge=-3, le=3)
    desire_delta: int = Field(default=0, ge=-3, le=3)
    suspicion_delta: int = Field(default=0, ge=-3, le=3)
    obligation_delta: int = Field(default=0, ge=-3, le=3)
    summary: str


class EventCandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_type: EventType
    title: str
    details: str
    significance: int = Field(default=5, ge=1, le=10)
    arc_slug: str | None = None
    tags: list[str] = Field(default_factory=list)


class CharacterTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    public_message: str
    thought_pulse: str | None = None
    event_candidates: list[EventCandidate] = Field(default_factory=list)
    relationship_updates: list[RelationshipUpdate] = Field(default_factory=list)
    new_questions: list[str] = Field(default_factory=list)
    answered_questions: list[str] = Field(default_factory=list)
    tone: str | None = None
    silence: bool = False


class RecapWindowSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    headline: str
    what_changed: list[str] = Field(default_factory=list)
    emotional_shifts: list[str] = Field(default_factory=list)
    clues: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    loyalty_status: str
    romance_status: str
    watch_next: str


class RecapBundle(BaseModel):
    model_config = ConfigDict(extra="ignore")

    one_hour: RecapWindowSummary
    twelve_hours: RecapWindowSummary
    twenty_four_hours: RecapWindowSummary


class MessageView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    speaker_label: str
    content: str
    kind: str
    created_at: datetime


class EventView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_type: str
    title: str
    details: str
    significance: int
    payload: dict = Field(default_factory=dict)
    created_at: datetime


class SummaryView(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary_window: str
    content: str
    structured_highlights: dict = Field(default_factory=dict)
    bucket_end_at: datetime


class RelationshipSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    counterpart_slug: str
    trust_score: int
    desire_score: int
    suspicion_score: int
    obligation_score: int
    summary: str


class StoryArcSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str
    title: str
    status: str = "active"
    arc_type: str = "mystery"
    summary: str
    stage_index: int
    unresolved_questions: list[str] = Field(default_factory=list)
    reveal_ladder: list[str] = Field(default_factory=list)
    payoff_window: str = "weeks"
    pressure_score: int
    metadata: dict = Field(default_factory=dict)


class StoryArcProgressUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str
    stage_index: int
    pressure_score: int
    metadata: dict = Field(default_factory=dict)
    surfaced_questions: list[str] = Field(default_factory=list)
    archived_threads: list[str] = Field(default_factory=list)


class StoryProgressionPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    arc_updates: list[StoryArcProgressUpdate] = Field(default_factory=list)
    surfaced_questions: list[str] = Field(default_factory=list)
    archived_threads: list[str] = Field(default_factory=list)


class PacingHealthReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: int = Field(ge=0, le=100)
    repetitive: bool = False
    mystery_stalled: bool = False
    romance_stalled: bool = False
    low_progression: bool = False
    too_agreeable: bool = False
    recommendations: list[str] = Field(default_factory=list)


class StoryGovernanceReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    viewer_value_score: int = Field(default=100, ge=0, le=100)
    hourly_progression_met: bool = True
    meaningful_progressions_last_hour: int = 0
    core_drift: bool = False
    robotic_voice_risk: bool = False
    cliffhanger_pressure_low: bool = False
    active_gravity_axes: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ContinuityFlagDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    severity: FlagSeverity
    flag_type: str
    description: str
    related_entity: str | None = None


class ManagerContextPacket(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    scene_objective: str
    scene_location: str
    emotional_temperature: int
    story_gravity: list[str] = Field(default_factory=list)
    viewer_value_targets: list[str] = Field(default_factory=list)
    voice_guardrails: list[str] = Field(default_factory=list)
    cast_guidance: list[str] = Field(default_factory=list)
    current_arc_summaries: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    payoff_threads: list[str] = Field(default_factory=list)
    relationship_map: list[str] = Field(default_factory=list)
    recent_summaries: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    recent_messages: list[str] = Field(default_factory=list)
    continuity_warnings: list[str] = Field(default_factory=list)
    pacing_health: PacingHealthReport
    story_governance: StoryGovernanceReport = Field(default_factory=StoryGovernanceReport)


class CharacterContextPacket(BaseModel):
    model_config = ConfigDict(extra="ignore")

    character_slug: str
    full_name: str
    cultural_background: str
    public_persona: str
    hidden_wound: str
    long_term_desire: str
    private_fear: str
    family_expectations: str
    conflict_style: str
    privacy_boundaries: str
    value_instincts: str
    emotional_expression: str
    message_style: str
    ensemble_role: str
    current_location: str
    voice_guardrails: list[str] = Field(default_factory=list)
    emotional_state: dict = Field(default_factory=dict)
    current_goals: list[str] = Field(default_factory=list)
    relationship_snapshots: list[str] = Field(default_factory=list)
    recent_messages: list[str] = Field(default_factory=list)
    relevant_facts: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    manager_directive: str
    forbidden_boundaries: list[str] = Field(default_factory=list)
