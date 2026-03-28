# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import GuestCirculationConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import BeatPlanItem, GuestProfileSnapshot
from lantern_house.utils.time import ensure_utc, isoformat, utcnow

_GUEST_TEMPLATES = [
    {
        "key": "permit-clerk",
        "display_name": "Elsie Rowan",
        "role": "permit clerk",
        "pressure_tags": ["inspection", "paperwork", "class"],
        "summary": "A permit clerk who never raises her voice while making everybody feel behind.",
        "hook": "She asks for the binder nobody wants to open in front of the room.",
        "linked_location_slug": "front-desk",
        "trigger": "inspection",
    },
    {
        "key": "travel-creator",
        "display_name": "Nadia Bloom",
        "role": "travel creator",
        "pressure_tags": ["reputation", "clip", "status"],
        "summary": (
            "A charming travel creator whose camera turns private embarrassment "
            "into public risk."
        ),
        "hook": "She frames the house as romantic content exactly when someone needs privacy.",
        "linked_location_slug": "front-desk",
        "trigger": "reputation",
    },
    {
        "key": "debt-liaison",
        "display_name": "Mateo Quill",
        "role": "collections liaison",
        "pressure_tags": ["debt", "money", "threat"],
        "summary": "A debt liaison who smiles like a host while talking like foreclosure.",
        "hook": "He arrives politely to discuss money the house does not have.",
        "linked_location_slug": "front-desk",
        "trigger": "cash",
    },
    {
        "key": "ferry-captain",
        "display_name": "Basri Halim",
        "role": "retired ferry captain",
        "pressure_tags": ["witness", "history", "community"],
        "summary": (
            "A long-memory regular who knows the harbor rumors older residents "
            "stopped repeating."
        ),
        "hook": "He recognizes a name or object that the house wanted buried in memory.",
        "linked_location_slug": "lobby",
        "trigger": "memory",
    },
    {
        "key": "storm-stranded-musician",
        "display_name": "Soraya Finch",
        "role": "storm-stranded musician",
        "pressure_tags": ["weather", "chemistry", "performance"],
        "summary": (
            "A stranded musician who turns delays into candlelit intimacy and "
            "fresh jealousy."
        ),
        "hook": "She needs a room and a favor while the weather makes everybody too available.",
        "linked_location_slug": "lobby",
        "trigger": "weather",
    },
]


class GuestCirculationService:
    def __init__(self, repository: StoryRepository, config: GuestCirculationConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None, force: bool = False) -> list[GuestProfileSnapshot]:
        now = ensure_utc(now or utcnow())
        existing = self.repository.list_active_guest_profiles(limit=self.config.max_active_guests)
        if (
            not force
            and not self.config.enabled
            and existing
        ):
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
        profiles = self._select_profiles(world=world, house=house, now=now)
        persisted = self.repository.sync_guest_profiles(profiles=profiles, now=now)
        self._sync_guest_beats(profiles=persisted, now=now)
        return persisted

    def _select_profiles(self, *, world: dict, house, now) -> list[GuestProfileSnapshot]:
        story_day = int(world.get("current_story_day") or 1)
        inspection_risk = int(getattr(house, "inspection_risk", 0) or 0)
        cash_on_hand = int(getattr(house, "cash_on_hand", 0) or 0)
        hourly_burn_rate = int(getattr(house, "hourly_burn_rate", 0) or 0)
        payroll_due_in_hours = int(getattr(house, "payroll_due_in_hours", 0) or 0)
        reputation_risk = int(getattr(house, "reputation_risk", 0) or 0)
        weather_pressure = int(getattr(house, "weather_pressure", 0) or 0)
        chosen: list[dict[str, str | list[str]]] = []
        if inspection_risk >= 6:
            chosen.append(_template("permit-clerk"))
        if cash_on_hand <= max(600, hourly_burn_rate * 36) or payroll_due_in_hours <= 48:
            chosen.append(_template("debt-liaison"))
        if reputation_risk >= 6:
            chosen.append(_template("travel-creator"))
        if weather_pressure >= 6:
            chosen.append(_template("storm-stranded-musician"))
        chosen.append(_template("ferry-captain"))

        ordered = []
        seen = set()
        for item in chosen:
            if item["key"] in seen:
                continue
            seen.add(item["key"])
            ordered.append(item)

        if len(ordered) < self.config.max_active_guests:
            rotation = [
                template
                for template in _GUEST_TEMPLATES
                if template["key"] not in seen
            ]
            if rotation:
                ordered.append(rotation[story_day % len(rotation)])

        return [
            GuestProfileSnapshot(
                guest_key=str(item["key"]),
                display_name=str(item["display_name"]),
                role=str(item["role"]),
                pressure_tags=list(item["pressure_tags"]),
                summary=str(item["summary"]),
                hook=str(item["hook"]),
                linked_location_slug=str(item["linked_location_slug"]),
                metadata={
                    "trigger": item["trigger"],
                    "story_day": story_day,
                    "refreshed_at": isoformat(now),
                },
                updated_at=now,
            )
            for item in ordered[: self.config.max_active_guests]
        ]

    def _sync_guest_beats(self, *, profiles: list[GuestProfileSnapshot], now) -> None:
        if not profiles:
            return
        items = [
            BeatPlanItem(
                beat_key=f"guest-{profile.guest_key}",
                beat_type="guest-circulation",
                objective=f"{profile.display_name} pressures the room: {profile.hook}",
                significance=6,
                ready_at=isoformat(now),
                keywords=[profile.display_name.split()[0], *profile.pressure_tags[:2]],
                metadata={
                    "guest_key": profile.guest_key,
                    "role": profile.role,
                    "pressure_tags": profile.pressure_tags,
                },
            )
            for profile in profiles[: self.config.max_pending_guest_beats]
        ]
        sync_beats = getattr(self.repository, "sync_beats", None)
        if callable(sync_beats):
            try:
                sync_beats(
                    beat_type="guest-circulation",
                    items=items,
                    source_key="guest-circulation",
                    now=now,
                )
            except RuntimeError:
                return


def _template(key: str) -> dict:
    for item in _GUEST_TEMPLATES:
        if item["key"] == key:
            return dict(item)
    raise KeyError(key)
