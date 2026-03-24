# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import StoryGravityConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import DormantThreadSnapshot, StoryGravityStateSnapshot
from lantern_house.utils.time import ensure_utc, utcnow


class StoryGravityService:
    def __init__(self, repository: StoryRepository, config: StoryGravityConfig) -> None:
        self.repository = repository
        self.config = config
        self.interval = timedelta(minutes=max(1, config.refresh_interval_minutes))

    def refresh(self, *, now=None, force: bool = False) -> StoryGravityStateSnapshot:
        now = ensure_utc(now or utcnow())
        current = self.repository.get_story_gravity_state_snapshot()
        if not self.config.enabled:
            return current
        if (
            not force
            and current.updated_at
            and now - ensure_utc(current.updated_at) < self.interval
        ):
            return current

        world = self.repository.get_world_state_snapshot()
        messages = self.repository.list_recent_messages(limit=10)
        events = self.repository.list_recent_events(hours=24, limit=18, minimum_significance=4)
        house_state = self.repository.get_house_state_snapshot()
        recap_scores = self.repository.list_recent_recap_quality_scores(limit=3)
        story_engine = world["metadata"].get("story_engine", {})

        central_force = str(story_engine.get("central_force", "")).strip()
        core_promises = [
            str(item).strip() for item in story_engine.get("core_promises", []) if str(item).strip()
        ]
        voice_guardrails = [
            str(item).strip()
            for item in story_engine.get("voice_guardrails", [])
            if str(item).strip()
        ]
        active_axes = _active_axes(
            text=_recent_text(messages=messages, events=events),
            core_tensions=story_engine.get("core_tensions", []),
        )
        dormant_threads = self._build_dormant_threads(world=world, now=now)
        self.repository.sync_dormant_threads(threads=dormant_threads, now=now)

        drift_score = _clamp(
            28
            + int(len(active_axes) < 2) * 22
            + int(len(world["unresolved_questions"]) > 8) * 16
            + int(len(recap_scores) > 0 and _recent_recap_weakness(recap_scores)) * 12
            - int(bool(house_state.active_pressures)) * 10,
            0,
            100,
        )
        recap_focus = [
            *world["unresolved_questions"][:2],
            *[signal.label for signal in house_state.active_pressures[:2]],
        ][:4]
        north_star = central_force or (
            "Keep the house under pressure through debt, hidden records, loyalty fractures, "
            "and unstable attraction."
        )

        snapshot = StoryGravityStateSnapshot(
            state_key="primary",
            north_star_objective=north_star,
            central_tension=core_promises[0] if core_promises else north_star,
            core_tensions=[
                str(item.get("key", "")).strip()
                for item in story_engine.get("core_tensions", [])
                if isinstance(item, dict) and str(item.get("key", "")).strip()
            ],
            active_axes=active_axes,
            dormant_threads=dormant_threads,
            drift_score=drift_score,
            reentry_priority=_clamp(6 + int(len(world["unresolved_questions"]) >= 5), 1, 10),
            clip_priority=_clamp(
                5
                + int(any(event.event_type in {"reveal", "threat", "romance"} for event in events))
                + int(len(active_axes) >= 2),
                1,
                10,
            ),
            fandom_priority=_clamp(
                5
                + int(any("romance" in axis for axis in active_axes))
                + int(any("loyalty" in axis for axis in active_axes)),
                1,
                10,
            ),
            recap_focus=recap_focus,
            manager_guardrails=[*core_promises[:3], *voice_guardrails[:3]][:6],
            metadata={
                "house_pressure_labels": [
                    signal.label for signal in house_state.active_pressures[:4]
                ],
                "unresolved_questions_count": len(world["unresolved_questions"]),
                "recent_recap_issues": [
                    issue
                    for score in recap_scores
                    for issue in score.get("issues", [])[:2]
                    if issue
                ][:6],
            },
            updated_at=now,
        )
        return self.repository.save_story_gravity_state(snapshot, now=now)

    def _build_dormant_threads(
        self,
        *,
        world: dict,
        now,
    ) -> list[DormantThreadSnapshot]:
        dormant: list[DormantThreadSnapshot] = []
        archived_threads = [
            str(item).strip() for item in world.get("archived_threads", []) if str(item).strip()
        ]
        unresolved = [
            str(item).strip() for item in world.get("unresolved_questions", []) if str(item).strip()
        ]
        for index, item in enumerate(archived_threads[:8]):
            dormant.append(
                DormantThreadSnapshot(
                    thread_key=f"archived-{index}-{_slugify(item)[:48]}",
                    summary=item,
                    source="archived-thread",
                    status="dormant",
                    heat=_clamp(
                        6
                        - min(index, 3)
                        + int(
                            any(
                                token in item.lower()
                                for token in ("kiss", "lied", "ledger", "owner")
                            )
                        ),
                        1,
                        10,
                    ),
                    last_seen_at=now,
                    metadata={"origin": "world.archived_threads"},
                )
            )
        for index, item in enumerate(unresolved[:4]):
            dormant.append(
                DormantThreadSnapshot(
                    thread_key=f"question-{index}-{_slugify(item)[:48]}",
                    summary=item,
                    source="unresolved-question",
                    status="warming",
                    heat=_clamp(5 + int("who" in item.lower() or "why" in item.lower()), 1, 10),
                    last_seen_at=now,
                    metadata={"origin": "world.unresolved_questions"},
                )
            )
        deduped: list[DormantThreadSnapshot] = []
        seen: set[str] = set()
        for item in dormant:
            normalized = _slugify(item.summary)
            if not normalized or normalized in seen:
                continue
            deduped.append(item)
            seen.add(normalized)
        return deduped[:8]


def _recent_text(*, messages, events) -> str:
    return " ".join(
        [message.content for message in messages[-8:]]
        + [event.title for event in events[-10:]]
        + [event.details for event in events[-10:]]
    ).lower()


def _active_axes(*, text: str, core_tensions: list[dict]) -> list[str]:
    active: list[str] = []
    for item in core_tensions:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        keywords = [str(word).lower() for word in item.get("keywords", []) if str(word).strip()]
        if key and keywords and any(keyword in text for keyword in keywords):
            active.append(key)
    return active[:5]


def _recent_recap_weakness(scores: list[dict]) -> bool:
    if not scores:
        return False
    latest = scores[0]
    return any(
        latest.get(metric, 10) <= 4
        for metric in (
            "usefulness",
            "clarity",
            "theory_value",
            "emotional_readability",
            "next_hook_strength",
        )
    )


def _slugify(value: str) -> str:
    return "-".join("".join(ch.lower() if ch.isalnum() else " " for ch in value).split())


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
