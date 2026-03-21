# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import RuntimeConfig
from lantern_house.domain.contracts import (
    AudienceControlReport,
    CharacterContextPacket,
    CharacterTurn,
    EventCandidate,
    EventView,
    ManagerContextPacket,
    MessageView,
    PacingHealthReport,
    SummaryView,
)
from lantern_house.domain.enums import EventType
from lantern_house.quality.governance import StoryGovernanceEvaluator
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
        character_slug="amelia",
        full_name="Amelia Vale",
        cultural_background="Anglo (US/UK family line)",
        public_persona="manager",
        hidden_wound="wound",
        long_term_desire="desire",
        private_fear="fear",
        family_expectations="Protect the family name and contain scandal.",
        conflict_style="Calm until forced into blunt clarity.",
        privacy_boundaries="Avoids public vulnerability.",
        value_instincts="Duty first, loyalty through action.",
        emotional_expression="Care through competence and restraint.",
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


def test_continuity_guard_flags_robotic_voice() -> None:
    packet = CharacterContextPacket(
        character_slug="amelia",
        full_name="Amelia Vale",
        cultural_background="Anglo (US/UK family line)",
        public_persona="manager",
        hidden_wound="wound",
        long_term_desire="desire",
        private_fear="fear",
        family_expectations="Protect the family name and contain scandal.",
        conflict_style="Calm until forced into blunt clarity.",
        privacy_boundaries="Avoids public vulnerability.",
        value_instincts="Duty first, loyalty through action.",
        emotional_expression="Care through competence and restraint.",
        message_style="Clipped and dry",
        ensemble_role="House Manager",
        current_location="Front Desk",
        voice_guardrails=["Prefer concrete details over speeches."],
        emotional_state={"current": "guarded"},
        current_goals=["protect the house"],
        relationship_snapshots=[],
        recent_messages=[],
        relevant_facts=["Invoices are stacked under the desk."],
        recent_events=[],
        manager_directive="Objective: keep the scene moving.",
        forbidden_boundaries=[],
    )
    turn = CharacterTurn(public_message="The truth is we both know this changes everything.")
    flags = ContinuityGuard().review_turn(packet=packet, directive={"reveal_budget": 1}, turn=turn)
    assert "robotic-voice" in {flag.flag_type for flag in flags}


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
                "character_slug": "amelia",
                "trust_delta": "-2",
                "suspicion_delta": 4,
            }
        ],
    }
    coerced = service._coerce_payload(payload)
    update = coerced["relationship_updates"][0]
    assert update["summary"] == "Tension shifted around amelia."
    assert update["trust_delta"] == -2
    assert update["suspicion_delta"] == 3


def test_character_service_filters_fragment_questions() -> None:
    service = CharacterService.__new__(CharacterService)
    turn = CharacterTurn(
        public_message="Watch the desk, not me.",
        new_questions=[
            "the exact nature of the mystery",
            "Where did the copied codicil go",
            "none",
        ],
        answered_questions=["none", "How much of the debt is real"],
    )
    sanitized = service._sanitize(turn, thought_pulse_allowed=False)
    assert sanitized.new_questions == ["Where did the copied codicil go?"]
    assert sanitized.answered_questions == ["How much of the debt is real?"]


def test_character_service_drops_placeholder_thought_pulse() -> None:
    service = CharacterService.__new__(CharacterService)
    turn = CharacterTurn(
        public_message="Watch the desk, not me.",
        thought_pulse="rare",
    )
    sanitized = service._sanitize(turn, thought_pulse_allowed=True)
    assert sanitized.thought_pulse is None


def test_character_service_detects_template_leak() -> None:
    service = CharacterService.__new__(CharacterService)
    turn = CharacterTurn(public_message="the visible message")
    assert service._looks_like_template_leak(turn) is True


def test_manager_normalize_respects_active_character_bounds() -> None:
    service = StoryManagerService(
        llm=None,
        model_name="gemma3:4b",
        runtime_config=RuntimeConfig(active_character_min=2, active_character_max=3),
    )
    context = ManagerContextPacket(
        title="Lantern House",
        scene_objective="Hold the line.",
        scene_location="Front Desk",
        emotional_temperature=6,
        cast_guidance=["amelia / Amelia Vale: Anglo anchor. Family pressure: legacy."],
        pacing_health=PacingHealthReport(score=50),
    )
    plan = service._fallback(
        context=context,
        roster=["amelia", "rafael", "arjun", "ayu"],
    )
    normalized = service._normalize(
        plan.model_copy(update={"active_character_slugs": ["amelia"]}),
        ["amelia", "rafael", "arjun", "ayu"],
    )
    assert 2 <= len(normalized.active_character_slugs) <= 3
    assert "amelia" in normalized.active_character_slugs


