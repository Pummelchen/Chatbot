# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import HighlightsConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import (
    CharacterTurn,
    HighlightPackageSnapshot,
    StrategicBriefSnapshot,
    TurnCriticReport,
)
from lantern_house.utils.time import ensure_utc, utcnow


class HighlightPackagingService:
    def __init__(self, repository: StoryRepository, config: HighlightsConfig) -> None:
        self.repository = repository
        self.config = config

    def maybe_record(
        self,
        *,
        message_id: int | None,
        speaker_slug: str,
        turn: CharacterTurn,
        report: TurnCriticReport,
        strategic_brief: StrategicBriefSnapshot | None,
        now=None,
    ) -> HighlightPackageSnapshot | None:
        if not self.config.enabled:
            return None
        if (
            report.clip_value < self.config.clip_threshold
            and report.quote_worthiness < self.config.quote_threshold
        ):
            return None
        now = ensure_utc(now or utcnow())
        ship_angle = _ship_angle(turn)
        theory_angle = _theory_angle(turn)
        conflict_axis = _conflict_axis(turn)
        hook_line = turn.public_message[:180]
        event_summary = (
            turn.event_candidates[0].details if turn.event_candidates else turn.public_message
        )
        strategic_title = strategic_brief.title if strategic_brief else ""
        score = min(
            100,
            report.clip_value * 8
            + report.quote_worthiness * 6
            + report.fandom_discussion_value * 5
            + report.novelty * 4,
        )
        title = _title(
            speaker_slug=speaker_slug,
            ship_angle=ship_angle,
            theory_angle=theory_angle,
            conflict_axis=conflict_axis,
        )
        package = HighlightPackageSnapshot(
            message_id=message_id,
            speaker_slug=speaker_slug,
            title=title,
            alternate_titles=[
                f"{speaker_slug.title()} just raised the price of tonight",
                f"Why viewers will argue about {speaker_slug.title()} next",
            ],
            hook_line=hook_line,
            quote_line=turn.public_message[:220],
            summary_blurb=event_summary[:220],
            ship_angle=ship_angle,
            theory_angle=theory_angle,
            conflict_axis=conflict_axis,
            recommended_clip_seconds=max(15, min(45, 15 + report.clip_value * 2)),
            source_window_minutes=4,
            score=score,
            metadata={
                "strategic_title": strategic_title,
                "reasons": report.reasons,
                "event_types": [event.event_type.value for event in turn.event_candidates],
                "generated_at": now.isoformat(),
            },
        )
        return self.repository.record_highlight_package(package=package, now=now)


def _ship_angle(turn: CharacterTurn) -> str:
    for update in turn.relationship_updates:
        if update.desire_delta != 0:
            return f"{update.character_slug} shipping tension"
    if any(event.event_type.value == "romance" for event in turn.event_candidates):
        return "slow-burn romance pressure"
    return ""


def _theory_angle(turn: CharacterTurn) -> str:
    if turn.new_questions:
        return turn.new_questions[0][:160]
    for event in turn.event_candidates:
        if event.event_type.value in {"clue", "reveal", "question"}:
            return event.title[:160]
    return ""


def _conflict_axis(turn: CharacterTurn) -> str:
    if turn.event_candidates:
        return turn.event_candidates[0].event_type.value
    return "chat"


def _title(
    *,
    speaker_slug: str,
    ship_angle: str,
    theory_angle: str,
    conflict_axis: str,
) -> str:
    if ship_angle:
        return f"{speaker_slug.title()} just fed the ship war"
    if theory_angle:
        return f"{speaker_slug.title()} just handed viewers a new theory"
    if conflict_axis == "financial":
        return f"{speaker_slug.title()} just made the house crisis worse"
    if conflict_axis in {"threat", "conflict"}:
        return f"{speaker_slug.title()} just changed the balance of power"
    return f"{speaker_slug.title()} just gave the hour its hook"
