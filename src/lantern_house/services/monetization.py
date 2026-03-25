# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import MonetizationConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import (
    CharacterTurn,
    HighlightPackageSnapshot,
    MonetizationPackageSnapshot,
    StrategicBriefSnapshot,
    TurnCriticReport,
)
from lantern_house.utils.time import ensure_utc, utcnow


class MonetizationPackagingService:
    def __init__(self, repository: StoryRepository, config: MonetizationConfig) -> None:
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
        highlight_package: HighlightPackageSnapshot | None,
        programming_grid_digest: list[str],
        now=None,
    ) -> MonetizationPackageSnapshot | None:
        if not self.config.enabled:
            return None
        score = _package_score(report=report, highlight_package=highlight_package)
        if score < self.config.min_package_score:
            return None
        now = ensure_utc(now or utcnow())
        ship_angle = highlight_package.ship_angle if highlight_package else _ship_angle(turn)
        theory_angle = (
            highlight_package.theory_angle if highlight_package else _theory_angle(turn)
        )
        betrayal_angle = _betrayal_angle(turn)
        tags = _tags(
            speaker_slug=speaker_slug,
            turn=turn,
            ship_angle=ship_angle,
            theory_angle=theory_angle,
            betrayal_angle=betrayal_angle,
        )
        comment_prompt = _comment_prompt(
            ship_angle=ship_angle,
            theory_angle=theory_angle,
            betrayal_angle=betrayal_angle,
        )
        chapter_label = _chapter_label(programming_grid_digest)
        package = MonetizationPackageSnapshot(
            message_id=message_id,
            highlight_message_id=highlight_package.message_id if highlight_package else message_id,
            speaker_slug=speaker_slug,
            primary_title=(
                highlight_package.title
                if highlight_package
                else f"{speaker_slug.title()} just shifted the room"
            ),
            alternate_titles=[
                *(
                    highlight_package.alternate_titles[:2]
                    if highlight_package
                    else [
                        f"Why viewers are picking sides after {speaker_slug.title()}",
                        f"{speaker_slug.title()} just gave the hour a new hook",
                    ]
                ),
                "What this changes at Lantern House tonight",
            ][:3],
            short_title_options=[
                f"{speaker_slug.title()} just raised the stakes",
                "This changes the ship map",
                "The house just got more dangerous",
            ],
            hook_line=(
                highlight_package.hook_line
                if highlight_package
                else turn.public_message[:180]
            ),
            quote_line=(
                highlight_package.quote_line
                if highlight_package
                else turn.public_message[:180]
            ),
            summary_blurb=(
                highlight_package.summary_blurb
                if highlight_package
                else (
                    turn.event_candidates[0].details
                    if turn.event_candidates
                    else turn.public_message
                )
            )[:220],
            recap_blurb=_recap_blurb(turn=turn, strategic_brief=strategic_brief),
            chapter_label=chapter_label,
            comment_prompt=comment_prompt,
            ship_angle=ship_angle,
            theory_angle=theory_angle,
            betrayal_angle=betrayal_angle,
            faction_labels=_faction_labels(
                ship_angle=ship_angle,
                theory_angle=theory_angle,
                betrayal_angle=betrayal_angle,
            ),
            tags=tags,
            recommended_clip_start_seconds=0,
            recommended_clip_end_seconds=max(
                self.config.min_clip_seconds,
                min(
                    self.config.max_clip_seconds,
                    (highlight_package.recommended_clip_seconds if highlight_package else 20),
                ),
            ),
            score=score,
            metadata={
                "strategic_title": strategic_brief.title if strategic_brief else "",
                "grid_signals": programming_grid_digest[:3],
                "critic_reasons": report.reasons,
                "generated_at": now.isoformat(),
            },
            created_at=now,
        )
        return self.repository.record_monetization_package(package=package, now=now)


def _package_score(
    *,
    report: TurnCriticReport,
    highlight_package: HighlightPackageSnapshot | None,
) -> int:
    highlight_score = highlight_package.score if highlight_package else 0
    return min(
        100,
        highlight_score
        + report.clip_value * 2
        + report.quote_worthiness * 2
        + report.fandom_discussion_value * 2
        + report.novelty,
    )


def _ship_angle(turn: CharacterTurn) -> str:
    for update in turn.relationship_updates:
        if update.desire_delta > 0:
            return f"{update.character_slug} ship pressure"
    return ""


def _theory_angle(turn: CharacterTurn) -> str:
    if turn.new_questions:
        return turn.new_questions[0][:140]
    for event in turn.event_candidates:
        if event.event_type.value in {"clue", "reveal", "question"}:
            return event.title[:140]
    return ""


def _betrayal_angle(turn: CharacterTurn) -> str:
    for event in turn.event_candidates:
        if event.event_type.value in {"conflict", "threat", "alliance"}:
            return event.title[:140]
    return ""


def _tags(
    *,
    speaker_slug: str,
    turn: CharacterTurn,
    ship_angle: str,
    theory_angle: str,
    betrayal_angle: str,
) -> list[str]:
    tags = ["lantern-house", speaker_slug]
    if ship_angle:
        tags.append("ship-war")
    if theory_angle:
        tags.append("fan-theory")
    if betrayal_angle:
        tags.append("betrayal-watch")
    tags.extend(event.event_type.value for event in turn.event_candidates[:2])
    unique: list[str] = []
    for tag in tags:
        compact = tag.strip().lower().replace(" ", "-")
        if compact and compact not in unique:
            unique.append(compact)
    return unique[:8]


def _comment_prompt(*, ship_angle: str, theory_angle: str, betrayal_angle: str) -> str:
    if theory_angle:
        return "Who do you think is hiding the next piece of the truth?"
    if ship_angle:
        return "Who is handling this slow-burn situation worst right now?"
    if betrayal_angle:
        return "Whose side would you trust after this move?"
    return "What would you watch for next if you just joined the stream?"


def _chapter_label(programming_grid_digest: list[str]) -> str:
    if programming_grid_digest:
        return programming_grid_digest[0][:120]
    return "Live escalation"


def _recap_blurb(
    *,
    turn: CharacterTurn,
    strategic_brief: StrategicBriefSnapshot | None,
) -> str:
    if turn.event_candidates:
        return turn.event_candidates[0].title[:200]
    if strategic_brief and strategic_brief.next_one_hour_intention:
        return strategic_brief.next_one_hour_intention[:200]
    return turn.public_message[:200]


def _faction_labels(*, ship_angle: str, theory_angle: str, betrayal_angle: str) -> list[str]:
    labels: list[str] = []
    if ship_angle:
        labels.append("shipping")
    if theory_angle:
        labels.append("theory")
    if betrayal_angle:
        labels.append("betrayal")
    if not labels:
        labels.append("reentry")
    return labels[:3]
