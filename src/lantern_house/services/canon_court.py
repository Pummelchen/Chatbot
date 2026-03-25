# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import re

from lantern_house.config import CanonCourtConfig
from lantern_house.domain.contracts import (
    CanonCourtFindingSnapshot,
    CanonCourtReport,
    CharacterContextPacket,
    CharacterTurn,
    ContinuityFlagDraft,
    EventCandidate,
)
from lantern_house.domain.enums import EventType, FlagSeverity


class CanonCourtService:
    _ABSOLUTE_REVEAL_MARKERS = (
        "case closed",
        "we know exactly",
        "that's the whole truth",
        "it's over",
        "solved",
        "nothing left to hide",
    )
    _ABSOLUTE_TIMELINE_MARKERS = (
        "never",
        "all night",
        "exactly where",
        "could not have",
        "wasn't there",
    )

    def __init__(self, config: CanonCourtConfig) -> None:
        self.config = config

    def review(
        self,
        *,
        packet: CharacterContextPacket,
        turn: CharacterTurn,
        events: list[EventCandidate],
    ) -> CanonCourtReport:
        if not self.config.enabled:
            return CanonCourtReport(
                revised_turn=turn,
                revised_events=events,
                revised_questions=turn.new_questions,
            )

        findings: list[CanonCourtFindingSnapshot] = []
        additional_flags: list[ContinuityFlagDraft] = []
        lowered = turn.public_message.lower()
        restricted_hits = _restricted_hits(
            boundaries=packet.forbidden_boundaries,
            message=lowered,
        )
        if restricted_hits:
            findings.append(
                CanonCourtFindingSnapshot(
                    issue_type="forbidden-truth-bleed",
                    severity="warning",
                    action="soften",
                    summary=(
                        f"{packet.character_slug} is leaning too close to protected truth "
                        "instead of staying in plausible suspicion."
                    ),
                    evidence=restricted_hits[:3],
                )
            )
            additional_flags.append(
                ContinuityFlagDraft(
                    severity=FlagSeverity.WARNING,
                    flag_type="canon-court",
                    description=("The turn leaned too close to protected truth and was softened."),
                    related_entity=packet.character_slug,
                )
            )

        if any(marker in lowered for marker in self._ABSOLUTE_REVEAL_MARKERS):
            findings.append(
                CanonCourtFindingSnapshot(
                    issue_type="premature-finality",
                    severity="critical",
                    action="repair",
                    summary=(
                        "The turn speaks with finality that would collapse the mystery too fast."
                    ),
                    evidence=[
                        marker for marker in self._ABSOLUTE_REVEAL_MARKERS if marker in lowered
                    ],
                )
            )
            additional_flags.append(
                ContinuityFlagDraft(
                    severity=FlagSeverity.CRITICAL,
                    flag_type="canon-court",
                    description="The turn tried to close a mystery lane too completely.",
                    related_entity=packet.character_slug,
                )
            )

        timeline_hits = _timeline_conflicts(
            message=lowered,
            timeline_grounding=packet.timeline_grounding,
            absolute_markers=self._ABSOLUTE_TIMELINE_MARKERS,
        )
        if timeline_hits:
            findings.append(
                CanonCourtFindingSnapshot(
                    issue_type="timeline-certainty",
                    severity="warning",
                    action="soften",
                    summary=(
                        "The turn speaks too confidently about rooms, keys, or alibis that the "
                        "tracking layer only supports as last-known facts."
                    ),
                    evidence=timeline_hits[:3],
                )
            )
            additional_flags.append(
                ContinuityFlagDraft(
                    severity=FlagSeverity.WARNING,
                    flag_type="timeline-certainty",
                    description="The turn overstated timeline or possession certainty.",
                    related_entity=packet.character_slug,
                )
            )

        revised_turn = turn
        revised_events = list(events)
        revised_questions = list(turn.new_questions)
        requires_repair = any(finding.action == "repair" for finding in findings)

        if findings and not requires_repair:
            revised_turn = _soften_turn(turn=turn, packet=packet)
            revised_events = _soften_events(events)
            revised_questions = _soften_questions(turn.new_questions)

        return CanonCourtReport(
            status="repair" if requires_repair else "softened" if findings else "clean",
            findings=findings[: self.config.max_findings_per_turn],
            additional_flags=additional_flags[: self.config.max_findings_per_turn],
            revised_turn=revised_turn,
            revised_events=revised_events,
            revised_questions=revised_questions,
            requires_repair=requires_repair and self.config.force_repair_on_block,
        )


def _restricted_hits(*, boundaries: list[str], message: str) -> list[str]:
    hits: list[str] = []
    for boundary in boundaries:
        keywords = [
            token
            for token in re.findall(r"[a-z]{5,}", boundary.lower())
            if token not in {"until", "without", "should", "reveal", "about"}
        ]
        matched = [keyword for keyword in keywords[:4] if keyword in message]
        if len(matched) >= 2:
            hits.append(", ".join(matched[:3]))
    return hits


def _soften_turn(*, turn: CharacterTurn, packet: CharacterContextPacket) -> CharacterTurn:
    softened_message = turn.public_message
    replacements = {
        "we know exactly": "something still doesn't add up",
        "case closed": "that is too neat",
        "it's over": "this is getting worse",
        "solved": "closer than I like",
        "nothing left to hide": "someone is still hiding something",
        " copied ": " may have copied ",
        " staged ": " may have staged ",
        " is ": " might be ",
        " was ": " may have been ",
    }
    lowered = softened_message.lower()
    for source, target in replacements.items():
        if source in lowered:
            softened_message = re.sub(source, target, softened_message, flags=re.IGNORECASE)
            lowered = softened_message.lower()
    if softened_message == turn.public_message and turn.public_message.strip():
        softened_message = f"I think {turn.public_message[0].lower()}{turn.public_message[1:]}"
    if not softened_message.strip():
        softened_message = "Something about this still doesn't add up."
    return turn.model_copy(
        update={
            "public_message": softened_message,
            "thought_pulse": turn.thought_pulse,
        }
    )


def _soften_events(events: list[EventCandidate]) -> list[EventCandidate]:
    softened: list[EventCandidate] = []
    for event in events:
        if event.event_type == EventType.REVEAL and event.significance >= 7:
            softened.append(
                event.model_copy(
                    update={
                        "event_type": EventType.QUESTION,
                        "title": f"Suspicion: {event.title}",
                        "details": f"{event.details} The truth is still unconfirmed.",
                        "significance": max(4, min(6, event.significance - 2)),
                    }
                )
            )
            continue
        softened.append(event)
    return softened


def _soften_questions(questions: list[str]) -> list[str]:
    softened: list[str] = []
    for question in questions:
        if any(marker in question.lower() for marker in ("who did it", "what really happened")):
            softened.append(question.replace("really", "actually"))
        else:
            softened.append(question)
    return softened[:3]


def _timeline_conflicts(
    *,
    message: str,
    timeline_grounding: list[str],
    absolute_markers: tuple[str, ...],
) -> list[str]:
    if not timeline_grounding or not any(marker in message for marker in absolute_markers):
        return []
    hits: list[str] = []
    for note in timeline_grounding:
        lowered = note.lower()
        keywords = [
            token
            for token in re.findall(r"[a-z]{4,}", lowered)
            if token not in {"last", "known", "room", "house"}
        ]
        matches = [keyword for keyword in keywords[:4] if keyword in message]
        if matches:
            hits.append(", ".join(matches[:3]))
    return hits[:3]