def test_manager_fallback_uses_audience_control_requests() -> None:
    service = StoryManagerService(
        llm=None,
        model_name="gemma3:4b",
        runtime_config=RuntimeConfig(active_character_min=2, active_character_max=3),
    )
    context = ManagerContextPacket(
        title="Lantern House",
        scene_objective="Hold the line.",
        scene_location="Front Desk",
        emotional_temperature=6,
        cast_guidance=["amelia / Amelia Vale: Anglo anchor. Family pressure: legacy."],
        pacing_health=PacingHealthReport(score=70),
        audience_control=AudienceControlReport(
            active=True,
            file_status="active",
            requests=["Build a believable baby path for Amelia and Rafael."],
            tone_dials={"romance": 9},
            directives=["Roll out gradually over 24 hours."],
        ),
    )
    plan = service._fallback(
        context=context,
        roster=["amelia", "rafael", "arjun"],
    )
    assert "audience-voted change" in plan.objective.lower()
    assert "baby path" in plan.desired_developments[0].lower()


def test_story_governance_detects_hourly_progression_gap_and_voice_risk() -> None:
    now = utcnow()
    messages = [
        MessageView(
            speaker_label="Amelia",
            content="The truth is we both know this changes everything.",
            kind="chat",
            created_at=now - timedelta(minutes=4),
        ),
        MessageView(
            speaker_label="Rafael",
            content="The truth is we both know this changes everything.",
            kind="chat",
            created_at=now - timedelta(minutes=3),
        ),
        MessageView(
            speaker_label="Lucía",
            content="The truth is we both know this changes everything.",
            kind="chat",
            created_at=now - timedelta(minutes=2),
        ),
        MessageView(
            speaker_label="Arjun",
            content="The truth is we both know this changes everything.",
            kind="chat",
            created_at=now - timedelta(minutes=1),
        ),
    ]
    events = [
        EventView(
            event_type="routine",
            title="Tea was served",
            details="The kitchen stayed calm.",
            significance=3,
            payload={},
            created_at=now - timedelta(minutes=20),
        )
    ]
    report = StoryGovernanceEvaluator().evaluate(
        messages=messages,
        events=events,
        summaries=[
            SummaryView(
                summary_window="1h",
                content=(
                    "The truth is this changes everything | "
                    "The truth is this changes everything"
                ),
                structured_highlights={},
                bucket_end_at=now,
            )
        ],
        world_metadata={
            "story_engine": {
                "core_tensions": [
                    {"key": "house-survival", "keywords": ["debt", "sale"]},
                    {"key": "hidden-records", "keywords": ["ledger", "archive"]},
                ]
            }
        },
        unresolved_questions=["Who moved the archive?"],
    )
    assert report.hourly_progression_met is False
    assert report.robotic_voice_risk is True
    assert report.core_drift is True
    assert report.viewer_value_score < 70


def test_continuity_guard_flags_chat_register_drift() -> None:
    packet = CharacterContextPacket(
        character_slug="arjun",
        full_name="Arjun Mehta",
        cultural_background="Indian",
        public_persona="observer",
        hidden_wound="wound",
        long_term_desire="desire",
        private_fear="fear",
        family_expectations="Be respectable and measured.",
        conflict_style="Quietly incisive.",
        privacy_boundaries="Deflects direct exposure.",
        value_instincts="Protect dignity before spectacle.",
        emotional_expression="Controlled warmth and sharp observation.",
        message_style="Measured and dry",
        ensemble_role="Long-Term Guest / Observer",
        current_location="Front Desk",
        voice_guardrails=["Keep it chatty, not literary."],
        emotional_state={"current": "watchful"},
        current_goals=["push the scene"],
        relationship_snapshots=[],
        recent_messages=[],
        relevant_facts=[],
        recent_events=[],
        manager_directive="Objective: keep pressure up.",
        forbidden_boundaries=[],
    )
    turn = CharacterTurn(
        public_message=(
            "The reception counter's card reader is buzzing like a trapped beetle. "
            "It's a pattern I've observed for weeks, a subtle rhythm of hurried departures."
        )
    )
    flags = ContinuityGuard().review_turn(packet=packet, directive={"reveal_budget": 1}, turn=turn)
    assert "chat-register" in {flag.flag_type for flag in flags}
