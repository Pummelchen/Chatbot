from __future__ import annotations

from datetime import timedelta

from lantern_house.config import HousePressureConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import BeatPlanItem, HousePressureSignal, HouseStateSnapshot
from lantern_house.utils.time import ensure_utc, isoformat, utcnow


class HousePressureService:
    def __init__(self, repository: StoryRepository, config: HousePressureConfig) -> None:
        self.repository = repository
        self.config = config
        self.interval = timedelta(minutes=max(1, config.refresh_interval_minutes))

    def refresh(self, *, now=None, force: bool = False) -> HouseStateSnapshot:
        state = self.repository.get_house_state_snapshot()
        now = ensure_utc(now or utcnow())
        if not self.config.enabled:
            return state
        if not self.repository.seed_exists():
            return state
        if not force and state.updated_at and now - ensure_utc(state.updated_at) < self.interval:
            return state
        try:
            self.repository.get_scene_snapshot()
        except RuntimeError:
            return state

        events = self.repository.list_recent_events(hours=6, limit=24, minimum_significance=3)
        messages = self.repository.list_recent_messages(limit=8)
        next_state = self._advance(state=state, events=events, messages=messages, now=now)
        persisted = self.repository.save_house_state(next_state, now=now)
        self.repository.sync_beats(
            beat_type="house-pressure",
            items=self._build_pressure_beats(persisted, now=now),
            source_key="house-pressure",
            now=now,
        )
        return persisted

    def _advance(self, *, state: HouseStateSnapshot, events, messages, now) -> HouseStateSnapshot:
        previous = ensure_utc(state.updated_at) if state.updated_at else now - self.interval
        hours_elapsed = max(0.0, (now - previous).total_seconds() / 3600)
        repair_relief = _count_keyword_hits(
            events,
            keywords=("repair", "boiler", "pipe", "fuse", "fix"),
            event_types={"routine", "clue"},
        )
        guest_flashpoints = _count_event_types(events, {"conflict", "threat", "reveal"})
        financial_hits = _count_event_types(events, {"financial"})
        romance_spikes = _count_event_types(events, {"romance"})
        humor_relief = _count_event_types(events, {"humor"})

        cash_on_hand = max(
            0,
            state.cash_on_hand
            - round(state.hourly_burn_rate * hours_elapsed)
            - financial_hits * 120
            + repair_relief * 40,
        )
        payroll_due_in_hours = state.payroll_due_in_hours
        if payroll_due_in_hours > 0:
            payroll_due_in_hours = max(0, payroll_due_in_hours - round(hours_elapsed))
        elif state.hourly_burn_rate > 0:
            cash_on_hand = max(0, cash_on_hand - state.hourly_burn_rate * 18)
            payroll_due_in_hours = 168

        weather_pressure = _clamp(
            round((state.weather_pressure + _weather_wave(now)) / 2)
            + int(state.repair_backlog >= 7),
            0,
            10,
        )
        repair_backlog = _clamp(
            state.repair_backlog
            + int(hours_elapsed >= 4)
            + int(weather_pressure >= 6)
            + financial_hits
            - repair_relief,
            0,
            10,
        )
        guest_tension = _clamp(
            state.guest_tension + guest_flashpoints + romance_spikes - humor_relief - repair_relief,
            0,
            10,
        )
        staff_fatigue = _clamp(
            state.staff_fatigue
            + int(hours_elapsed >= 3)
            + guest_flashpoints
            + int(_same_voice_loop(messages))
            - humor_relief,
            0,
            10,
        )
        inspection_risk = _clamp(
            max(state.inspection_risk, repair_backlog - 2)
            + int(guest_tension >= 7)
            + int(financial_hits > 0)
            - repair_relief,
            0,
            10,
        )
        vacant_rooms = max(state.capacity - state.occupied_rooms, 0)
        cash_reserve_hours = cash_on_hand // max(1, state.hourly_burn_rate or 1)
        vacancy_pressure = _clamp(
            vacant_rooms + int(cash_reserve_hours < 72) + int(inspection_risk >= 7),
            0,
            10,
        )
        reputation_risk = _clamp(
            round((guest_tension + inspection_risk + romance_spikes + financial_hits) / 2),
            0,
            10,
        )

        active_pressures = self._active_pressures(
            state=state,
            metrics={
                "vacancy_pressure": vacancy_pressure,
                "cash_on_hand": cash_on_hand,
                "cash_reserve_hours": cash_reserve_hours,
                "payroll_due_in_hours": payroll_due_in_hours,
                "repair_backlog": repair_backlog,
                "inspection_risk": inspection_risk,
                "guest_tension": guest_tension,
                "weather_pressure": weather_pressure,
                "staff_fatigue": staff_fatigue,
                "reputation_risk": reputation_risk,
            },
        )

        metadata = dict(state.metadata)
        metadata["derived_metrics"] = {
            "cash_reserve_hours": cash_reserve_hours,
            "guest_flashpoints_last_6h": guest_flashpoints,
            "repair_relief_last_6h": repair_relief,
        }
        metadata["last_pressure_refresh_at"] = isoformat(now)
        return HouseStateSnapshot(
            state_key=state.state_key,
            capacity=state.capacity,
            occupied_rooms=state.occupied_rooms,
            vacancy_pressure=vacancy_pressure,
            cash_on_hand=cash_on_hand,
            hourly_burn_rate=state.hourly_burn_rate,
            payroll_due_in_hours=payroll_due_in_hours,
            repair_backlog=repair_backlog,
            inspection_risk=inspection_risk,
            guest_tension=guest_tension,
            weather_pressure=weather_pressure,
            staff_fatigue=staff_fatigue,
            reputation_risk=reputation_risk,
            active_pressures=active_pressures[: self.config.max_active_signals],
            metadata=metadata,
            updated_at=now,
        )

    def _active_pressures(
        self,
        *,
        state: HouseStateSnapshot,
        metrics: dict[str, int],
    ) -> list[HousePressureSignal]:
        catalog = state.metadata.get("pressure_catalog", [])
        signals: list[HousePressureSignal] = []
        for item in catalog:
            if not isinstance(item, dict):
                continue
            metric = str(item.get("metric", "")).strip()
            if not metric:
                continue
            comparison = str(item.get("comparison", "gte")).lower()
            threshold = _int_or_default(item.get("threshold"), 6)
            value = metrics.get(metric, 0)
            triggered = value >= threshold if comparison != "lte" else value <= threshold
            if not triggered:
                continue
            intensity = value if comparison != "lte" else min(10, threshold - value + 5)
            signals.append(
                HousePressureSignal(
                    slug=str(item.get("slug", metric)),
                    label=str(item.get("label", metric.replace("_", " ").title())),
                    intensity=_clamp(intensity, 1, 10),
                    summary=str(item.get("summary", "")),
                    recommended_move=str(item.get("recommended_move", "")),
                    source_metric=metric,
                )
            )
        if signals:
            return sorted(signals, key=lambda item: item.intensity, reverse=True)

        fallback: list[HousePressureSignal] = []
        if metrics.get("repair_backlog", 0) >= 7:
            fallback.append(
                HousePressureSignal(
                    slug="repair-overflow",
                    label="Repair overflow",
                    intensity=metrics["repair_backlog"],
                    summary=(
                        "The house keeps collecting practical failures faster "
                        "than people can fix them."
                    ),
                    recommended_move=(
                        "Force a breakdown, blame cycle, or money argument "
                        "around one visible system."
                    ),
                    source_metric="repair_backlog",
                )
            )
        if metrics.get("cash_reserve_hours", 999) <= 48:
            fallback.append(
                HousePressureSignal(
                    slug="cash-breathing-room",
                    label="Cash breathing room is collapsing",
                    intensity=min(10, 10 - metrics["cash_reserve_hours"] // 8),
                    summary="Lantern House is running low on hours, not just money.",
                    recommended_move=(
                        "Tie romance and loyalty decisions to a concrete cost "
                        "or guest payment problem."
                    ),
                    source_metric="cash_reserve_hours",
                )
            )
        return fallback

    def _build_pressure_beats(self, state: HouseStateSnapshot, *, now) -> list[BeatPlanItem]:
        catalog = {
            str(item.get("slug")): item
            for item in state.metadata.get("pressure_catalog", [])
            if isinstance(item, dict) and item.get("slug")
        }
        beats: list[BeatPlanItem] = []
        for signal in state.active_pressures[: self.config.max_pending_beats]:
            catalog_item = catalog.get(signal.slug, {})
            objective = str(
                catalog_item.get("beat_objective") or signal.recommended_move or signal.summary
            )
            ready_in_hours = max(0, _int_or_default(catalog_item.get("ready_in_hours"), 0))
            beats.append(
                BeatPlanItem(
                    beat_key=f"house-{signal.slug}",
                    beat_type="house-pressure",
                    objective=objective,
                    significance=max(5, signal.intensity),
                    ready_at=isoformat(now + timedelta(hours=ready_in_hours)),
                    keywords=_unique_keywords(
                        [
                            *catalog_item.get("keywords", []),
                            signal.slug,
                            signal.label,
                            signal.source_metric,
                        ]
                    ),
                    metadata={
                        "source": "house-pressure",
                        "signal_slug": signal.slug,
                        "source_metric": signal.source_metric,
                        "pressure_intensity": signal.intensity,
                        "phase": "ready" if ready_in_hours == 0 else "build",
                    },
                )
            )
        return beats


def _weather_wave(now) -> int:
    cycle = (now.toordinal() + now.hour) % 6
    return [2, 3, 5, 7, 6, 4][cycle]


def _count_event_types(events, event_types: set[str]) -> int:
    return sum(1 for event in events if event.event_type in event_types and event.significance >= 6)


def _count_keyword_hits(events, *, keywords: tuple[str, ...], event_types: set[str]) -> int:
    hits = 0
    for event in events:
        if event.event_type not in event_types:
            continue
        text = f"{event.title} {event.details}".lower()
        if any(keyword in text for keyword in keywords):
            hits += 1
    return hits


def _same_voice_loop(messages) -> bool:
    if len(messages) < 3:
        return False
    recent = [message.speaker_label for message in messages[-3:]]
    return len(set(recent)) == 1


def _unique_keywords(values: list[str]) -> list[str]:
    keywords: list[str] = []
    for value in values:
        for token in str(value).replace("-", " ").split():
            cleaned = token.strip(" ,.!?\"'()[]").lower()
            if len(cleaned) < 4 or cleaned in keywords:
                continue
            keywords.append(cleaned)
    return keywords[:8]


def _int_or_default(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))
