# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.context.assembler import ContextAssembler
from lantern_house.domain.contracts import (
    AudienceControlReport,
    DormantThreadSnapshot,
    EventView,
    MessageView,
    RelationshipSnapshot,
    StoryGravityStateSnapshot,
    SummaryView,
)
from lantern_house.quality.pacing import PacingHealthEvaluator
from lantern_house.utils.time import utcnow


class FakeRepository:
    def list_characters(self):
        return [
            {
                "slug": "amelia",
                "full_name": "Amelia Vale",
                "cultural_background": "Anglo (US/UK family line)",
                "family_expectations": "Protect the family name and contain scandal.",
                "conflict_style": "Calm until forced into blunt clarity.",
                "privacy_boundaries": "Avoids public vulnerability.",
                "value_instincts": "Duty first, loyalty through action.",
                "emotional_expression": "Care through competence and restraint.",
                "public_persona": "manager",
                "hidden_wound": "wound",
                "long_term_desire": "desire",
                "private_fear": "fear",
                "message_style": "steady",
                "ensemble_role": "House Manager",
                "color": "bright_blue",
            }
        ]

    def get_world_state_snapshot(self):
        return {
            "title": "Lantern House",
            "active_scene_key": "opening-night",
            "current_story_day": 1,
            "emotional_temperature": 6,
            "reveal_pressure": 1,
            "unresolved_questions": ["Who hid the ledger?"],
            "archived_threads": ["A blackout trapped Amelia and Rafael in the records closet."],
            "metadata": {
                "story_engine": {
                    "central_force": "Every hour must tighten the house's core tensions.",
                    "viewer_value_targets": ["Deliver one meaningful hourly progression."],
                    "voice_guardrails": ["Prefer concrete specifics over speeches."],
                }
            },
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
            "active_character_slugs": ["amelia", "ayu", "lucia"],
        }

    def list_recent_messages(self, limit=20):
        now = utcnow()
        return [
            MessageView(
                speaker_label="Amelia",
                content="Stay focused.",
                kind="chat",
                created_at=now - timedelta(minutes=5),
            ),
            MessageView(
                speaker_label="Lucía",
                content="On what, exactly?",
                kind="chat",
                created_at=now - timedelta(minutes=4),
            ),
        ]

    def list_recent_events(self, hours=24, limit=20, minimum_significance=1):
        now = utcnow()
        return [
            EventView(
                event_type="clue",
                title="The brass key matters",
                details="The lantern-wing key was mentioned with unusual urgency.",
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
                content="Lucía's arrival destabilized the room.",
                structured_highlights={},
                bucket_end_at=now - timedelta(hours=1),
            )
        ]

    def list_open_arcs(self, limit=6):
        from lantern_house.domain.contracts import StoryArcSnapshot

        return [
            StoryArcSnapshot(
                slug="vanished-owner",
                title="What Happened to Evelyn Vale?",
                summary="The central mystery remains open.",
                stage_index=0,
                unresolved_questions=["Who was Evelyn warning Amelia about?"],
                reveal_ladder=["A clue appears."],
                pressure_score=10,
            )
        ]

    def list_open_continuity_flags(self, limit=8):
        return [
            {
                "severity": "warning",
                "flag_type": "repetition",
                "description": "Energy has flattened.",
            }
        ]

    def get_relationship_map(self):
        return ["amelia<->rafael: trust 8, desire 8, suspicion 4, obligation 9."]

    def get_character_overview(self, slug):
        return {
            "slug": "amelia",
            "full_name": "Amelia Vale",
            "cultural_background": "Anglo (US/UK family line)",
            "public_persona": "manager",
            "hidden_wound": "wound",
            "long_term_desire": "desire",
            "private_fear": "fear",
            "family_expectations": "Protect the family name and contain scandal.",
            "conflict_style": "Calm until forced into blunt clarity.",
            "privacy_boundaries": "Avoids public vulnerability.",
            "value_instincts": "Duty first, loyalty through action.",
            "emotional_expression": "Care through competence and restraint.",
            "message_style": "clipped",
            "ensemble_role": "manager",
            "location_name": "Front Desk",
            "emotional_state": {"current": "guarded"},
            "current_goals": ["hold the room"],
        }

    def list_relationship_snapshots(self, slug):
        return [
            RelationshipSnapshot(
                counterpart_slug="rafael",
                trust_score=8,
                desire_score=8,
                suspicion_score=4,
                obligation_score=9,
                summary="Complicated history.",
            )
        ]

    def get_relevant_facts(self, location_id, limit=6):
        return ["The desk drawers are full of unpaid invoices."]

    def get_forbidden_boundaries(self, character_slug, limit=6):
        return ["Do not reveal hidden recordings without a trigger."]

    def get_story_gravity_state_snapshot(self):
        return StoryGravityStateSnapshot(
            north_star_objective="Keep the house tied to debt, records, and unstable attraction.",
            active_axes=["hidden-records", "house-survival"],
            dormant_threads=[
                DormantThreadSnapshot(
                    thread_key="closet-blackout",
                    summary="Amelia and Rafael were trapped in the records closet once.",
                    heat=7,
                )
            ],
            manager_guardrails=["The house itself must always matter."],
        )

    def list_recent_public_turn_reviews(self, limit=4):
        return [
            {
                "speaker_slug": "amelia",
                "critic_score": 68,
                "clip_value": 7,
                "fandom_discussion_value": 8,
                "reasons": ["Low-value line."],
            }
        ]

    def list_recent_recap_quality_scores(self, limit=3):
        return [
            {
                "summary_window": "1h",
                "clarity": 4,
                "next_hook_strength": 4,
                "issues": ["Recap language is getting generic."],
            }
        ]

    def list_dormant_threads(self, limit=4):
        return [
            DormantThreadSnapshot(
                thread_key="closet-blackout",
                summary="Amelia and Rafael were trapped in the records closet once.",
                heat=7,
            )
        ]


def test_context_assembler_builds_packets() -> None:
    assembler = ContextAssembler(FakeRepository(), PacingHealthEvaluator())
    manager_packet = assembler.build_manager_packet(
        audience_control=AudienceControlReport(
            active=True,
            file_status="active",
            requests=["Build a believable baby path for Amelia and Rafael."],
        )
    )
    character_packet = assembler.build_character_packet(
        "amelia",
        {
            "objective": "Push the scene toward a sharper question.",
            "per_character": {
                "amelia": {
                    "goal": "control the damage",
                    "pressure_point": "Hana is back",
                }
            },
        },
    )
    assert manager_packet.title == "Lantern House"
    assert "Amelia Vale" in manager_packet.cast_guidance[0]
    assert manager_packet.story_gravity
    assert manager_packet.story_gravity_state.north_star_objective
    assert manager_packet.viewer_value_targets
    assert "Who hid the ledger?" in manager_packet.unresolved_questions
    assert manager_packet.payoff_threads
    assert manager_packet.recap_quality_alerts
    assert manager_packet.public_turn_review_signals
    assert manager_packet.audience_control.active is True
    assert character_packet.character_slug == "amelia"
    assert character_packet.voice_guardrails
    assert "control the damage" in character_packet.manager_directive
