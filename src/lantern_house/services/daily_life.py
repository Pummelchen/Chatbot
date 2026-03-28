# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import DailyLifeConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import BeatPlanItem, DailyLifeSlotSnapshot, HouseStateSnapshot
from lantern_house.utils.time import ensure_utc, isoformat, utcnow

_ROLE_TASKS: dict[str, list[dict[str, object]]] = {
    "manager": [
        {
            "task_type": "front-desk",
            "location_hints": ["front-desk", "lobby"],
            "objective": "Close the cash gap without letting the lobby smell the panic.",
            "notes": ["Desk receipts", "payroll pressure", "protect the house face"],
        },
        {
            "task_type": "inspection",
            "location_hints": ["lantern-wing", "hallway", "back-office"],
            "objective": "Walk the fragile rooms before an inspector or claimant does.",
            "notes": ["Keys", "sealed doors", "evidence risk"],
        },
    ],
    "fixer": [
        {
            "task_type": "repair",
            "location_hints": ["roof-access", "boiler-room", "lantern-wing"],
            "objective": "Keep one repair from becoming public proof that the house is failing.",
            "notes": ["Tools", "weather strain", "private leverage"],
        },
        {
            "task_type": "security",
            "location_hints": ["service-corridor", "back-yard", "lantern-wing"],
            "objective": (
                "Check a room, lock, or route that somebody else is pretending not to need."
            ),
            "notes": ["Night route", "hidden access", "old promises"],
        },
    ],
    "observer": [
        {
            "task_type": "writing",
            "location_hints": ["courtyard", "tea-room", "lobby"],
            "objective": (
                "Stay visible enough to charm people while quietly collecting contradictions."
            ),
            "notes": ["Notebook", "tea", "dangerous questions"],
        },
        {
            "task_type": "interview",
            "location_hints": ["front-desk", "courtyard", "stairwell"],
            "objective": "Ask one warm question that leaves somebody exposed after the answer.",
            "notes": ["Soft tone", "hard inference", "watch reactions"],
        },
    ],
    "helper": [
        {
            "task_type": "check-in",
            "location_hints": ["front-desk", "lobby"],
            "objective": (
                "Keep arrivals and gossip moving before the house tension freezes the room."
            ),
            "notes": ["Guest warmth", "snack run", "accidental chaos"],
        },
        {
            "task_type": "errand",
            "location_hints": ["market-lane", "kitchen", "front-desk"],
            "objective": "Run an errand that overhears exactly the wrong secret.",
            "notes": ["Supplies", "community chatter", "misdelivered message"],
        },
    ],
    "heir": [
        {
            "task_type": "records",
            "location_hints": ["back-office", "study", "front-desk"],
            "objective": "Force the paper trail to acknowledge you without letting your fear show.",
            "notes": ["Lawyer call", "inheritance", "status pressure"],
        },
        {
            "task_type": "boundary",
            "location_hints": ["lobby", "courtyard", "lantern-wing"],
            "objective": "Reclaim symbolic ground in the house even if it starts an argument.",
            "notes": ["Legitimacy", "class friction", "nobody yields cleanly"],
        },
    ],
    "returning": [
        {
            "task_type": "archive",
            "location_hints": ["lantern-wing", "back-office", "storage-room"],
            "objective": "Touch the old evidence carefully enough to stay deniable.",
            "notes": ["Old betrayal", "private knowledge", "watch who follows"],
        },
        {
            "task_type": "watch",
            "location_hints": ["roof-access", "courtyard", "stairwell"],
            "objective": "Hold position where you can catch a lie before the others feel watched.",
            "notes": ["Composed threat", "memory pressure", "timed interruption"],
        },
    ],
}


