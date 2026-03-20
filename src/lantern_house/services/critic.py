from __future__ import annotations

import re
from collections.abc import Iterable

from lantern_house.config import CriticConfig
from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    ContinuityFlagDraft,
    TurnCriticReport,
)


class TurnCriticService:
    _GENERIC_MARKERS = (
        "the truth is",
        "this changes everything",
        "we both know",
        "you don't understand",
        "it's not that simple",
    )
    _NARRATIVE_MARKERS = (
        "i've observed",
        "a subtle rhythm",
        "the room was",
        "the air was",
        "it felt like",
    )
    _PLACEHOLDER_MARKERS = (
        "visible message",
        "public message",
        "short event title",
        "why the relationship shifted",
    )

    def __init__(self, config: CriticConfig) -> None:
        self.config = config

    def review(
        self,
        *,
        packet: CharacterContextPacket,
        turn: CharacterTurn,
        flags: list[ContinuityFlagDraft],
    ) -> TurnCriticReport:
        if not self.config.enabled:
            return TurnCriticReport()

        score = 100
        reasons: list[str] = []
        message = " ".join(turn.public_message.split())
        lowered = message.lower()
        words = message.split()

        if any(marker in lowered for marker in self._PLACEHOLDER_MARKERS):
            score -= 55
            reasons.append("The turn leaked placeholder or template language.")
        if len(words) > 38:
            score -= 18
            reasons.append("The turn is too long for fast live-chat readability.")
        if any(marker in lowered for marker in self._GENERIC_MARKERS):
            score -= 15
            reasons.append("The turn is leaning on generic confrontation language.")
        if any(marker in lowered for marker in self._NARRATIVE_MARKERS):
            score -= 14
            reasons.append("The turn reads like prose narration instead of chat.")
        if self._missing_grounding(packet=packet, message=lowered):
            score -= 16
            reasons.append("The turn is not grounded in house specifics, people, or objects.")
        if self._low_progress_value(turn):
            score -= 16
            reasons.append("The turn does not create enough visible progression.")
        if self._repeats_recent_language(packet.recent_messages, lowered):
            score -= 12
            reasons.append("The turn repeats recent language too closely.")

        repairable_flag_types = {"robotic-voice", "chat-register", "voice-integrity"}
        if any(flag.flag_type in repairable_flag_types for flag in flags):
            score -= 14
            reasons.append("Rule-based guards already see a voice or register problem.")

        return TurnCriticReport(
            score=max(0, min(100, score)),
            reasons=reasons[:4],
            should_repair=score < self.config.repair_threshold,
        )

    def is_hard_failure(self, report: TurnCriticReport) -> bool:
        return report.score < self.config.hard_fail_threshold

    def _missing_grounding(self, *, packet: CharacterContextPacket, message: str) -> bool:
        grounding_terms = set(_extract_terms(packet.current_location))
        grounding_terms.update(
            token
            for item in (
                *packet.relevant_facts[:3],
                *packet.live_pressures[:2],
                *packet.relationship_snapshots[:2],
            )
            for token in _extract_terms(item)
        )
        if not grounding_terms:
            return False
        return not any(term in message for term in grounding_terms)

    def _low_progress_value(self, turn: CharacterTurn) -> bool:
        if turn.new_questions or turn.answered_questions:
            return False
        if any(event.significance >= 5 for event in turn.event_candidates):
            return False
        if any(
            abs(delta.trust_delta)
            + abs(delta.desire_delta)
            + abs(delta.suspicion_delta)
            + abs(delta.obligation_delta)
            >= 2
            for delta in turn.relationship_updates
        ):
            return False
        return "?" not in turn.public_message and len(turn.public_message.split()) < 10

    def _repeats_recent_language(self, recent_messages: list[str], message: str) -> bool:
        if not recent_messages:
            return False
        normalized_message = _normalize_text(message)
        recent = [_normalize_text(item) for item in recent_messages[-3:]]
        return any(
            normalized_message == candidate or normalized_message[:35] == candidate[:35]
            for candidate in recent
            if candidate
        )


def _extract_terms(text: str) -> Iterable[str]:
    return [
        token
        for token in re.findall(r"[a-z]{4,}", text.lower())
        if token not in {"trust", "desire", "suspicion", "obligation"}
    ]


def _normalize_text(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", text.lower()).split())
