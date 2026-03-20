from __future__ import annotations

from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import AudienceControlReport, CharacterTurn
from lantern_house.utils.time import ensure_utc, utcnow


class StoryBeatService:
    def __init__(self, repository: StoryRepository) -> None:
        self.repository = repository

    def sync_audience_rollout(self, report: AudienceControlReport, *, now=None) -> None:
        now = ensure_utc(now or utcnow())
        if report.active and report.beat_hints:
            self.repository.sync_beats(
                beat_type="audience-rollout",
                items=report.beat_hints,
                source_key="audience-control",
                now=now,
            )
            return
        self.repository.sync_beats(
            beat_type="audience-rollout",
            items=[],
            source_key="audience-control",
            now=now,
        )

    def reconcile_turn(self, *, turn: CharacterTurn, events, now=None) -> None:
        now = ensure_utc(now or utcnow())
        texts = [turn.public_message]
        texts.extend(turn.new_questions)
        texts.extend(turn.answered_questions)
        texts.extend(event.title for event in events)
        texts.extend(event.details for event in events)
        self.repository.complete_matching_beats(texts=texts, now=now)
