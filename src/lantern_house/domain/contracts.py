# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
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
    trust_progression_last_hour: int = 0
    desire_progression_last_hour: int = 0
    evidence_progression_last_hour: int = 0
    debt_pressure_progression_last_hour: int = 0
    power_progression_last_hour: int = 0
    loyalty_progression_last_hour: int = 0
    core_drift: bool = False
    robotic_voice_risk: bool = False
    cliffhanger_pressure_low: bool = False
    repeated_dialogue_patterns: bool = False
    collapsing_distinctiveness: bool = False
    mystery_flattened: bool = False
    romance_flattened: bool = False
    recap_weakness: bool = False
    unresolved_thread_overload: bool = False
    clip_value_score: int = Field(default=50, ge=0, le=100)
    reentry_value_score: int = Field(default=50, ge=0, le=100)
    fandom_discussion_value: int = Field(default=50, ge=0, le=100)
    daily_uniqueness_score: int = Field(default=50, ge=0, le=100)
    active_gravity_axes: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class AudienceControlReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active: bool = False
    file_status: str = "missing"
    change_id: str | None = None
    source: str | None = None
    fingerprint: str | None = None
    priority: int = Field(default=5, ge=1, le=10)
    activated_at: str | None = None
    last_checked_at: str | None = None
    full_integration_hours: int = Field(default=24, ge=1, le=168)
    rollout_stage: str = "inactive"
    tone_dials: dict[str, int] = Field(default_factory=dict)
    requests: list[str] = Field(default_factory=list)
    directives: list[str] = Field(default_factory=list)
    beat_hints: list[BeatPlanItem] = Field(default_factory=list)
    parse_error: str | None = None


class HousePressureSignal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    slug: str = "unspecified-pressure"
    label: str = "Unspecified pressure"
    intensity: int = Field(default=5, ge=1, le=10)
    summary: str = ""
    recommended_move: str = ""
    source_metric: str = "unknown"


class HouseStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state_key: str = "primary"
    capacity: int = 0
    occupied_rooms: int = 0
    vacancy_pressure: int = Field(default=0, ge=0, le=10)
    cash_on_hand: int = 0
    hourly_burn_rate: int = 0
    payroll_due_in_hours: int = 0
    repair_backlog: int = Field(default=0, ge=0, le=10)
    inspection_risk: int = Field(default=0, ge=0, le=10)
    guest_tension: int = Field(default=0, ge=0, le=10)
    weather_pressure: int = Field(default=0, ge=0, le=10)
    staff_fatigue: int = Field(default=0, ge=0, le=10)
    reputation_risk: int = Field(default=0, ge=0, le=10)
    active_pressures: list[HousePressureSignal] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    updated_at: datetime | None = None


class DormantThreadSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    thread_key: str
    summary: str
    source: str = "world-memory"
    status: str = "dormant"
    heat: int = Field(default=5, ge=0, le=10)
    last_seen_at: datetime | None = None
    last_revived_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class StoryGravityStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    state_key: str = "primary"
    north_star_objective: str = ""
    central_tension: str = ""
    core_tensions: list[str] = Field(default_factory=list)
    active_axes: list[str] = Field(default_factory=list)
    dormant_threads: list[DormantThreadSnapshot] = Field(default_factory=list)
    drift_score: int = Field(default=0, ge=0, le=100)
    reentry_priority: int = Field(default=5, ge=1, le=10)
    clip_priority: int = Field(default=5, ge=1, le=10)
    fandom_priority: int = Field(default=5, ge=1, le=10)
    recap_focus: list[str] = Field(default_factory=list)
    manager_guardrails: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    updated_at: datetime | None = None


class BeatPlanItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    beat_key: str
    beat_type: str
    objective: str
    significance: int = Field(default=5, ge=1, le=10)
    ready_at: str | None = None
    keywords: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class BeatSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    beat_key: str | None = None
    beat_type: str
    objective: str
    status: str = "planned"
    significance: int = Field(default=5, ge=1, le=10)
    due_by: datetime | None = None
    metadata: dict = Field(default_factory=dict)


