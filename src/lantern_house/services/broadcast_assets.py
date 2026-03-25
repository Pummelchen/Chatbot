# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import BroadcastAssetsConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import (
    BroadcastAssetSnapshot,
    CharacterTurn,
    HighlightPackageSnapshot,
    MonetizationPackageSnapshot,
    StrategicBriefSnapshot,
    TurnCriticReport,
    ViewerSignalSnapshot,
)
from lantern_house.utils.time import ensure_utc, utcnow


class BroadcastAssetService:
    def __init__(self, repository: StoryRepository, config: BroadcastAssetsConfig) -> None:
        self.repository = repository
        self.config = config

    def maybe_record(
        self,
        *,
        message_id: int | None,
        speaker_slug: str,
        turn: CharacterTurn,
        report: TurnCriticReport,
        highlight_package: HighlightPackageSnapshot | None,
        monetization_package: MonetizationPackageSnapshot | None,
        strategic_brief: StrategicBriefSnapshot | None,
        viewer_signals: list[ViewerSignalSnapshot],
        now=None,
    ) -> BroadcastAssetSnapshot | None:
        if not self.config.enabled:
            return None
        score = _asset_score(
            report=report,
            highlight_package=highlight_package,
            monetization_package=monetization_package,
            viewer_signals=viewer_signals,
        )
        if score < self.config.min_asset_score:
            return None
        now = ensure_utc(now or utcnow())
        primary_title = (
            monetization_package.primary_title
            if monetization_package is not None
            else highlight_package.title
            if highlight_package is not None
            else f"{speaker_slug.title()} just changed the room"
        )
        hook_line = (
            monetization_package.hook_line
            if monetization_package is not None
            else highlight_package.hook_line
            if highlight_package is not None
            else turn.public_message[:180]
        )
        recap_blurb = (
            monetization_package.recap_blurb
            if monetization_package is not None
            else highlight_package.summary_blurb
            if highlight_package is not None
            else turn.public_message[:180]
        )
        why_it_matters = (
            strategic_brief.viewer_value_thesis[:220]
            if strategic_brief and strategic_brief.viewer_value_thesis
            else recap_blurb
        )
        ship_labels = _labels_from_angle(
            monetization_package.ship_angle if monetization_package else ""
        )
        theory_labels = _labels_from_angle(
            monetization_package.theory_angle if monetization_package else ""
        )
        faction_labels = (
            monetization_package.faction_labels[:] if monetization_package else ["reentry"]
        )
        tags = list((monetization_package.tags if monetization_package else [])[:8])
        tags.extend(signal.signal_type for signal in viewer_signals[:2] if signal.signal_type)
        unique_tags: list[str] = []
        for item in tags:
            compact = str(item).strip().lower()
            if compact and compact not in unique_tags:
                unique_tags.append(compact)
        package = BroadcastAssetSnapshot(
            message_id=message_id,
            monetization_message_id=(
                monetization_package.message_id if monetization_package else message_id
            ),
            speaker_slug=speaker_slug,
            asset_title=primary_title,
            hook_line=hook_line[:220],
            short_description=recap_blurb[:220],
            long_description=[
                recap_blurb[:220],
                why_it_matters[:220],
                _watch_next(strategic_brief=strategic_brief, turn=turn)[:220],
            ],
            chapter_markers=[
                _chapter_marker("Hook", hook_line),
                _chapter_marker("Shift", recap_blurb),
                _chapter_marker(
                    "Watch Next", _watch_next(strategic_brief=strategic_brief, turn=turn)
                ),
            ],
            clip_manifest=[
                {
                    "title": primary_title[:160],
                    "start_seconds": (
                        monetization_package.recommended_clip_start_seconds
                        if monetization_package
                        else 0
                    ),
                    "end_seconds": (
                        monetization_package.recommended_clip_end_seconds
                        if monetization_package
                        else max(
                            18,
                            min(
                                50,
                                (
                                    highlight_package.recommended_clip_seconds
                                    if highlight_package
                                    else 24
                                ),
                            ),
                        )
                    ),
                    "hook": hook_line[:180],
                    "quote": (
                        monetization_package.quote_line
                        if monetization_package
                        else highlight_package.quote_line
                        if highlight_package
                        else turn.public_message[:180]
                    )[:180],
                    "angle": _asset_angle(monetization_package=monetization_package, turn=turn),
                }
            ],
            ship_labels=ship_labels,
            theory_labels=theory_labels,
            faction_labels=faction_labels[:4],
            tags=unique_tags[:10],
            why_it_matters=why_it_matters[:240],
            comment_seed=(
                monetization_package.comment_prompt
                if monetization_package
                else "What would you watch for next if you just joined?"
            )[:220],
            asset_score=score,
            metadata={
                "viewer_signals": [
                    {
                        "type": signal.signal_type,
                        "subject": signal.subject,
                        "impact": signal.retention_impact,
                    }
                    for signal in viewer_signals[:3]
                ],
                "strategic_title": strategic_brief.title if strategic_brief else "",
                "critic_reasons": report.reasons,
                "speaker_slug": speaker_slug,
            },
            created_at=now,
        )
        return self.repository.record_broadcast_asset(package=package, now=now)


def _asset_score(
    *,
    report: TurnCriticReport,
    highlight_package: HighlightPackageSnapshot | None,
    monetization_package: MonetizationPackageSnapshot | None,
    viewer_signals: list[ViewerSignalSnapshot],
) -> int:
    base = (
        (monetization_package.score if monetization_package else 0)
        + (highlight_package.score if highlight_package else 0) // 2
        + report.clip_value * 2
        + report.quote_worthiness * 2
        + report.fandom_discussion_value * 2
    )
    if viewer_signals:
        base += max(signal.retention_impact for signal in viewer_signals[:3])
    return min(100, base)


def _labels_from_angle(angle: str) -> list[str]:
    text = " ".join(angle.split())
    if not text:
        return []
    return [text[:60]]


def _watch_next(*, strategic_brief: StrategicBriefSnapshot | None, turn: CharacterTurn) -> str:
    if strategic_brief and strategic_brief.next_one_hour_intention:
        return strategic_brief.next_one_hour_intention
    if turn.new_questions:
        return f"Watch next: {turn.new_questions[0]}"
    return "Watch next: the next interruption, clue, or loyalty fracture."


def _chapter_marker(label: str, value: str) -> str:
    compact = " ".join(value.split())
    return f"{label}: {compact[:100]}"


def _asset_angle(
    *,
    monetization_package: MonetizationPackageSnapshot | None,
    turn: CharacterTurn,
) -> str:
    if monetization_package and monetization_package.theory_angle:
        return "theory"
    if monetization_package and monetization_package.ship_angle:
        return "ship"
    if any(event.event_type.value in {"conflict", "threat"} for event in turn.event_candidates):
        return "betrayal"
    return "reentry"
