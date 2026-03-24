# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import CanonConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import CanonCapsuleSnapshot
from lantern_house.utils.time import ensure_utc, utcnow

_WINDOW_HOURS = {
    "1h": 1,
    "6h": 6,
    "24h": 24,
    "7d": 24 * 7,
    "30d": 24 * 30,
}


class CanonDistillationService:
    def __init__(self, repository: StoryRepository, config: CanonConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None) -> list[CanonCapsuleSnapshot]:
        if not self.config.enabled:
            return self.repository.list_canon_capsules(window_keys=self.config.windows)
        now = ensure_utc(now or utcnow())
        world = self.repository.get_world_state_snapshot()
        scene = self.repository.get_scene_snapshot()
        house_state = self.repository.get_house_state_snapshot()
        strategic_brief = self.repository.get_latest_strategic_brief(now=now, active_only=False)
        guardrails = self.repository.get_story_gravity_state_snapshot().manager_guardrails
        relationship_map = self.repository.get_relationship_map()
        open_arcs = self.repository.list_open_arcs(limit=max(3, self.config.max_items_per_section))
        results: list[CanonCapsuleSnapshot] = []

        for window_key in self.config.windows:
            hours = _WINDOW_HOURS.get(window_key)
            if hours is None:
                continue
            events = self.repository.list_recent_events(
                hours=hours,
                limit=self.config.max_items_per_section * 4,
                minimum_significance=3,
            )
            summaries = self.repository.list_recent_summaries(limit=6)
            headline = _headline(
                window_key=window_key, scene_objective=scene["objective"], events=events
            )
            snapshot = CanonCapsuleSnapshot(
                window_key=window_key,
                headline=headline,
                state_of_play=_state_of_play(
                    world_title=world["title"],
                    scene_objective=scene["objective"],
                    open_arcs=open_arcs,
                    limit=self.config.max_items_per_section,
                ),
                key_clues=_key_clues(events, limit=self.config.max_items_per_section),
                relationship_fault_lines=_slice(
                    relationship_map,
                    limit=self.config.max_items_per_section,
                ),
                active_pressures=_active_pressures(
                    house_state.active_pressures,
                    limit=self.config.max_items_per_section,
                ),
                unresolved_questions=_slice(
                    world["unresolved_questions"],
                    limit=self.config.max_items_per_section,
                ),
                protected_truths=_protected_truths(
                    strategic_brief.reveals_forbidden_for_now if strategic_brief else [],
                    guardrails,
                    limit=self.config.max_items_per_section,
                ),
                recap_hooks=_recap_hooks(
                    events=events,
                    summaries=summaries,
                    limit=self.config.max_items_per_section,
                ),
                metadata={
                    "hours": hours,
                    "generated_at": now.isoformat(),
                    "event_count": len(events),
                },
            )
            results.append(self.repository.save_canon_capsule(snapshot=snapshot, now=now))
        return results


def _headline(*, window_key: str, scene_objective: str, events) -> str:
    if events:
        lead = events[-1]
        return f"{window_key} canon: {lead.title}"
    return f"{window_key} canon: {scene_objective}"


def _state_of_play(*, world_title: str, scene_objective: str, open_arcs, limit: int) -> list[str]:
    items = [f"{world_title}: {scene_objective}"]
    items.extend(f"{arc.title}: {arc.summary}" for arc in open_arcs[: max(0, limit - 1)])
    return _slice(items, limit=limit)


def _key_clues(events, *, limit: int) -> list[str]:
    clues = [
        f"{event.event_type.upper()}: {event.title} - {event.details}"
        for event in events
        if event.event_type in {"clue", "question", "reveal"}
    ]
    return _slice(clues, limit=limit)


def _active_pressures(active_pressures, *, limit: int) -> list[str]:
    return _slice(
        [
            f"{item.label}: {item.recommended_move or item.summary}"
            for item in active_pressures[:limit]
        ],
        limit=limit,
    )


def _protected_truths(
    strategic_forbidden: list[str], guardrails: list[str], *, limit: int
) -> list[str]:
    return _slice([*strategic_forbidden, *guardrails], limit=limit)


def _recap_hooks(*, events, summaries, limit: int) -> list[str]:
    hooks = [event.title for event in events[-limit:] if event.significance >= 5]
    hooks.extend(summary.content for summary in summaries[-1:])
    return _slice(hooks, limit=limit)


def _slice(items: list[str], *, limit: int) -> list[str]:
    cleaned: list[str] = []
    for item in items:
        text = " ".join(str(item).split())
        if not text or text in cleaned:
            continue
        cleaned.append(text[:220])
        if len(cleaned) >= limit:
            break
    return cleaned
