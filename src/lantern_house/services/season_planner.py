# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import SeasonPlannerConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import ProgrammingGridSlotSnapshot
from lantern_house.utils.time import ensure_utc, utcnow


class SeasonPlannerService:
    def __init__(self, repository: StoryRepository, config: SeasonPlannerConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None, force: bool = False) -> list[ProgrammingGridSlotSnapshot]:
        now = ensure_utc(now or utcnow())
        if not self.config.enabled and not force:
            return self.repository.list_programming_grid_slots(limit=12)

        current_slots = [
            *self.repository.list_programming_grid_slots(horizon="season-30d", limit=8),
            *self.repository.list_programming_grid_slots(horizon="season-90d", limit=8),
        ]
        if (
            current_slots
            and current_slots[0].updated_at
            and not force
            and now - ensure_utc(current_slots[0].updated_at)
            < timedelta(minutes=max(1, self.config.refresh_interval_minutes))
        ):
            return current_slots

        thirty_day_window = (now, now + timedelta(days=max(7, self.config.near_term_horizon_days)))
        ninety_day_window = (now, now + timedelta(days=max(30, self.config.long_term_horizon_days)))
        recent_month_events = self.repository.list_recent_events(
            hours=24 * min(30, self.config.near_term_horizon_days),
            limit=160,
            minimum_significance=3,
        )
        recent_quarter_events = self.repository.list_recent_events(
            hours=24 * min(90, self.config.long_term_horizon_days),
            limit=220,
            minimum_significance=3,
        )
        arcs = self.repository.list_open_arcs(limit=8)
        world = self.repository.get_world_state_snapshot()
        future_character = (world.get("metadata") or {}).get("future_recurring_character") or {}

        slots = [
            *self._near_term_slots(
                now=now,
                window=thirty_day_window,
                events=recent_month_events,
                arcs=arcs,
            ),
            *self._long_term_slots(
                now=now,
                window=ninety_day_window,
                events=recent_quarter_events,
                arcs=arcs,
                future_character=future_character,
            ),
        ]
        persisted = self.repository.sync_programming_grid_slots(slots=slots, now=now)
        return sorted(
            persisted,
            key=lambda item: (
                0 if item.horizon.startswith("season") else 1,
                -item.priority,
                item.slot_key,
            ),
        )

    def _near_term_slots(
        self,
        *,
        now,
        window: tuple,
        events,
        arcs,
    ) -> list[ProgrammingGridSlotSnapshot]:
        window_start, window_end = window
        reveal_notes = _event_titles(events, {"clue", "question", "reveal"})
        romance_notes = _event_titles(events, {"romance", "conflict"})
        finance_notes = _event_titles(events, {"financial", "threat"})
        arc_titles = [arc.title for arc in arcs[:4]]
        return [
            _season_slot(
                horizon="season-30d",
                slot_key="reveal-window",
                label="Reveal window",
                objective=(
                    "Within the next 30 days, land one controlled reveal about Evelyn, "
                    "the missing records, or the codicil without closing the core mystery."
                ),
                target_axis="evidence",
                notes=reveal_notes + arc_titles,
                window_start=window_start,
                window_end=window_end,
                now=now,
            ),
            _season_slot(
                horizon="season-30d",
                slot_key="ship-cycle",
                label="Ship cycle",
                objective=(
                    "Within the next 30 days, rotate a slow-burn ship through hope, rupture, "
                    "and dangerous renewed longing."
                ),
                target_axis="desire",
                notes=romance_notes,
                window_start=window_start,
                window_end=window_end,
                now=now,
            ),
            _season_slot(
                horizon="season-30d",
                slot_key="inheritance-turn",
                label="Inheritance turn",
                objective=(
                    "Within the next 30 days, advance the legitimacy and ownership battle "
                    "through papers, family pressure, or a procedural threat."
                ),
                target_axis="power",
                notes=[
                    note
                    for note in arc_titles
                    if "own" in note.lower() or "inherit" in note.lower()
                ]
                or finance_notes,
                window_start=window_start,
                window_end=window_end,
                now=now,
            ),
            _season_slot(
                horizon="season-30d",
                slot_key="house-crisis-peak",
                label="House crisis peak",
                objective=(
                    "Within the next 30 days, build toward one house emergency that ties cash, "
                    "repairs, weather, and emotional fallout together."
                ),
                target_axis="debt",
                notes=finance_notes,
                window_start=window_start,
                window_end=window_end,
                now=now,
            ),
        ]

    def _long_term_slots(
        self,
        *,
        now,
        window: tuple,
        events,
        arcs,
        future_character: dict,
    ) -> list[ProgrammingGridSlotSnapshot]:
        window_start, window_end = window
        mystery_notes = _event_titles(events, {"clue", "question", "reveal"})
        trust_notes = _event_titles(events, {"relationship", "alliance", "conflict"})
        arc_titles = [arc.title for arc in arcs[:5]]
        future_name = str(
            future_character.get("full_name") or future_character.get("name") or ""
        ).strip()
        return [
            _season_slot(
                horizon="season-90d",
                slot_key="hidden-history-deepening",
                label="Hidden-history deepening",
                objective=(
                    "Within the next 90 days, widen the house mythology through archives, old "
                    "residents, and documents without losing the central Vale mystery."
                ),
                target_axis="evidence",
                notes=mystery_notes + arc_titles,
                window_start=window_start,
                window_end=window_end,
                now=now,
            ),
            _season_slot(
                horizon="season-90d",
                slot_key="camp-realignment",
                label="Camp realignment",
                objective=(
                    "Within the next 90 days, reshuffle trust camps so the ensemble keeps "
                    "producing fresh but believable alliances and betrayals."
                ),
                target_axis="loyalty",
                notes=trust_notes,
                window_start=window_start,
                window_end=window_end,
                now=now,
            ),
            _season_slot(
                horizon="season-90d",
                slot_key="cast-refresh-point",
                label="Cast refresh point",
                objective=(
                    f"Within the next 90 days, prepare a controlled cast-refresh lane for "
                    f"{future_name or 'the archivist figure'} or a similarly grounded resident "
                    "who deepens the house's record war."
                ),
                target_axis="novelty",
                notes=[future_name]
                if future_name
                else ["No future recurring character seeded yet."],
                window_start=window_start,
                window_end=window_end,
                now=now,
            ),
        ]


def _season_slot(
    *,
    horizon: str,
    slot_key: str,
    label: str,
    objective: str,
    target_axis: str,
    notes: list[str],
    window_start,
    window_end,
    now,
) -> ProgrammingGridSlotSnapshot:
    cleaned = [note for note in notes if note][:3]
    status = "planned" if cleaned else "at-risk"
    priority = 8 if status == "at-risk" else 5
    return ProgrammingGridSlotSnapshot(
        horizon=horizon,
        slot_key=slot_key,
        label=label,
        objective=objective,
        target_axis=target_axis,
        status=status,
        priority=priority,
        notes=cleaned or ["No confirming movement has landed yet."],
        metadata={"planner": "season"},
        window_start_at=window_start,
        window_end_at=window_end,
        updated_at=now,
    )


def _event_titles(events, event_types: set[str]) -> list[str]:
    titles: list[str] = []
    for event in events:
        if event.event_type not in event_types:
            continue
        title = " ".join(event.title.split())
        if title and title not in titles:
            titles.append(title[:160])
    return titles[:3]