class DailyLifeSchedulerService:
    def __init__(self, repository: StoryRepository, config: DailyLifeConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None, force: bool = False) -> list[DailyLifeSlotSnapshot]:
        now = ensure_utc(now or utcnow())
        existing = self.repository.list_daily_life_schedule_slots(
            limit=self.config.max_active_slots
        )
        if not force and not self.config.enabled:
            return existing
        if (
            not force
            and existing
            and existing[0].updated_at
            and now - ensure_utc(existing[0].updated_at)
            < timedelta(minutes=max(1, self.config.refresh_interval_minutes))
        ):
            return existing

        world = self.repository.get_world_state_snapshot()
        house = self.repository.get_house_state_snapshot()
        roster = self.repository.list_characters()
        guests = self.repository.list_active_guest_profiles(limit=4)
        locations = self.repository.list_locations()
        slots = self._build_slots(
            world=world,
            house=house,
            roster=roster,
            guests=guests,
            locations=locations,
            now=now,
        )
        persisted = self.repository.sync_daily_life_schedule_slots(slots=slots, now=now)
        self._sync_daily_life_beats(slots=persisted, now=now)
        return persisted

    def _build_slots(
        self,
        *,
        world: dict,
        house: HouseStateSnapshot,
        roster: list[dict[str, object]],
        guests,
        locations: list[dict[str, object]],
        now,
    ) -> list[DailyLifeSlotSnapshot]:
        story_day = int(world.get("current_story_day") or 1)
        horizon_hours = max(6, self.config.horizon_hours)
        base_start = now.replace(minute=0, second=0, microsecond=0)
        slots: list[DailyLifeSlotSnapshot] = []
        for index, character in enumerate(roster):
            slots.extend(
                self._character_slots(
                    character=character,
                    house=house,
                    locations=locations,
                    story_day=story_day,
                    slot_index=index,
                    base_start=base_start,
                    horizon_hours=horizon_hours,
                    now=now,
                )
            )
        for guest_index, guest in enumerate(guests):
            offset_hours = (guest_index * 2) % max(2, horizon_hours)
            window_start = base_start + timedelta(hours=offset_hours)
            window_end = window_start + timedelta(hours=2)
            slots.append(
                DailyLifeSlotSnapshot(
                    slot_key=f"guest-{guest.guest_key}-{window_start:%Y%m%d%H}",
                    horizon_key="current-day",
                    participant_slug=guest.guest_key,
                    participant_name=guest.display_name,
                    role_type="guest",
                    location_slug=guest.linked_location_slug,
                    location_name=_location_name(guest.linked_location_slug, locations),
                    objective=guest.hook,
                    task_type="guest-pressure",
                    status=_status_for_window(now=now, start=window_start, end=window_end),
                    priority=min(10, 5 + len(guest.pressure_tags)),
                    notes=guest.pressure_tags[:3],
                    metadata={"guest": True, "role": guest.role},
                    window_start_at=window_start,
                    window_end_at=window_end,
                    updated_at=now,
                )
            )
        slots.sort(
            key=lambda item: (
                item.window_start_at or now,
                -item.priority,
                item.participant_name,
            )
        )
        return slots[: self.config.max_active_slots]

    def _character_slots(
        self,
        *,
        character: dict[str, object],
        house: HouseStateSnapshot,
        locations: list[dict[str, object]],
        story_day: int,
        slot_index: int,
        base_start,
        horizon_hours: int,
        now,
    ) -> list[DailyLifeSlotSnapshot]:
        role_key = _role_key(str(character.get("ensemble_role") or ""))
        templates = _ROLE_TASKS.get(role_key, _ROLE_TASKS["observer"])
        full_name = str(character.get("full_name") or character.get("slug") or "Resident")
        slots: list[DailyLifeSlotSnapshot] = []
        for phase_index in range(2):
            template = templates[(story_day + slot_index + phase_index) % len(templates)]
            offset_hours = ((slot_index + phase_index * 3) * 2) % max(3, horizon_hours)
            window_start = base_start + timedelta(hours=offset_hours)
            window_end = window_start + timedelta(hours=3)
            notes = list(template["notes"])[:2]
            if phase_index == 0 and house.payroll_due_in_hours <= 24:
                notes.append("Money deadline is now story-visible.")
            if phase_index == 1 and house.weather_pressure >= 6:
                notes.append("Weather can interrupt the task at any time.")
            location_slug = _first_location_slug(locations, template["location_hints"])
            location_name = _location_name(location_slug, locations)
            slots.append(
                DailyLifeSlotSnapshot(
                    slot_key=(
                        f"{character.get('slug')}-{template['task_type']}-"
                        f"{window_start:%Y%m%d%H}"
                    ),
                    horizon_key="current-day",
                    participant_slug=str(character.get("slug") or ""),
                    participant_name=full_name,
                    role_type="resident",
                    location_slug=location_slug,
                    location_name=location_name,
                    objective=str(template["objective"]),
                    task_type=str(template["task_type"]),
                    status=_status_for_window(now=now, start=window_start, end=window_end),
                    priority=_priority_for_role(
                        role_key=role_key,
                        task_type=str(template["task_type"]),
                        house=house,
                    ),
                    notes=notes,
                    metadata={
                        "ensemble_role": character.get("ensemble_role"),
                        "message_style": character.get("message_style"),
                    },
                    window_start_at=window_start,
                    window_end_at=window_end,
                    updated_at=now,
                )
            )
        return slots

    def _sync_daily_life_beats(self, *, slots: list[DailyLifeSlotSnapshot], now) -> None:
        items = [
            BeatPlanItem(
                beat_key=f"daily-life-{slot.slot_key}",
                beat_type="daily-life",
                objective=f"{slot.participant_name}: {slot.objective}",
                significance=max(4, min(8, slot.priority)),
                ready_at=isoformat(slot.window_start_at or now),
                keywords=[
                    slot.participant_name.split()[0],
                    slot.task_type.replace("-", " "),
                    *(slot.notes[:1] or []),
                ],
                metadata={
                    "participant_slug": slot.participant_slug,
                    "location_slug": slot.location_slug,
                    "task_type": slot.task_type,
                },
            )
            for slot in slots[: self.config.max_pending_beats]
        ]
        self.repository.sync_beats(
            beat_type="daily-life",
            items=items,
            source_key="daily-life-scheduler",
            now=now,
        )


