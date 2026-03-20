from __future__ import annotations

from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import CharacterContextPacket, ManagerContextPacket, PacingHealthReport
from lantern_house.quality.pacing import PacingHealthEvaluator
from lantern_house.utils.time import isoformat


class ContextAssembler:
    def __init__(self, repository: StoryRepository, pacing_evaluator: PacingHealthEvaluator) -> None:
        self.repository = repository
        self.pacing_evaluator = pacing_evaluator

    def build_manager_packet(self) -> ManagerContextPacket:
        world = self.repository.get_world_state_snapshot()
        scene = self.repository.get_scene_snapshot()
        messages = self.repository.list_recent_messages(limit=24)
        events = self.repository.list_recent_events(hours=24, limit=18, minimum_significance=4)
        summaries = self.repository.list_recent_summaries(limit=6)
        arcs = self.repository.list_open_arcs(limit=6)
        continuity_flags = self.repository.list_open_continuity_flags(limit=8)

        pacing_health = self.pacing_evaluator.evaluate(messages=messages, events=events)

        return ManagerContextPacket(
            title=world["title"],
            scene_objective=scene["objective"],
            scene_location=scene["location_name"],
            emotional_temperature=scene["emotional_temperature"],
            current_arc_summaries=[
                f"{arc.title} (stage {arc.stage_index}, pressure {arc.pressure_score}): {arc.summary}"
                for arc in arcs
            ],
            unresolved_questions=world["unresolved_questions"],
            relationship_map=self.repository.get_relationship_map()[:12],
            recent_summaries=[
                f"{summary.summary_window} @ {isoformat(summary.bucket_end_at)}: {summary.content}"
                for summary in summaries
            ],
            recent_events=[
                f"{event.event_type.upper()}: {event.title} - {event.details}" for event in events
            ],
            recent_messages=[
                f"{message.speaker_label}: {message.content}" for message in messages
            ],
            continuity_warnings=[
                f"{flag['severity'].upper()} {flag['flag_type']}: {flag['description']}"
                for flag in continuity_flags
            ],
            pacing_health=pacing_health,
        )

    def build_character_packet(self, character_slug: str, directive: dict) -> CharacterContextPacket:
        overview = self.repository.get_character_overview(character_slug)
        scene = self.repository.get_scene_snapshot()
        recent_messages = self.repository.list_recent_messages(limit=12)
        recent_events = self.repository.list_recent_events(hours=6, limit=10, minimum_significance=3)
        relationships = self.repository.list_relationship_snapshots(character_slug)
        relevant_facts = self.repository.get_relevant_facts(location_id=scene["location_id"], limit=6)
        boundaries = self.repository.get_forbidden_boundaries(character_slug=character_slug, limit=6)

        personal_directive = directive.get("per_character", {}).get(character_slug, {})
        directive_text = (
            f"Objective: {directive['objective']}. "
            f"Your soft goal: {personal_directive.get('goal', 'Keep the scene alive')}. "
            f"Pressure point: {personal_directive.get('pressure_point', 'Do not become passive')}. "
            f"Desired partner: {personal_directive.get('desired_partner', 'anyone volatile in scene')}."
        )

        return CharacterContextPacket(
            character_slug=overview["slug"],
            full_name=overview["full_name"],
            public_persona=overview["public_persona"],
            hidden_wound=overview["hidden_wound"],
            long_term_desire=overview["long_term_desire"],
            private_fear=overview["private_fear"],
            message_style=overview["message_style"],
            ensemble_role=overview["ensemble_role"],
            current_location=overview["location_name"],
            emotional_state=overview["emotional_state"],
            current_goals=overview["current_goals"],
            relationship_snapshots=[
                f"{item.counterpart_slug}: trust {item.trust_score}, desire {item.desire_score}, suspicion {item.suspicion_score}, obligation {item.obligation_score}. {item.summary}"
                for item in relationships
            ],
            recent_messages=[
                f"{message.speaker_label}: {message.content}" for message in recent_messages
            ],
            relevant_facts=relevant_facts,
            recent_events=[
                f"{event.event_type.upper()}: {event.title} - {event.details}" for event in recent_events
            ],
            manager_directive=directive_text,
            forbidden_boundaries=boundaries,
        )

