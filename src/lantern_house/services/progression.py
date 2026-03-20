from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import ClassVar

from lantern_house.domain.contracts import (
    EventCandidate,
    StoryArcProgressUpdate,
    StoryArcSnapshot,
    StoryProgressionPlan,
)
from lantern_house.domain.enums import EventType
from lantern_house.utils.time import ensure_utc, isoformat, utcnow


class StoryProgressionService:
    _ARC_TYPE_HINTS: ClassVar[dict[str, set[EventType]]] = {
        "central-mystery": {EventType.CLUE, EventType.REVEAL, EventType.QUESTION, EventType.THREAT},
        "mystery": {EventType.CLUE, EventType.REVEAL, EventType.QUESTION, EventType.THREAT},
        "finance": {EventType.FINANCIAL, EventType.THREAT, EventType.CONFLICT, EventType.QUESTION},
        "romance": {
            EventType.ROMANCE,
            EventType.RELATIONSHIP,
            EventType.CONFLICT,
            EventType.ALLIANCE,
        },
    }
    _STOPWORDS: ClassVar[set[str]] = {
        "about",
        "after",
        "again",
        "around",
        "because",
        "before",
        "being",
        "between",
        "could",
        "every",
        "house",
        "inside",
        "keep",
        "keeps",
        "later",
        "might",
        "night",
        "still",
        "their",
        "there",
        "these",
        "they",
        "this",
        "turning",
        "what",
        "when",
        "where",
        "which",
        "while",
        "with",
    }

    def plan(
        self,
        *,
        arcs: list[StoryArcSnapshot],
        events: list[EventCandidate],
        now: datetime | None = None,
    ) -> StoryProgressionPlan:
        if not arcs or not events:
            return StoryProgressionPlan()
        now = ensure_utc(now or utcnow())
        by_slug = {arc.slug: arc for arc in arcs}
        per_arc_stats: dict[str, dict[str, object]] = defaultdict(
            lambda: {"points": 0, "pressure_delta": 0, "titles": [], "surface": False}
        )

        for event in events:
            matched = event.arc_slug if event.arc_slug in by_slug else self._match_arc(arcs, event)
            if matched is None:
                continue
            stats = per_arc_stats[matched]
            stats["points"] = int(stats["points"]) + self._points_for_event(event)
            stats["pressure_delta"] = int(stats["pressure_delta"]) + min(
                2, 1 + int(event.significance >= 8)
            )
            stats["titles"] = [*stats["titles"], event.title][:4]
            if event.significance >= 6:
                stats["surface"] = True

        updates: list[StoryArcProgressUpdate] = []
        surfaced_questions: list[str] = []
        archived_threads: list[str] = []
        for arc in arcs:
            stats = per_arc_stats.get(arc.slug)
            if not stats:
                continue

            metadata = dict(arc.metadata)
            progress_points = _coerce_int(metadata.get("progress_points")) + int(stats["points"])
            stage_index = arc.stage_index
            threshold, cooldown = self._advance_rules(arc)
            if (
                progress_points >= threshold
                and stage_index < max(0, len(arc.reveal_ladder) - 1)
                and self._cooldown_elapsed(metadata.get("last_stage_change_at"), cooldown, now)
            ):
                stage_index += 1
                progress_points -= threshold

            active_beat = (
                arc.reveal_ladder[min(stage_index, len(arc.reveal_ladder) - 1)]
                if arc.reveal_ladder
                else None
            )
            pressure_score = min(10, max(arc.pressure_score, 5) + int(stats["pressure_delta"]))
            titles = [title for title in stats["titles"] if isinstance(title, str)]
            metadata.update(
                {
                    "progress_points": progress_points,
                    "active_beat": active_beat,
                    "recent_progress_titles": titles,
                    "last_progress_at": isoformat(now),
                }
            )
            if stage_index != arc.stage_index:
                metadata["last_stage_change_at"] = isoformat(now)

            per_arc_questions = self._surfaced_questions(
                arc=arc,
                stage_index=stage_index,
                should_surface=bool(stats["surface"]),
            )
            per_arc_threads = (
                [f"{arc.title}: {active_beat}"]
                if active_beat and stage_index != arc.stage_index
                else []
            )
            surfaced_questions.extend(per_arc_questions)
            archived_threads.extend(per_arc_threads)
            updates.append(
                StoryArcProgressUpdate(
                    slug=arc.slug,
                    stage_index=stage_index,
                    pressure_score=pressure_score,
                    metadata=metadata,
                    surfaced_questions=per_arc_questions,
                    archived_threads=per_arc_threads,
                )
            )

        return StoryProgressionPlan(
            arc_updates=updates,
            surfaced_questions=surfaced_questions,
            archived_threads=archived_threads,
        )

    def _match_arc(
        self,
        arcs: list[StoryArcSnapshot],
        event: EventCandidate,
    ) -> str | None:
        text = " ".join([event.title, event.details, *event.tags]).lower()
        best_slug: str | None = None
        best_score = 0
        for arc in arcs:
            keywords = self._keywords_for_arc(arc)
            keyword_hits = sum(keyword in text for keyword in keywords)
            type_bonus = int(event.event_type in self._ARC_TYPE_HINTS.get(arc.arc_type, set()))
            score = keyword_hits + type_bonus
            if score > best_score:
                best_score = score
                best_slug = arc.slug
        return best_slug if best_score >= 2 else None

    def _keywords_for_arc(self, arc: StoryArcSnapshot) -> set[str]:
        text = " ".join(
            [
                arc.slug.replace("-", " "),
                arc.title,
                arc.summary,
                *arc.reveal_ladder[: max(2, arc.stage_index + 1)],
                *arc.unresolved_questions[:3],
            ]
        ).lower()
        return {
            token
            for token in re.findall(r"[a-z]{4,}", text)
            if token not in self._STOPWORDS
        }

    def _points_for_event(self, event: EventCandidate) -> int:
        points = 1
        if event.significance >= 7:
            points += 1
        if event.event_type in {
            EventType.CLUE,
            EventType.REVEAL,
            EventType.FINANCIAL,
            EventType.THREAT,
            EventType.ROMANCE,
        }:
            points += 1
        return points

    def _advance_rules(self, arc: StoryArcSnapshot) -> tuple[int, timedelta]:
        window = arc.payoff_window.lower()
        if "years" in window:
            return 16, timedelta(days=2)
        if "months" in window and "weeks" in window:
            return 12, timedelta(hours=18)
        if "months" in window:
            return 14, timedelta(days=1)
        if "continuous" in window:
            return 8, timedelta(hours=4)
        return 10, timedelta(hours=12)

    def _cooldown_elapsed(
        self,
        last_changed_at: str | None,
        cooldown: timedelta,
        now: datetime,
    ) -> bool:
        if not last_changed_at:
            return True
        try:
            parsed = datetime.fromisoformat(last_changed_at)
        except ValueError:
            return True
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return now - ensure_utc(parsed) >= cooldown

    def _surfaced_questions(
        self,
        *,
        arc: StoryArcSnapshot,
        stage_index: int,
        should_surface: bool,
    ) -> list[str]:
        if not should_surface or not arc.unresolved_questions:
            return []
        index = min(stage_index, len(arc.unresolved_questions) - 1)
        return [arc.unresolved_questions[index]]


def _coerce_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