def _role_key(raw_role: str) -> str:
    lowered = raw_role.lower()
    if "manager" in lowered:
        return "manager"
    if "fixer" in lowered or "handyman" in lowered:
        return "fixer"
    if "observer" in lowered or "guest" in lowered or "writer" in lowered:
        return "observer"
    if "worker" in lowered or "reception" in lowered or "helper" in lowered:
        return "helper"
    if "heir" in lowered or "claimant" in lowered or "relative" in lowered:
        return "heir"
    if "returning" in lowered or "past" in lowered:
        return "returning"
    return "observer"


def _first_location_slug(locations: list[dict[str, object]], hints: object) -> str | None:
    candidates = [str(item) for item in (hints or [])]
    for hint in candidates:
        for location in locations:
            slug = str(location.get("slug") or "")
            name = str(location.get("name") or "").lower()
            if hint == slug or hint.replace("-", " ") in name:
                return slug
    return str(locations[0]["slug"]) if locations else None


def _location_name(location_slug: str | None, locations: list[dict[str, object]]) -> str:
    if not location_slug:
        return "the house"
    for location in locations:
        if location.get("slug") == location_slug:
            return str(location.get("name") or location_slug)
    return location_slug.replace("-", " ")


def _priority_for_role(
    *,
    role_key: str,
    task_type: str,
    house: HouseStateSnapshot,
) -> int:
    priority = 5
    if role_key == "manager":
        priority += int(house.payroll_due_in_hours <= 24) + int(house.reputation_risk >= 6)
    if task_type in {"repair", "inspection"}:
        priority += int(house.repair_backlog >= 6) + int(house.weather_pressure >= 6)
    if task_type in {"records", "archive"}:
        priority += int(house.inspection_risk >= 6)
    return max(4, min(10, priority))


def _status_for_window(*, now, start, end) -> str:
    if start <= now <= end:
        return "active"
    if end < now:
        return "completed"
    return "planned"
