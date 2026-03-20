from __future__ import annotations

from datetime import timedelta

from lantern_house.config import RuntimeConfig
from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    EventCandidate,
    ManagerContextPacket,
    MessageView,
    PacingHealthReport,
)
from lantern_house.domain.enums import EventType
from lantern_house.quality.pacing import ContinuityGuard, PacingHealthEvaluator
from lantern_house.services.character import CharacterService
from lantern_house.services.manager import StoryManagerService
from lantern_house.utils.time import utcnow


def test_pacing_health_detects_repetition_and_stall() -> None:
    now = utcnow()
    messages = [
        MessageView(
            speaker_label="Mara",
            content="Fine. Fine. Fine.",
            kind="chat",
            created_at=now - timedelta(seconds=i),
        )
        for i in range(8)
    ]
    report = PacingHealthEvaluator().evaluate(messages=messages, events=[])
    assert report.repetitive is True
    assert report.low_progression is True
    assert report.score < 70


def test_continuity_guard_flags_reveal_budget_and_long_message() -> None:
    packet = CharacterContextPacket(
        character_slug="mara",
        full_name="Mara Dela Cruz",
        public_persona="manager",
        hidden_wound="wound",
        long_term_desire="desire",
        private_fear="fear",
        message_style="Clipped and dry",
        ensemble_role="House Manager",
        current_location="Front Desk",
        emotional_state={"current": "guarded"},
        current_goals=["protect the house"],
        relationship_snapshots=[],
        recent_messages=[],
        relevant_facts=[],
        recent_events=[],
        manager_directive="Objective: keep the scene moving.",
        forbidden_boundaries=["Do not reveal hidden recordings without a trigger."],
    )
    turn = CharacterTurn(
        public_message=(
            "This is an intentionally overlong message that keeps talking far beyond "
            "the natural rhythm of a live group chat and also plainly mentions hidden "
            "recordings because the test needs to trigger multiple flags in one review pass."
        ),
        event_candidates=[
            EventCandidate(
                event_type=EventType.REVEAL,
                title="big reveal",
                details="too much too soon",
                significance=9,
            ),
            EventCandidate(
                event_type=EventType.CLUE,
                title="second clue",
                details="still too much",
                significance=8,
            ),
        ],
    )
    flags = ContinuityGuard().review_turn(packet=packet, directive={"reveal_budget": 1}, turn=turn)
    flag_types = {flag.flag_type for flag in flags}
    assert "voice-integrity" in flag_types
    assert "reveal-budget" in flag_types


def test_character_service_coerces_broken_event_type_hint() -> None:
    service = CharacterService.__new__(CharacterService)
    payload = {
        "public_message": "The key matters more than you're admitting.",
        "event_candidates": [
            {
                "event_type": (
                    "clue|relationship|reveal|question|humor|financial|threat|romance|"
                    "routine|conflict|alliance"
                ),
                "title": "The brass key matters",
                "details": "A hidden key became central to the scene.",
                "significance": 7,
            }
        ],
    }
    coerced = service._coerce_payload(payload)
    assert coerced["event_candidates"][0]["event_type"] == "clue"


def test_character_service_fills_missing_relationship_summary() -> None:
    service = CharacterService.__new__(CharacterService)
    payload = {
        "public_message": "You know why I'm angry.",
        "relationship_updates": [
            {
                "character_slug": "mara",
                "trust_delta": "-2",
                "suspicion_delta": 4,
            }
        ],
    }
    coerced = service._coerce_payload(payload)
    update = coerced["relationship_updates"][0]
    assert update["summary"] == "Tension shifted around mara."
    assert update["trust_delta"] == -2
    assert update["suspicion_delta"] == 3


def test_manager_normalize_respects_active_character_bounds() -> None:
    service = StoryManagerService(
        llm=None,
        model_name="gemma3:4b",
        runtime_config=RuntimeConfig(active_character_min=2, active_character_max=3),
    )
    context = ManagerContextPacket(
        title="Saltglass House",
        scene_objective="Hold the line.",
        scene_location="Front Desk",
        emotional_temperature=6,
        pacing_health=PacingHealthReport(score=50),
    )
    plan = service._fallback(
        context=context,
        roster=["mara", "elias", "soren", "nia"],
    )
    normalized = service._normalize(
        plan.model_copy(update={"active_character_slugs": ["mara"]}),
        ["mara", "elias", "soren", "nia"],
    )
    assert 2 <= len(normalized.active_character_slugs) <= 3
    assert "mara" in normalized.active_character_slugs
