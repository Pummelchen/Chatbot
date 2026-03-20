from __future__ import annotations

from datetime import timedelta

from lantern_house.context.assembler import ContextAssembler
from lantern_house.domain.contracts import EventView, MessageView, RelationshipSnapshot, SummaryView
from lantern_house.quality.pacing import PacingHealthEvaluator
from lantern_house.utils.time import utcnow


class FakeRepository:
    def get_world_state_snapshot(self):
        return {
            "title": "Saltglass House",
            "active_scene_key": "opening-night",
            "current_story_day": 1,
            "emotional_temperature": 6,
            "reveal_pressure": 1,
            "unresolved_questions": ["Who hid the ledger?"],
            "archived_threads": [],
            "metadata": {},
        }

    def get_scene_snapshot(self):
        return {
            "id": 1,
            "scene_key": "opening-night",
            "objective": "Keep the house from splintering.",
            "location_name": "Front Desk",
            "location_id": 1,
            "emotional_temperature": 6,
            "mystery_pressure": 7,
            "romance_pressure": 6,
            "comedic_pressure": 4,
            "active_character_slugs": ["mara", "nia", "luca"],
        }

    def list_recent_messages(self, limit=20):
        now = utcnow()
        return [
            MessageView(speaker_label="Mara", content="Stay focused.", kind="chat", created_at=now - timedelta(minutes=5)),
            MessageView(speaker_label="Luca", content="On what, exactly?", kind="chat", created_at=now - timedelta(minutes=4)),
        ]

    def list_recent_events(self, hours=24, limit=20, minimum_significance=1):
        now = utcnow()
        return [
            EventView(
                event_type="clue",
                title="The brass key matters",
                details="A key was mentioned with unusual urgency.",
                significance=7,
                payload={},
                created_at=now - timedelta(minutes=4),
            )
        ]

    def list_recent_summaries(self, limit=6):
        now = utcnow()
        return [
            SummaryView(
                summary_window="1h",
                content="Luca's return destabilized the room.",
                structured_highlights={},
                bucket_end_at=now - timedelta(hours=1),
            )
        ]

    def list_open_arcs(self, limit=6):
        from lantern_house.domain.contracts import StoryArcSnapshot

        return [
            StoryArcSnapshot(
                slug="vanished-owner",
                title="The Vanishing of Celeste Vale",
                summary="The central mystery remains open.",
                stage_index=0,
                unresolved_questions=["Who was Celeste afraid of?"],
                reveal_ladder=["A clue appears."],
                pressure_score=10,
            )
        ]

    def list_open_continuity_flags(self, limit=8):
        return [{"severity": "warning", "flag_type": "repetition", "description": "Energy has flattened."}]

    def get_relationship_map(self):
        return ["mara<->elias: trust 8, desire 7, suspicion 3, obligation 9."]

    def get_character_overview(self, slug):
        return {
            "slug": "mara",
            "full_name": "Mara Dela Cruz",
            "public_persona": "manager",
            "hidden_wound": "wound",
            "long_term_desire": "desire",
            "private_fear": "fear",
            "message_style": "clipped",
            "ensemble_role": "manager",
            "location_name": "Front Desk",
            "emotional_state": {"current": "guarded"},
            "current_goals": ["hold the room"],
        }

    def list_relationship_snapshots(self, slug):
        return [
            RelationshipSnapshot(
                counterpart_slug="elias",
                trust_score=8,
                desire_score=7,
                suspicion_score=3,
                obligation_score=9,
                summary="Complicated history.",
            )
        ]

    def get_relevant_facts(self, location_id, limit=6):
        return ["The desk drawers are full of unpaid invoices."]

    def get_forbidden_boundaries(self, character_slug, limit=6):
        return ["Do not reveal hidden recordings without a trigger."]


def test_context_assembler_builds_packets() -> None:
    assembler = ContextAssembler(FakeRepository(), PacingHealthEvaluator())
    manager_packet = assembler.build_manager_packet()
    character_packet = assembler.build_character_packet(
        "mara",
        {
            "objective": "Push the scene toward a sharper question.",
            "per_character": {"mara": {"goal": "control the damage", "pressure_point": "Luca is back"}},
        },
    )
    assert manager_packet.title == "Saltglass House"
    assert "Who hid the ledger?" in manager_packet.unresolved_questions
    assert character_packet.character_slug == "mara"
    assert "control the damage" in character_packet.manager_directive

