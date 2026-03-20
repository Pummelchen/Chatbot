# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from collections import OrderedDict

from lantern_house.domain.contracts import CharacterTurn, EventCandidate
from lantern_house.domain.enums import EventType


class EventExtractor:
    def extract(self, *, speaker_slug: str, turn: CharacterTurn) -> list[EventCandidate]:
        events: OrderedDict[tuple[str, str], EventCandidate] = OrderedDict()
        for event in turn.event_candidates:
            events[(event.event_type.value, event.title)] = event

        if turn.new_questions:
            for question in turn.new_questions:
                event = EventCandidate(
                    event_type=EventType.QUESTION,
                    title=f"New question from {speaker_slug}",
                    details=question,
                    significance=5,
                    tags=["question"],
                )
                events[(event.event_type.value, event.title + question)] = event

        if turn.relationship_updates and not any(
            event.event_type == EventType.RELATIONSHIP for event in events.values()
        ):
            event = EventCandidate(
                event_type=EventType.RELATIONSHIP,
                title=f"Relationship shift around {speaker_slug}",
                details=turn.relationship_updates[0].summary,
                significance=6,
                tags=["relationship"],
            )
            events[(event.event_type.value, event.title)] = event

        if "?" in turn.public_message and not turn.new_questions:
            event = EventCandidate(
                event_type=EventType.QUESTION,
                title=f"Suspicion sharpened by {speaker_slug}",
                details=turn.public_message,
                significance=4,
                tags=["dialogue-question"],
            )
            events[(event.event_type.value, event.title)] = event

        return list(events.values())
