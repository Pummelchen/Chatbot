from __future__ import annotations

import re
from collections import Counter

from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    ContinuityFlagDraft,
    EventView,
    MessageView,
    PacingHealthReport,
)
from lantern_house.domain.enums import FlagSeverity


class PacingHealthEvaluator:
    def evaluate(
        self, *, messages: list[MessageView], events: list[EventView]
    ) -> PacingHealthReport:
        score = 100
        repetitive = self._is_repetitive(messages)
        mystery_stalled = not any(
            event.event_type in {"clue", "question", "reveal", "threat"} for event in events[-8:]
        )
        romance_stalled = not any(event.event_type == "romance" for event in events[-12:])
        low_progression = not any(event.significance >= 6 for event in events[-12:])
        too_agreeable = self._too_agreeable(messages)

        recommendations: list[str] = []
        if repetitive:
            score -= 25
            recommendations.append(
                "Break the loop with a concrete clue, interruption, or reversal."
            )
        if mystery_stalled:
            score -= 20
            recommendations.append(
                "Push a fresh question, hidden object, or suspicious inconsistency."
            )
        if romance_stalled:
            score -= 12
            recommendations.append("Use unstable intimacy, jealousy, or interrupted vulnerability.")
        if low_progression:
            score -= 20
            recommendations.append("Make at least one turn matter in the next 10 minutes.")
        if too_agreeable:
            score -= 10
            recommendations.append("Increase friction without flattening character loyalty.")

        return PacingHealthReport(
            score=max(0, min(100, score)),
            repetitive=repetitive,
            mystery_stalled=mystery_stalled,
            romance_stalled=romance_stalled,
            low_progression=low_progression,
            too_agreeable=too_agreeable,
            recommendations=recommendations,
        )

    def _is_repetitive(self, messages: list[MessageView]) -> bool:
        normalized = []
        for message in messages[-8:]:
            text = re.sub(r"[^a-z0-9 ]+", "", message.content.lower())
            normalized.append(" ".join(text.split()[:8]))
        return len(normalized) >= 4 and len(set(normalized)) <= max(2, len(normalized) // 2)

    def _too_agreeable(self, messages: list[MessageView]) -> bool:
        if len(messages) < 6:
            return False
        agreeable_markers = ("yes", "right", "okay", "fine", "true", "exactly")
        hits = 0
        for message in messages[-8:]:
            lowered = message.content.lower()
            if any(marker in lowered for marker in agreeable_markers) and "?" not in lowered:
                hits += 1
        return hits >= 5


class ContinuityGuard:
    def review_turn(
        self,
        *,
        packet: CharacterContextPacket,
        directive: dict,
        turn: CharacterTurn,
    ) -> list[ContinuityFlagDraft]:
        flags: list[ContinuityFlagDraft] = []
        word_count = len(turn.public_message.split())
        if word_count > 45:
            flags.append(
                ContinuityFlagDraft(
                    severity=FlagSeverity.WARNING,
                    flag_type="voice-integrity",
                    description=(
                        f"{packet.character_slug} spoke too long for live chat readability."
                    ),
                    related_entity=packet.character_slug,
                )
            )
        if "clipped" in packet.message_style.lower() and word_count > 28:
            flags.append(
                ContinuityFlagDraft(
                    severity=FlagSeverity.INFO,
                    flag_type="voice-integrity",
                    description=f"{packet.character_slug} drifted away from a clipped style.",
                    related_entity=packet.character_slug,
                )
            )
        major_reveals = len(
            [
                event
                for event in turn.event_candidates
                if event.event_type.value in {"reveal", "clue"} and event.significance >= 8
            ]
        )
        if major_reveals > int(directive.get("reveal_budget", 1)):
            flags.append(
                ContinuityFlagDraft(
                    severity=FlagSeverity.WARNING,
                    flag_type="reveal-budget",
                    description="Turn appears to reveal more than the manager budget allows.",
                    related_entity=packet.character_slug,
                )
            )
        lowered = turn.public_message.lower()
        for boundary in packet.forbidden_boundaries:
            keywords = [
                token
                for token in re.findall(r"[a-z]{5,}", boundary.lower())
                if token not in {"reveal", "without", "until", "should"}
            ]
            if keywords and sum(token in lowered for token in keywords[:3]) >= 2:
                flags.append(
                    ContinuityFlagDraft(
                        severity=FlagSeverity.WARNING,
                        flag_type="forbidden-knowledge",
                        description=(
                            f"{packet.character_slug} may be touching "
                            "restricted knowledge too directly."
                        ),
                        related_entity=packet.character_slug,
                    )
                )
                break
        return flags


def summarize_event_types(events: list[EventView]) -> Counter:
    return Counter(event.event_type for event in events)
