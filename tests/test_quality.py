from __future__ import annotations

from datetime import timedelta

from lantern_house.domain.contracts import CharacterContextPacket, CharacterTurn, EventCandidate, MessageView
from lantern_house.domain.enums import EventType
from lantern_house.quality.pacing import ContinuityGuard, PacingHealthEvaluator
from lantern_house.utils.time import utcnow


def test_pacing_health_detects_repetition_and_stall() -> None:
    now = utcnow()
    messages = [
        MessageView(speaker_label="Mara", content="Fine. Fine. Fine.", kind="chat", created_at=now - timedelta(seconds=i))
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
        public_message="This is an intentionally overlong message that keeps talking far beyond the natural rhythm of a live group chat and also plainly mentions hidden recordings because the test needs to trigger multiple flags in one review pass.",
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

