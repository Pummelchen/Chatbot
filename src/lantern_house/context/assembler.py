from __future__ import annotations

from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import (
    CharacterContextPacket,
    ManagerContextPacket,
)
from lantern_house.quality.governance import StoryGovernanceEvaluator
from lantern_house.quality.pacing import PacingHealthEvaluator
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

    def build_manager_packet(self) -> ManagerContextPacket:
        world = self.repository.get_world_state_snapshot()
        scene = self.repository.get_scene_snapshot()
        characters = self.repository.list_characters()
        messages = self.repository.list_recent_messages(limit=8)
        events = self.repository.list_recent_events(hours=24, limit=6, minimum_significance=4)
        summaries = self.repository.list_recent_summaries(limit=2)
        arcs = self.repository.list_open_arcs(limit=4)
        continuity_flags = self.repository.list_open_continuity_flags(limit=4)

        pacing_health = self.pacing_evaluator.evaluate(messages=messages, events=events)
        story_engine = world["metadata"].get("story_engine", {})
        story_governance = self.governance_evaluator.evaluate(
            messages=messages,
            events=events,
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
                    story_engine.get("central_force", ""),
                    *story_engine.get("core_promises", []),
                ]
                if item
            ],
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
            payoff_threads=[
                _compact_text(item, limit=120) for item in world["archived_threads"][:4]
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
            pacing_health=pacing_health,
            story_governance=story_governance,
        )

    def build_character_packet(
        self, character_slug: str, directive: dict
    ) -> CharacterContextPacket:
        overview = self.repository.get_character_overview(character_slug)
        scene = self.repository.get_scene_snapshot()
        recent_messages = self.repository.list_recent_messages(limit=5)
        recent_events = self.repository.list_recent_events(
            hours=6, limit=5, minimum_significance=3
        )
        relationships = self.repository.list_relationship_snapshots(character_slug)[:3]
        relevant_facts = self.repository.get_relevant_facts(
            location_id=scene["location_id"], limit=3
        )
        boundaries = self.repository.get_forbidden_boundaries(
            character_slug=character_slug, limit=3
        )
        story_engine = self.repository.get_world_state_snapshot()["metadata"].get(
            "story_engine", {}
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