class SimulationCandidateScore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    strategy_key: str
    score: int = Field(default=50, ge=0, le=100)
    value_profile: dict[str, int] = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)
    next_hour_focus: str
    six_hour_path: str


class SimulationLabReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: int | None = None
    generated_at: datetime | None = None
    horizon_hours: int = Field(default=24, ge=1, le=168)
    turns_per_hour: int = Field(default=90, ge=1, le=360)
    candidates: list[SimulationCandidateScore] = Field(default_factory=list)
    systemic_risks: list[str] = Field(default_factory=list)
    recommended_focus: list[str] = Field(default_factory=list)
    ranked_strategy_keys: list[str] = Field(default_factory=list)


class HourlyProgressLedgerSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bucket_start_at: datetime | None = None
    bucket_end_at: datetime | None = None
    meaningful_progressions: int = Field(default=0, ge=0)
    trust_shift_count: int = Field(default=0, ge=0)
    desire_shift_count: int = Field(default=0, ge=0)
    evidence_shift_count: int = Field(default=0, ge=0)
    debt_shift_count: int = Field(default=0, ge=0)
    power_shift_count: int = Field(default=0, ge=0)
    loyalty_shift_count: int = Field(default=0, ge=0)
    contract_met: bool = False
    dominant_axis: str = "none"
    blockers: list[str] = Field(default_factory=list)
    recommended_push: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ProgrammingGridSlotSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    horizon: str
    slot_key: str
    label: str
    objective: str
    target_axis: str
    status: str = "planned"
    priority: int = Field(default=5, ge=1, le=10)
    notes: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    window_start_at: datetime | None = None
    window_end_at: datetime | None = None
    updated_at: datetime | None = None


class CanonCapsuleSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    window_key: str
    headline: str = ""
    state_of_play: list[str] = Field(default_factory=list)
    key_clues: list[str] = Field(default_factory=list)
    relationship_fault_lines: list[str] = Field(default_factory=list)
    active_pressures: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    protected_truths: list[str] = Field(default_factory=list)
    recap_hooks: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class CanonCourtFindingSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    issue_type: str
    severity: str = "warning"
    action: str = "allow"
    summary: str
    evidence: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    message_id: int | None = None
    created_at: datetime | None = None


class CanonCourtReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = "clean"
    findings: list[CanonCourtFindingSnapshot] = Field(default_factory=list)
    additional_flags: list[ContinuityFlagDraft] = Field(default_factory=list)
    revised_turn: CharacterTurn | None = None
    revised_events: list[EventCandidate] = Field(default_factory=list)
    revised_questions: list[str] = Field(default_factory=list)
    requires_repair: bool = False


class TimelineFactSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fact_type: str
    subject_slug: str = ""
    related_slug: str | None = None
    location_slug: str | None = None
    location_name: str = ""
    object_slug: str | None = None
    object_name: str = ""
    summary: str
    confidence: int = Field(default=5, ge=1, le=10)
    source: str = "runtime"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class ObjectPossessionSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    object_slug: str
    object_name: str = ""
    holder_character_slug: str | None = None
    location_slug: str | None = None
    location_name: str = ""
    possession_status: str = "room"
    summary: str
    confidence: int = Field(default=5, ge=1, le=10)
    metadata: dict = Field(default_factory=dict)
    last_seen_at: datetime | None = None
    created_at: datetime | None = None


class ChronologyNodeSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_key: str
    node_type: str
    label: str
    status: str = "active"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ChronologyEdgeSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject_key: str
    predicate: str
    object_key: str
    confidence: int = Field(default=5, ge=1, le=10)
    contradiction_status: str = "clean"
    supporting_text: str = ""
    source: str = "runtime"
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ViewerSignalSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    signal_key: str
    signal_type: str
    subject: str
    intensity: int = Field(default=5, ge=1, le=10)
    sentiment: str = "mixed"
    summary: str
    source: str = "operator"
    retention_impact: int = Field(default=5, ge=1, le=10)
    metadata: dict = Field(default_factory=dict)
    expires_at: datetime | None = None
    created_at: datetime | None = None


class VoiceFingerprintSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    character_slug: str
    signature_line: str
    cadence_profile: str = "balanced"
    conflict_tone: str = ""
    affection_tone: str = ""
    humor_markers: list[str] = Field(default_factory=list)
    lexical_markers: list[str] = Field(default_factory=list)
    taboo_markers: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    updated_at: datetime | None = None


class HighlightPackageSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: int | None = None
    speaker_slug: str = ""
    title: str
    alternate_titles: list[str] = Field(default_factory=list)
    hook_line: str = ""
    quote_line: str = ""
    summary_blurb: str = ""
    ship_angle: str = ""
    theory_angle: str = ""
    conflict_axis: str = ""
    recommended_clip_seconds: int = Field(default=25, ge=5, le=120)
    source_window_minutes: int = Field(default=4, ge=1, le=60)
    score: int = Field(default=0, ge=0, le=100)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class MonetizationPackageSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: int | None = None
    highlight_message_id: int | None = None
    speaker_slug: str = ""
    primary_title: str
    alternate_titles: list[str] = Field(default_factory=list)
    short_title_options: list[str] = Field(default_factory=list)
    hook_line: str = ""
    quote_line: str = ""
    summary_blurb: str = ""
    recap_blurb: str = ""
    chapter_label: str = ""
    comment_prompt: str = ""
    ship_angle: str = ""
    theory_angle: str = ""
    betrayal_angle: str = ""
    faction_labels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    recommended_clip_start_seconds: int = Field(default=0, ge=0, le=300)
    recommended_clip_end_seconds: int = Field(default=25, ge=5, le=300)
    score: int = Field(default=0, ge=0, le=100)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class BroadcastAssetSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message_id: int | None = None
    monetization_message_id: int | None = None
    speaker_slug: str = ""
    asset_title: str
    hook_line: str = ""
    short_description: str = ""
    long_description: list[str] = Field(default_factory=list)
    chapter_markers: list[str] = Field(default_factory=list)
    clip_manifest: list[dict] = Field(default_factory=list)
    ship_labels: list[str] = Field(default_factory=list)
    theory_labels: list[str] = Field(default_factory=list)
    faction_labels: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    why_it_matters: str = ""
    comment_seed: str = ""
    asset_score: int = Field(default=0, ge=0, le=100)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class GuestProfileSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    guest_key: str
    display_name: str
    role: str
    status: str = "active"
    pressure_tags: list[str] = Field(default_factory=list)
    summary: str
    hook: str
    linked_location_slug: str | None = None
    metadata: dict = Field(default_factory=dict)
    updated_at: datetime | None = None


class HotPatchCanaryRunSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str
    changed_files: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    error_summary: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class LoadProfileSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    load_tier: str = "low"
    average_latency_ms: int = Field(default=0, ge=0)
    p95_latency_ms: int = Field(default=0, ge=0)
    recent_failures: int = Field(default=0, ge=0)
    degraded_mode: bool = False
    pending_manager_prefetch: bool = False
    background_pressure: int = Field(default=0, ge=0, le=10)
    recommended_actions: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class SoakAuditSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: int | None = None
    horizons_hours: list[int] = Field(default_factory=list)
    progression_miss_risk: int = Field(default=0, ge=0, le=100)
    drift_risk: int = Field(default=0, ge=0, le=100)
    strategy_lock_risk: int = Field(default=0, ge=0, le=100)
    recap_decay_risk: int = Field(default=0, ge=0, le=100)
    clip_drought_risk: int = Field(default=0, ge=0, le=100)
    ship_stagnation_risk: int = Field(default=0, ge=0, le=100)
    unresolved_overload_risk: int = Field(default=0, ge=0, le=100)
    recommended_direction: str = ""
    audit_notes: list[str] = Field(default_factory=list)
    candidate_pressure: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class OpsTelemetrySnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    runtime_status: str = "unknown"
    phase: str = "unknown"
    degraded_mode: bool = False
    load_tier: str = "low"
    average_latency_ms: int = Field(default=0, ge=0)
    checkpoint_age_seconds: int = Field(default=0, ge=0)
    recap_age_minutes: int = Field(default=0, ge=0)
    strategy_age_minutes: int = Field(default=0, ge=0)
    drift_risk: int = Field(default=0, ge=0, le=100)
    progression_contract_open: bool = False
    restart_count: int = Field(default=0, ge=0)
    active_strategy: str = ""
    auto_remediations: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime | None = None


class StrategicBriefPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str
    current_north_star_objective: str
    viewer_value_thesis: str
    urgency: int = Field(default=5, ge=1, le=10)
    arc_priority_ranking: list[str] = Field(default_factory=list)
    danger_of_drift_score: int = Field(default=25, ge=0, le=100)
    cliffhanger_urgency: int = Field(default=5, ge=1, le=10)
    romance_urgency: int = Field(default=5, ge=1, le=10)
    mystery_urgency: int = Field(default=5, ge=1, le=10)
    house_pressure_priority: int = Field(default=5, ge=1, le=10)
    audience_rollout_priority: int = Field(default=5, ge=1, le=10)
    dormant_threads_to_revive: list[str] = Field(default_factory=list)
    reveals_allowed_soon: list[str] = Field(default_factory=list)
    reveals_forbidden_for_now: list[str] = Field(default_factory=list)
    next_one_hour_intention: str
    next_six_hour_intention: str
    next_twenty_four_hour_intention: str
    next_hour_focus: list[str] = Field(default_factory=list)
    next_six_hours: list[str] = Field(default_factory=list)
    recap_priorities: list[str] = Field(default_factory=list)
    fan_theory_potential: int = Field(default=5, ge=1, le=10)
    clip_generation_potential: int = Field(default=5, ge=1, le=10)
    reentry_clarity_priority: int = Field(default=5, ge=1, le=10)
    quote_worthiness: int = Field(default=5, ge=1, le=10)
    betrayal_value: int = Field(default=5, ge=1, le=10)
    daily_uniqueness: int = Field(default=5, ge=1, le=10)
    fandom_discussion_value: int = Field(default=5, ge=1, le=10)
    recommendations: list[str] = Field(default_factory=list)
    risk_alerts: list[str] = Field(default_factory=list)
    house_pressure_actions: list[str] = Field(default_factory=list)
    audience_rollout_actions: list[str] = Field(default_factory=list)
    manager_biases: dict[str, list[str]] = Field(default_factory=dict)
    expires_in_minutes: int = Field(default=90, ge=10, le=720)


class StrategicBriefSnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str = "god-ai"
    model_name: str | None = None
    title: str = ""
    current_north_star_objective: str = ""
    viewer_value_thesis: str = ""
    urgency: int = Field(default=5, ge=1, le=10)
    arc_priority_ranking: list[str] = Field(default_factory=list)
    danger_of_drift_score: int = Field(default=25, ge=0, le=100)
    cliffhanger_urgency: int = Field(default=5, ge=1, le=10)
    romance_urgency: int = Field(default=5, ge=1, le=10)
    mystery_urgency: int = Field(default=5, ge=1, le=10)
    house_pressure_priority: int = Field(default=5, ge=1, le=10)
    audience_rollout_priority: int = Field(default=5, ge=1, le=10)
    dormant_threads_to_revive: list[str] = Field(default_factory=list)
    reveals_allowed_soon: list[str] = Field(default_factory=list)
    reveals_forbidden_for_now: list[str] = Field(default_factory=list)
    next_one_hour_intention: str = ""
    next_six_hour_intention: str = ""
    next_twenty_four_hour_intention: str = ""
    next_hour_focus: list[str] = Field(default_factory=list)
    next_six_hours: list[str] = Field(default_factory=list)
    recap_priorities: list[str] = Field(default_factory=list)
    fan_theory_potential: int = Field(default=5, ge=1, le=10)
    clip_generation_potential: int = Field(default=5, ge=1, le=10)
    reentry_clarity_priority: int = Field(default=5, ge=1, le=10)
    quote_worthiness: int = Field(default=5, ge=1, le=10)
    betrayal_value: int = Field(default=5, ge=1, le=10)
    daily_uniqueness: int = Field(default=5, ge=1, le=10)
    fandom_discussion_value: int = Field(default=5, ge=1, le=10)
    recommendations: list[str] = Field(default_factory=list)
    risk_alerts: list[str] = Field(default_factory=list)
    house_pressure_actions: list[str] = Field(default_factory=list)
    audience_rollout_actions: list[str] = Field(default_factory=list)
    manager_biases: dict[str, list[str]] = Field(default_factory=dict)
    simulation_ranking: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    expires_at: datetime | None = None


class TurnCriticReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: int = Field(default=100, ge=0, le=100)
    reasons: list[str] = Field(default_factory=list)
    repair_actions: list[str] = Field(default_factory=list)
    quote_worthiness: int = Field(default=5, ge=0, le=10)
    clip_value: int = Field(default=5, ge=0, le=10)
    fandom_discussion_value: int = Field(default=5, ge=0, le=10)
    novelty: int = Field(default=5, ge=0, le=10)
    should_repair: bool = False


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
    story_gravity_state: StoryGravityStateSnapshot = Field(
        default_factory=StoryGravityStateSnapshot
    )
    viewer_value_targets: list[str] = Field(default_factory=list)
    voice_guardrails: list[str] = Field(default_factory=list)
    cast_guidance: list[str] = Field(default_factory=list)
    current_arc_summaries: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    payoff_threads: list[str] = Field(default_factory=list)
    dormant_threads: list[str] = Field(default_factory=list)
    relationship_map: list[str] = Field(default_factory=list)
    recent_summaries: list[str] = Field(default_factory=list)
    recent_events: list[str] = Field(default_factory=list)
    recent_messages: list[str] = Field(default_factory=list)
    continuity_warnings: list[str] = Field(default_factory=list)
    recap_quality_alerts: list[str] = Field(default_factory=list)
    public_turn_review_signals: list[str] = Field(default_factory=list)
    pacing_health: PacingHealthReport
    story_governance: StoryGovernanceReport = Field(default_factory=StoryGovernanceReport)
    audience_control: AudienceControlReport = Field(default_factory=AudienceControlReport)
    house_state: HouseStateSnapshot = Field(default_factory=HouseStateSnapshot)
    pending_beats: list[str] = Field(default_factory=list)
    hourly_ledger: HourlyProgressLedgerSnapshot = Field(
        default_factory=HourlyProgressLedgerSnapshot
    )
    programming_grid_digest: list[str] = Field(default_factory=list)
    load_profile: LoadProfileSnapshot = Field(default_factory=LoadProfileSnapshot)
    canon_capsule_digest: list[str] = Field(default_factory=list)
    canon_court_alerts: list[str] = Field(default_factory=list)
    timeline_digest: list[str] = Field(default_factory=list)
    chronology_graph_digest: list[str] = Field(default_factory=list)
    contradiction_watch_digest: list[str] = Field(default_factory=list)
    possession_digest: list[str] = Field(default_factory=list)
    room_occupancy_digest: list[str] = Field(default_factory=list)
    season_plan_digest: list[str] = Field(default_factory=list)
    viewer_signal_digest: list[str] = Field(default_factory=list)
    voice_fingerprint_digest: list[str] = Field(default_factory=list)
    guest_pressure_digest: list[str] = Field(default_factory=list)
    highlight_signals: list[str] = Field(default_factory=list)
    monetization_signals: list[str] = Field(default_factory=list)
    broadcast_asset_signals: list[str] = Field(default_factory=list)
    soak_audit_signals: list[str] = Field(default_factory=list)
    ops_alerts: list[str] = Field(default_factory=list)
    strategic_guidance: list[str] = Field(default_factory=list)
    simulation_ranking: list[str] = Field(default_factory=list)
    strategic_brief: StrategicBriefSnapshot | None = None


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
    live_pressures: list[str] = Field(default_factory=list)
    timeline_grounding: list[str] = Field(default_factory=list)
    voice_fingerprint: list[str] = Field(default_factory=list)
    story_memory_capsule: list[str] = Field(default_factory=list)
    manager_directive: str
    forbidden_boundaries: list[str] = Field(default_factory=list)


CanonCourtReport.model_rebuild()
AudienceControlReport.model_rebuild()
