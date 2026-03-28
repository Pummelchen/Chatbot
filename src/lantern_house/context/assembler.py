# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import (
    AudienceControlReport,
    CharacterContextPacket,
    HourlyProgressLedgerSnapshot,
    HouseStateSnapshot,
    LoadProfileSnapshot,
    ManagerContextPacket,
    OpsTelemetrySnapshot,
    StoryGravityStateSnapshot,
)
from lantern_house.quality.governance import StoryGovernanceEvaluator
from lantern_house.quality.pacing import PacingHealthEvaluator
from lantern_house.services.world_tracking import build_room_occupancy_digest
from lantern_house.utils.time import isoformat


class ContextAssembler:
    def __init__(
        self,
        repository: StoryRepository,
        pacing_evaluator: PacingHealthEvaluator,
        governance_evaluator: StoryGovernanceEvaluator | None = None,
    ) -> None:
        self.repository = repository
        self.pacing_evaluator = pacing_evaluator
        self.governance_evaluator = governance_evaluator or StoryGovernanceEvaluator()

    def build_manager_packet(
        self,
        *,
        audience_control: AudienceControlReport | None = None,
        include_strategic: bool = True,
        load_profile: LoadProfileSnapshot | None = None,
        ops_snapshot: OpsTelemetrySnapshot | None = None,
    ) -> ManagerContextPacket:
        world = self.repository.get_world_state_snapshot()
        scene = self.repository.get_scene_snapshot()
        characters = self.repository.list_characters()
        messages = self.repository.list_recent_messages(limit=8)
        events = self.repository.list_recent_events(hours=24, limit=6, minimum_significance=4)
        summaries = self.repository.list_recent_summaries(limit=2)
        arcs = self.repository.list_open_arcs(limit=4)
        continuity_flags = self.repository.list_open_continuity_flags(limit=4)
        house_state = _repo_call(
            self.repository,
            "get_house_state_snapshot",
            default=HouseStateSnapshot(),
        )
        pending_beats = _repo_call(self.repository, "list_pending_beats", limit=4, default=[])
        story_gravity_state = _repo_call(
            self.repository,
            "get_story_gravity_state_snapshot",
            default=StoryGravityStateSnapshot(),
        )
        public_turn_reviews = _repo_call(
            self.repository,
            "list_recent_public_turn_reviews",
            limit=4,
            default=[],
        )
        recap_quality_scores = _repo_call(
            self.repository,
            "list_recent_recap_quality_scores",
            limit=3,
            default=[],
        )
        dormant_threads = _repo_call(
            self.repository,
            "list_dormant_threads",
            limit=4,
            default=[],
        )
        hourly_ledger = _repo_call(
            self.repository,
            "get_latest_hourly_progress_ledger",
            default=None,
        )
        programming_grid_slots = _repo_call(
            self.repository,
            "list_programming_grid_slots",
            limit=6,
            default=[],
        )
        canon_capsules = _repo_call(
            self.repository,
            "list_canon_capsules",
            default=[],
        )
        canon_court_findings = _repo_call(
            self.repository,
            "list_recent_canon_court_findings",
            limit=4,
            default=[],
        )
        chronology_edges = _repo_call(
            self.repository,
            "list_recent_chronology_edges",
            limit=8,
            default=[],
        )
        contradiction_edges = _repo_call(
            self.repository,
            "list_recent_chronology_edges",
            limit=4,
            contradiction_only=True,
            default=[],
        )
        timeline_facts = _repo_call(
            self.repository,
            "list_recent_timeline_facts",
            hours=12,
            limit=8,
            default=[],
        )
        object_possessions = _repo_call(
            self.repository,
            "list_object_possessions",
            limit=6,
            default=[],
        )
        viewer_signals = _repo_call(
            self.repository,
            "list_active_viewer_signals",
            limit=5,
            default=[],
        )
        youtube_adapter_state = _repo_call(
            self.repository,
            "get_youtube_adapter_state",
            default=None,
        )
        voice_fingerprints = _repo_call(
            self.repository,
            "list_voice_fingerprints",
            limit=6,
            default=[],
        )
        guest_profiles = _repo_call(
            self.repository,
            "list_active_guest_profiles",
            limit=4,
            default=[],
        )
        daily_life_slots = _repo_call(
            self.repository,
            "list_daily_life_schedule_slots",
            limit=8,
            default=[],
        )
        payoff_debts = _repo_call(
            self.repository,
            "list_payoff_debts",
            statuses=["open", "at-risk", "due", "overdue"],
            limit=6,
            default=[],
        )
        highlight_packages = _repo_call(
            self.repository,
            "list_recent_highlight_packages",
            limit=4,
            default=[],
        )
        monetization_packages = _repo_call(
            self.repository,
            "list_recent_monetization_packages",
            limit=3,
            default=[],
        )
        broadcast_assets = _repo_call(
            self.repository,
            "list_recent_broadcast_assets",
            limit=3,
            default=[],
        )
        soak_audit = _repo_call(
            self.repository,
            "get_latest_soak_audit",
            default=None,
        )
        shadow_replay = _repo_call(
            self.repository,
            "get_latest_shadow_replay_run",
            default=None,
        )
        strategic_brief = (
            _repo_call(self.repository, "get_latest_strategic_brief", default=None)
            if include_strategic
            else None
        )
        latest_ops_snapshot = ops_snapshot or _repo_call(
            self.repository,
            "get_latest_ops_telemetry",
            default=None,
        )
        positions = _repo_call(
            self.repository,
            "list_character_positions",
            default=[],
        )

        pacing_health = self.pacing_evaluator.evaluate(messages=messages, events=events)
        story_engine = world["metadata"].get("story_engine", {})
        effective_load_profile = load_profile or LoadProfileSnapshot()
        story_governance = self.governance_evaluator.evaluate(
            messages=messages,
            events=events,
            summaries=summaries,
            world_metadata=world["metadata"],
            unresolved_questions=world["unresolved_questions"],
        )

        return ManagerContextPacket(
            title=world["title"],
            scene_objective=scene["objective"],
            scene_location=scene["location_name"],
            emotional_temperature=scene["emotional_temperature"],
            story_gravity=[
                item
                for item in [
                    story_gravity_state.north_star_objective
                    or story_engine.get("central_force", ""),
                    *story_gravity_state.active_axes[:3],
                    *story_engine.get("core_promises", []),
                ]
                if item
            ][:6],
            story_gravity_state=story_gravity_state,
            viewer_value_targets=story_engine.get("viewer_value_targets", []),
            voice_guardrails=story_engine.get("voice_guardrails", []),
            cast_guidance=[
                _compact_text(
                    (
                        f"{item['slug']} / {item['full_name']}: {item['cultural_background']}. "
                        f"Family pressure: {item['family_expectations']} "
                        f"Conflict style: {item['conflict_style']} "
                        f"Values: {item['value_instincts']}"
                    ),
                    limit=150,
                )
                for item in characters
            ],
            current_arc_summaries=[
                _compact_text(
                    (
                        f"{arc.title} (stage {arc.stage_index}, "
                        f"pressure {arc.pressure_score}): {arc.summary} "
                        f"Current beat: {arc.metadata.get('active_beat') or _current_arc_beat(arc)}"
                    ),
                    limit=220,
                )
                for arc in arcs
            ],
            unresolved_questions=world["unresolved_questions"],
            payoff_threads=[_compact_text(item.summary, limit=120) for item in dormant_threads[:4]],
            dormant_threads=[
                _compact_text(
                    f"{item.status} / heat {item.heat}: {item.summary}",
                    limit=140,
                )
                for item in dormant_threads[:4]
            ],
            relationship_map=[
                _compact_text(item, limit=140)
                for item in self.repository.get_relationship_map()[:4]
            ],
            recent_summaries=[
                _compact_text(
                    (
                        f"{summary.summary_window} @ {isoformat(summary.bucket_end_at)}: "
                        f"{summary.content}"
                    ),
                    limit=220,
                )
                for summary in summaries
            ],
            recent_events=[
                _compact_text(
                    f"{event.event_type.upper()}: {event.title} - {event.details}",
                    limit=140,
                )
                for event in events
            ],
            recent_messages=[
                _compact_text(f"{message.speaker_label}: {message.content}", limit=120)
                for message in messages
            ],
            continuity_warnings=[
                _compact_text(
                    f"{flag['severity'].upper()} {flag['flag_type']}: {flag['description']}",
                    limit=180,
                )
                for flag in continuity_flags
            ],
            recap_quality_alerts=[
                _compact_text(
                    (
                        f"{item['summary_window']} recap quality "
                        f"(clarity {item['clarity']}, hook {item['next_hook_strength']}): "
                        f"{'; '.join(item['issues'][:2]) or 'no recent issue'}"
                    ),
                    limit=180,
                )
                for item in recap_quality_scores
            ],
            public_turn_review_signals=[
                _compact_text(
                    (
                        f"{item['speaker_slug']} review {item['critic_score']} "
                        f"(clip {item['clip_value']}, fandom {item['fandom_discussion_value']}): "
                        f"{'; '.join(item['reasons'][:2]) or 'clean'}"
                    ),
                    limit=180,
                )
                for item in public_turn_reviews
            ],
            pacing_health=pacing_health,
            story_governance=story_governance,
            audience_control=audience_control or AudienceControlReport(),
            house_state=house_state,
            pending_beats=[
                _compact_text(
                    (
                        f"{beat.beat_type} / {beat.status}: {beat.objective}"
                        + (f" @ {isoformat(beat.due_by)}" if beat.due_by else "")
                    ),
                    limit=180,
                )
                for beat in pending_beats
            ],
            hourly_ledger=hourly_ledger or HourlyProgressLedgerSnapshot(),
            programming_grid_digest=[
                _compact_text(
                    f"{slot.horizon} {slot.label} [{slot.status}]: {slot.notes[0]}",
                    limit=190,
                )
                for slot in programming_grid_slots
                if slot.horizon in {"daily", "weekly"}
            ][:4],
            load_profile=effective_load_profile,
            canon_capsule_digest=[
                _compact_text(
                    (
                        f"{capsule.window_key}: {capsule.headline} | "
                        f"{', '.join(capsule.state_of_play[:2])}"
                    ),
                    limit=200,
                )
                for capsule in canon_capsules[:3]
            ],
            canon_court_alerts=[
                _compact_text(
                    f"{item.severity.upper()} {item.issue_type}: {item.summary}",
                    limit=180,
                )
                for item in canon_court_findings[:3]
            ],
            timeline_digest=[
                _compact_text(
                    f"{item.fact_type}: {item.summary}",
                    limit=180,
                )
                for item in timeline_facts[:4]
            ],
            chronology_graph_digest=[
                _compact_text(
                    (
                        f"{item.subject_key} {item.predicate} {item.object_key} "
                        f"[{item.contradiction_status}]"
                    ),
                    limit=190,
                )
                for item in chronology_edges[:4]
            ],
            contradiction_watch_digest=[
                _compact_text(
                    f"{item.subject_key} contested: {item.supporting_text}",
                    limit=190,
                )
                for item in contradiction_edges[:3]
            ],
            possession_digest=[
                _compact_text(
                    f"{item.object_name}: {item.summary}",
                    limit=180,
                )
                for item in object_possessions[:4]
            ],
            room_occupancy_digest=[
                _compact_text(item, limit=160)
                for item in build_room_occupancy_digest(positions, max_rooms=4)
            ],
            season_plan_digest=[
                _compact_text(
                    f"{slot.horizon} {slot.label} [{slot.status}]: {slot.objective}",
                    limit=200,
                )
                for slot in programming_grid_slots
                if slot.horizon.startswith("season")
            ][:4],
            viewer_signal_digest=[
                _compact_text(
                    (
                        f"{item.signal_type} / {item.subject} / impact {item.retention_impact}: "
                        f"{item.summary}"
                    ),
                    limit=190,
                )
                for item in viewer_signals[:4]
            ],
            youtube_adapter_digest=[
                *(
                    [
                        _compact_text(
                            f"themes: {', '.join(youtube_adapter_state.active_themes[:3])}",
                            limit=190,
                        )
                    ]
                    if youtube_adapter_state.active_themes
                    else []
                ),
                *(
                    [
                        _compact_text(
                            f"ships: {', '.join(youtube_adapter_state.ship_heat[:2])}",
                            limit=190,
                        )
                    ]
                    if youtube_adapter_state.ship_heat
                    else []
                ),
                *(
                    [
                        _compact_text(
                            f"retention: {youtube_adapter_state.retention_alerts[0]}",
                            limit=190,
                        )
                    ]
                    if youtube_adapter_state.retention_alerts
                    else []
                ),
                *(
                    [
                        _compact_text(
                            f"clip spikes: {youtube_adapter_state.clip_spikes[0]}",
                            limit=190,
                        )
                    ]
                    if youtube_adapter_state.clip_spikes
                    else []
                ),
            ]
            if youtube_adapter_state
            else [],
            voice_fingerprint_digest=[
                _compact_text(
                    (
                        f"{item.character_slug}: {item.cadence_profile}; "
                        f"{item.conflict_tone}; markers {', '.join(item.lexical_markers[:3])}"
                    ),
                    limit=190,
                )
                for item in voice_fingerprints[:4]
            ],
            guest_pressure_digest=[
                _compact_text(
                    f"{item.display_name} / {item.role}: {item.hook}",
                    limit=190,
                )
                for item in guest_profiles[:3]
            ],
            daily_life_digest=[
                _compact_text(
                    (
                        f"{slot.participant_name} @ {slot.location_name}: "
                        f"{slot.objective} [{slot.status}]"
                    ),
                    limit=200,
                )
                for slot in daily_life_slots[:4]
            ],
            payoff_debt_digest=[
                _compact_text(
                    (
                        f"{item.payoff_class} / {item.due_window} / heat {item.heat}: "
                        f"{item.summary}"
                    ),
                    limit=200,
                )
                for item in payoff_debts[:4]
            ],
            inference_policy_digest=[
                _compact_text(item, limit=180)
                for item in ((effective_load_profile.metadata or {}).get("policy_digest") or [])
            ],
            highlight_signals=[
                _compact_text(
                    f"{item.speaker_slug} / score {item.score}: {item.title} | {item.hook_line}",
                    limit=190,
                )
                for item in highlight_packages[:3]
            ],
            monetization_signals=[
                _compact_text(
                    (
                        f"{item.speaker_slug} / score {item.score}: {item.primary_title} | "
                        f"{item.comment_prompt}"
                    ),
                    limit=190,
                )
                for item in monetization_packages[:2]
            ],
            broadcast_asset_signals=[
                _compact_text(
                    (
                        f"{item.speaker_slug} / asset {item.asset_score}: "
                        f"{item.asset_title} | {item.why_it_matters}"
                    ),
                    limit=190,
                )
                for item in broadcast_assets[:2]
            ],
            soak_audit_signals=(
                [
                    _compact_text(
                        (
                            f"Soak winner {soak_audit.recommended_direction}; "
                            f"progression risk {soak_audit.progression_miss_risk}; "
                            f"drift risk {soak_audit.drift_risk}"
                        ),
                        limit=180,
                    ),
                    *[_compact_text(item, limit=160) for item in soak_audit.audit_notes[:2]],
                ]
                if soak_audit
                else []
            ),
            shadow_replay_digest=(
                [
                    _compact_text(
                        (
                            f"shadow {shadow_replay.status}; turns {shadow_replay.compared_turns}; "
                            f"regressions {shadow_replay.regression_count}"
                        ),
                        limit=190,
                    ),
                    *[
                        _compact_text(item, limit=180)
                        for item in shadow_replay.regressions[:2]
                    ],
                ]
                if shadow_replay
                else []
            ),
            ops_alerts=[
                _compact_text(
                    (
                        f"{latest_ops_snapshot.load_tier} load / checkpoint "
                        f"{latest_ops_snapshot.checkpoint_age_seconds}s / recap "
                        f"{latest_ops_snapshot.recap_age_minutes}m"
                    ),
                    limit=180,
                ),
                *[
                    _compact_text(item, limit=160)
                    for item in latest_ops_snapshot.auto_remediations[:2]
                ],
            ]
            if latest_ops_snapshot
            else [],
            strategic_guidance=[
                _compact_text(strategic_brief.current_north_star_objective, limit=180),
                _compact_text(strategic_brief.viewer_value_thesis, limit=180),
                _compact_text(strategic_brief.next_one_hour_intention, limit=160),
                *[
                    _compact_text(item, limit=150)
                    for item in (strategic_brief.recommendations[:2] if strategic_brief else [])
                ],
            ]
            if strategic_brief
            else [],
            simulation_ranking=strategic_brief.simulation_ranking[:4] if strategic_brief else [],
            strategic_brief=strategic_brief,
        )

    def build_character_packet(
        self, character_slug: str, directive: dict
    ) -> CharacterContextPacket:
        overview = self.repository.get_character_overview(character_slug)
        scene = self.repository.get_scene_snapshot()
        recent_messages = self.repository.list_recent_messages(limit=5)
        recent_events = self.repository.list_recent_events(hours=6, limit=5, minimum_significance=3)
        relationships = self.repository.list_relationship_snapshots(character_slug)[:3]
        relevant_facts = self.repository.get_relevant_facts(
            location_id=scene["location_id"], limit=3
        )
        boundaries = self.repository.get_forbidden_boundaries(
            character_slug=character_slug, limit=3
        )
        house_state = _repo_call(
            self.repository,
            "get_house_state_snapshot",
            default=HouseStateSnapshot(),
        )
        pending_beats = _repo_call(self.repository, "list_pending_beats", limit=3, default=[])
        canon_capsules = _repo_call(
            self.repository,
            "list_canon_capsules",
            window_keys=["6h", "24h"],
            default=[],
        )
        story_engine = self.repository.get_world_state_snapshot()["metadata"].get(
            "story_engine", {}
        )
        timeline_facts = _repo_call(
            self.repository,
            "list_recent_timeline_facts",
            hours=8,
            limit=8,
            default=[],
        )
        object_possessions = _repo_call(
            self.repository,
            "list_object_possessions",
            limit=4,
            default=[],
        )
        positions = _repo_call(
            self.repository,
            "list_character_positions",
            default=[],
        )
        voice_fingerprint = _repo_call(
            self.repository,
            "list_voice_fingerprints",
            character_slugs=[character_slug],
            limit=1,
            default=[],
        )
        contradiction_edges = _repo_call(
            self.repository,
            "list_recent_chronology_edges",
            contradiction_only=True,
            limit=4,
            default=[],
        )
        daily_life_slots = _repo_call(
            self.repository,
            "list_daily_life_schedule_slots",
            participant_slug=character_slug,
            limit=3,
            default=[],
        )
        payoff_debts = _repo_call(
            self.repository,
            "list_payoff_debts",
            linked_character_slug=character_slug,
            statuses=["open", "at-risk", "due", "overdue"],
            limit=3,
            default=[],
        )

        personal_directive = directive.get("per_character", {}).get(character_slug, {})
        directive_text = (
            f"Objective: {directive['objective']}. "
            f"Your soft goal: {personal_directive.get('goal', 'Keep the scene alive')}. "
            f"Pressure point: {personal_directive.get('pressure_point', 'Do not become passive')}. "
            "Desired partner: "
            f"{personal_directive.get('desired_partner', 'anyone volatile in scene')}."
        )

        return CharacterContextPacket(
            character_slug=overview["slug"],
            full_name=overview["full_name"],
            cultural_background=overview["cultural_background"],
            public_persona=overview["public_persona"],
            hidden_wound=overview["hidden_wound"],
            long_term_desire=overview["long_term_desire"],
            private_fear=overview["private_fear"],
            family_expectations=overview["family_expectations"],
            conflict_style=overview["conflict_style"],
            privacy_boundaries=overview["privacy_boundaries"],
            value_instincts=overview["value_instincts"],
            emotional_expression=overview["emotional_expression"],
            message_style=overview["message_style"],
            ensemble_role=overview["ensemble_role"],
            current_location=overview["location_name"],
            voice_guardrails=story_engine.get("voice_guardrails", []),
            emotional_state=overview["emotional_state"],
            current_goals=overview["current_goals"],
            relationship_snapshots=[
                _compact_text(
                    (
                        f"{item.counterpart_slug}: trust {item.trust_score}, "
                        f"desire {item.desire_score}, suspicion {item.suspicion_score}, "
                        f"obligation {item.obligation_score}. {item.summary}"
                    ),
                    limit=140,
                )
                for item in relationships
            ],
            recent_messages=[
                _compact_text(f"{message.speaker_label}: {message.content}", limit=110)
                for message in recent_messages
            ],
            relevant_facts=[_compact_text(fact, limit=100) for fact in relevant_facts],
            recent_events=[
                _compact_text(
                    f"{event.event_type.upper()}: {event.title} - {event.details}",
                    limit=130,
                )
                for event in recent_events
            ],
            live_pressures=[
                *[
                    _compact_text(
                        f"{item.label}: {item.recommended_move or item.summary}",
                        limit=120,
                    )
                    for item in house_state.active_pressures[:2]
                ],
                *[_compact_text(beat.objective, limit=120) for beat in pending_beats[:1]],
            ],
            story_memory_capsule=[
                _compact_text(
                    f"{capsule.window_key}: {capsule.headline}",
                    limit=110,
                )
                for capsule in canon_capsules[:2]
            ],
            timeline_grounding=[
                *[
                    _compact_text(item, limit=120)
                    for item in build_room_occupancy_digest(positions, max_rooms=3)
                ][:2],
                *[
                    _compact_text(f"{fact.fact_type}: {fact.summary}", limit=120)
                    for fact in timeline_facts[:3]
                    if fact.subject_slug in {character_slug, "house"}
                    or fact.location_name == overview["location_name"]
                ],
                *[
                    _compact_text(f"{item.object_name}: {item.summary}", limit=120)
                    for item in object_possessions[:2]
                ],
                *[
                    _compact_text(item.supporting_text, limit=120)
                    for item in contradiction_edges
                    if character_slug in item.subject_key
                    or overview["location_name"].lower() in item.supporting_text.lower()
                ][:1],
            ][:5],
            voice_fingerprint=[
                _compact_text(item.signature_line, limit=140)
                for item in voice_fingerprint[:1]
            ]
            + [
                _compact_text(
                    (
                        f"cadence={item.cadence_profile}; conflict={item.conflict_tone}; "
                        f"markers={', '.join(item.lexical_markers[:3])}"
                    ),
                    limit=140,
                )
                for item in voice_fingerprint[:1]
            ],
            daily_life_schedule=[
                _compact_text(
                    f"{slot.location_name}: {slot.objective} [{slot.status}]",
                    limit=140,
                )
                for slot in daily_life_slots[:2]
            ],
            payoff_debt_pressure=[
                _compact_text(
                    f"{item.due_window} / heat {item.heat}: {item.summary}",
                    limit=140,
                )
                for item in payoff_debts[:2]
            ],
            manager_directive=_compact_text(directive_text, limit=220),
            forbidden_boundaries=[_compact_text(item, limit=100) for item in boundaries],
        )


def _current_arc_beat(arc) -> str:
    if not arc.reveal_ladder:
        return "Hold pressure without solving it."
    index = min(arc.stage_index, len(arc.reveal_ladder) - 1)
    return arc.reveal_ladder[index]


def _compact_text(value: str, *, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _repo_call(repository, method_name: str, *args, default=None, **kwargs):
    method = getattr(repository, method_name, None)
    if method is None:
        return default
    return method(*args, **kwargs)
