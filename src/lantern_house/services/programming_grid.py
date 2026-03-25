# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import ProgrammingGridConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import ProgrammingGridSlotSnapshot
from lantern_house.utils.time import ensure_utc, utcnow


class ProgrammingGridService:
    def __init__(self, repository: StoryRepository, config: ProgrammingGridConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None, force: bool = False) -> list[ProgrammingGridSlotSnapshot]:
        if not self.config.enabled and not force:
            return self.repository.list_programming_grid_slots(limit=10)

        now = ensure_utc(now or utcnow())
        current_slots = self.repository.list_programming_grid_slots(limit=10)
        if (
            current_slots
            and current_slots[0].updated_at
            and not force
            and now - ensure_utc(current_slots[0].updated_at)
            < timedelta(minutes=max(1, self.config.refresh_interval_minutes))
        ):
            return current_slots
        daily_window = _daily_window(now)
        weekly_window = _weekly_window(now)
        recent_day_events = self.repository.list_recent_events(
            hours=24,
            limit=72,
            minimum_significance=3,
        )
        recent_week_events = self.repository.list_recent_events(
            hours=24 * 7,
            limit=120,
            minimum_significance=3,
        )
        house_state = self.repository.get_house_state_snapshot()
        current_arcs = self.repository.list_open_arcs(limit=5)
        latest_hour = self.repository.get_latest_hourly_progress_ledger()

        slots = [
            *self._daily_slots(
                now=now,
                window=daily_window,
                events=recent_day_events,
                house_state=house_state,
                latest_hour=latest_hour,
            ),
            *self._weekly_slots(
                now=now,
                window=weekly_window,
                events=recent_week_events,
                house_state=house_state,
                current_arcs=current_arcs,
            ),
        ]
        return self.repository.sync_programming_grid_slots(slots=slots, now=now)

    def _daily_slots(
        self,
        *,
        now,
        window: tuple,
        events,
        house_state,
        latest_hour,
    ) -> list[ProgrammingGridSlotSnapshot]:
        window_start, window_end = window
        progress_notes = {
            "house-crisis": _event_titles(events, {"financial", "conflict", "threat"}),
            "romance-escalation": _event_titles(events, {"romance"}),
            "clue-turn": _event_titles(events, {"clue", "question", "reveal"}),
            "alliance-fracture": _event_titles(events, {"relationship", "alliance", "conflict"}),
            "recap-hook": _event_titles(
                [event for event in events if event.significance >= 7],
                {"clue", "reveal", "romance", "threat", "financial", "conflict"},
            ),
        }
        slots = [
            self._build_slot(
                horizon="daily",
                slot_key="house-crisis",
                label="House crisis beat",
                objective=(
                    "Each day needs one grounded house crisis involving debt, repairs, guests, "
                    "staff fatigue, inspections, or reputation."
                ),
                target_axis="debt",
                window_start=window_start,
                window_end=window_end,
                progress_notes=progress_notes["house-crisis"]
                + [
                    signal.label
                    for signal in house_state.active_pressures[:2]
                    if signal.intensity >= 7
                ],
                at_risk_threshold=timedelta(hours=self.config.at_risk_after_hours),
                now=now,
            ),
            self._build_slot(
                horizon="daily",
                slot_key="romance-escalation",
                label="Romance escalation",
                objective=(
                    "Each day needs one unstable romantic shift: jealousy, longing, interrupted "
                    "intimacy, public misread, or near-confession."
                ),
                target_axis="desire",
                window_start=window_start,
                window_end=window_end,
                progress_notes=progress_notes["romance-escalation"],
                at_risk_threshold=timedelta(hours=self.config.at_risk_after_hours),
                now=now,
            ),
            self._build_slot(
                horizon="daily",
                slot_key="clue-turn",
                label="Clue turn",
                objective=(
                    "Each day needs one clue, contradiction, or sharper question that deepens "
                    "the mystery without solving it."
                ),
                target_axis="evidence",
                window_start=window_start,
                window_end=window_end,
                progress_notes=progress_notes["clue-turn"],
                at_risk_threshold=timedelta(hours=self.config.at_risk_after_hours),
                now=now,
            ),
            self._build_slot(
                horizon="daily",
                slot_key="alliance-fracture",
                label="Alliance fracture",
                objective=(
                    "Each day needs one visible trust or loyalty shift that changes who can "
                    "lean on whom."
                ),
                target_axis="loyalty",
                window_start=window_start,
                window_end=window_end,
                progress_notes=progress_notes["alliance-fracture"],
                at_risk_threshold=timedelta(hours=self.config.at_risk_after_hours),
                now=now,
            ),
            self._build_slot(
                horizon="daily",
                slot_key="recap-hook",
                label="Recap-worthy hook",
                objective=(
                    "Each day needs at least one moment that recaps cleanly for re-entry: "
                    "a sharp threat, clue, reversal, or confession."
                ),
                target_axis="power",
                window_start=window_start,
                window_end=window_end,
                progress_notes=progress_notes["recap-hook"]
                + ([latest_hour.dominant_axis] if latest_hour and latest_hour.contract_met else []),
                at_risk_threshold=timedelta(hours=self.config.at_risk_after_hours),
                now=now,
            ),
        ]
        return slots

    def _weekly_slots(
        self,
        *,
        now,
        window: tuple,
        events,
        house_state,
        current_arcs,
    ) -> list[ProgrammingGridSlotSnapshot]:
        window_start, window_end = window
        weekly_days = timedelta(days=self.config.weekly_at_risk_after_days)
        romance_titles = _event_titles(events, {"romance"})
        clue_titles = _event_titles(events, {"clue", "question", "reveal"})
        conflict_titles = _event_titles(events, {"conflict", "threat", "alliance"})
        house_titles = _event_titles(events, {"financial"})
        arc_titles = [arc.title for arc in current_arcs[:3]]
        return [
            self._build_slot(
                horizon="weekly",
                slot_key="ownership-shift",
                label="Ownership or legitimacy shift",
                objective=(
                    "Each week needs one move in the ownership, inheritance, records, or family "
                    "legitimacy battle."
                ),
                target_axis="power",
                window_start=window_start,
                window_end=window_end,
                progress_notes=clue_titles + arc_titles,
                at_risk_threshold=weekly_days,
                now=now,
            ),
            self._build_slot(
                horizon="weekly",
                slot_key="major-house-setback",
                label="Major house setback",
                objective=(
                    "Each week needs one setback that proves the house is expensive to save."
                ),
                target_axis="debt",
                window_start=window_start,
                window_end=window_end,
                progress_notes=house_titles
                + [
                    signal.label
                    for signal in house_state.active_pressures
                    if signal.intensity >= 8
                ],
                at_risk_threshold=weekly_days,
                now=now,
            ),
            self._build_slot(
                horizon="weekly",
                slot_key="ship-rupture-or-advance",
                label="Ship rupture or advance",
                objective=(
                    "Each week needs one shippable emotional turn: a rupture, advance, or "
                    "dangerous almost-commitment."
                ),
                target_axis="desire",
                window_start=window_start,
                window_end=window_end,
                progress_notes=romance_titles + conflict_titles,
                at_risk_threshold=weekly_days,
                now=now,
            ),
            self._build_slot(
                horizon="weekly",
                slot_key="mystery-ladder-step",
                label="Mystery ladder step",
                objective=(
                    "Each week needs one meaningful climb up the central mystery ladder."
                ),
                target_axis="evidence",
                window_start=window_start,
                window_end=window_end,
                progress_notes=clue_titles,
                at_risk_threshold=weekly_days,
                now=now,
            ),
            self._build_slot(
                horizon="weekly",
                slot_key="fresh-pairing",
                label="Fresh pairing refresh",
                objective=(
                    "Each week needs one fresh character pairing or camp split to refresh the "
                    "ensemble without leaving the house core."
                ),
                target_axis="trust",
                window_start=window_start,
                window_end=window_end,
                progress_notes=conflict_titles + romance_titles,
                at_risk_threshold=weekly_days,
                now=now,
            ),
        ]

    def _build_slot(
        self,
        *,
        horizon: str,
        slot_key: str,
        label: str,
        objective: str,
        target_axis: str,
        window_start,
        window_end,
        progress_notes: list[str],
        at_risk_threshold: timedelta,
        now,
    ) -> ProgrammingGridSlotSnapshot:
        cleaned_notes = [note for note in progress_notes if note][:4]
        status = "done" if cleaned_notes else "planned"
        if status != "done" and now - window_start >= at_risk_threshold:
            status = "at-risk"
        priority = 9 if status == "at-risk" else 6 if status == "planned" else 3
        return ProgrammingGridSlotSnapshot(
            horizon=horizon,
            slot_key=slot_key,
            label=label,
            objective=objective,
            target_axis=target_axis,
            status=status,
            priority=priority,
            notes=cleaned_notes[:3] or [_fallback_note(slot_key=slot_key)],
            metadata={
                "window_hours": max(1, int((window_end - window_start).total_seconds() // 3600)),
                "status_source": "recent-events",
            },
            window_start_at=window_start,
            window_end_at=window_end,
            updated_at=now,
        )


def _daily_window(now):
    start = ensure_utc(now).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _weekly_window(now):
    value = ensure_utc(now)
    weekday_start = value - timedelta(days=value.weekday())
    start = weekday_start.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)


def _event_titles(events, event_types: set[str]) -> list[str]:
    titles: list[str] = []
    for event in events:
        if event.event_type not in event_types:
            continue
        title = " ".join(event.title.split())
        if title and title not in titles:
            titles.append(title[:160])
    return titles[:3]


def _fallback_note(*, slot_key: str) -> str:
    defaults = {
        "house-crisis": "No grounded house setback has landed yet.",
        "romance-escalation": "No meaningful romantic escalation has landed yet.",
        "clue-turn": "No fresh clue or contradiction has landed yet.",
        "alliance-fracture": "No visible alliance or trust fracture has landed yet.",
        "recap-hook": "No recap-clean hook has landed yet.",
        "ownership-shift": "Ownership pressure has not meaningfully moved yet.",
        "major-house-setback": "The house has avoided a major weekly setback so far.",
        "ship-rupture-or-advance": "No weekly ship-changing turn has landed yet.",
        "mystery-ladder-step": "The central mystery ladder has not climbed this week.",
        "fresh-pairing": "The ensemble has not rotated into a fresh pairing yet.",
    }
    return defaults.get(slot_key, "No progress has landed yet.")
