# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import re
from collections import defaultdict

from lantern_house.config import WorldTrackingConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    EventCandidate,
    ObjectPossessionSnapshot,
    TimelineFactSnapshot,
)
from lantern_house.utils.time import ensure_utc, utcnow


class WorldTrackingService:
    def __init__(self, repository: StoryRepository, config: WorldTrackingConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None, force: bool = False) -> None:
        if not self.config.enabled and not force:
            return
        now = ensure_utc(now or utcnow())
        positions = self.repository.list_character_positions()
        facts = [
            TimelineFactSnapshot(
                fact_type="presence",
                subject_slug=item["slug"],
                location_slug=item.get("location_slug"),
                location_name=item.get("location_name") or "",
                summary=(
                    f"{item['full_name']} was last placed in "
                    f"{item.get('location_name') or 'an unknown room'}."
                ),
                confidence=8,
                source="world-tracking",
                metadata={"occupancy": True},
                created_at=now,
            )
            for item in positions
            if _is_grounded_location(item.get("location_name"))
        ]
        facts.extend(self._house_anchor_facts(now=now))
        self.repository.record_timeline_facts(facts=facts, now=now)
        self.repository.sync_object_possessions(
            snapshots=[
                ObjectPossessionSnapshot(
                    object_slug=item["slug"],
                    object_name=item["name"],
                    holder_character_slug=item.get("holder_character_slug"),
                    location_slug=item.get("location_slug"),
                    location_name=item.get("location_name") or "",
                    possession_status=item.get("possession_status") or "room",
                    summary=item.get("summary")
                    or (
                        f"{item['name']} is currently tied to "
                        f"{item.get('location_name') or 'the house'}."
                    ),
                    confidence=8,
                    metadata={"seeded": item.get("seeded", False)},
                    last_seen_at=now,
                    created_at=now,
                )
                for item in self.repository.list_story_objects()
            ],
            now=now,
        )

    def capture_turn(
        self,
        *,
        packet: CharacterContextPacket,
        turn: CharacterTurn,
        events: list[EventCandidate],
        now=None,
    ) -> None:
        if not self.config.enabled or not self.config.refresh_every_turn:
            return
        now = ensure_utc(now or utcnow())
        positions = self.repository.list_character_positions()
        locations = self.repository.list_locations()
        objects = self.repository.list_story_objects()
        facts = [
            TimelineFactSnapshot(
                fact_type="presence",
                subject_slug=packet.character_slug,
                location_slug=_location_slug_for_name(packet.current_location, locations),
                location_name=packet.current_location,
                summary=f"{packet.full_name} spoke from {packet.current_location}.",
                confidence=9,
                source="public-turn",
                metadata={"tone": turn.tone or "", "event_count": len(events)},
                created_at=now,
            )
        ]
        facts.extend(
            _extract_alibi_facts(
                speaker_slug=packet.character_slug,
                speaker_name=packet.full_name,
                message=turn.public_message,
                positions=positions,
                locations=locations,
                now=now,
            )
        )
        facts.extend(self._house_anchor_facts(now=now))
        if (
            any(event.event_type.value in {"clue", "question", "reveal"} for event in events)
            and turn.new_questions
        ):
            facts.append(
                TimelineFactSnapshot(
                    fact_type="timeline-question",
                    subject_slug=packet.character_slug,
                    summary=turn.new_questions[0][:220],
                    confidence=6,
                    source="public-turn",
                    metadata={"event_titles": [event.title for event in events[:2]]},
                    created_at=now,
                )
            )
        self.repository.record_timeline_facts(facts=facts, now=now)

        possession_updates = _extract_possession_updates(
            speaker_slug=packet.character_slug,
            message=turn.public_message,
            current_location=packet.current_location,
            locations=locations,
            objects=objects,
            now=now,
        )
        if possession_updates:
            self.repository.sync_object_possessions(snapshots=possession_updates, now=now)

    def _house_anchor_facts(self, *, now) -> list[TimelineFactSnapshot]:
        house = self.repository.get_house_state_snapshot()
        facts: list[TimelineFactSnapshot] = []
        if 0 < house.payroll_due_in_hours <= self.config.money_deadline_hours:
            facts.append(
                TimelineFactSnapshot(
                    fact_type="money-deadline",
                    subject_slug="house",
                    summary=(
                        f"Payroll is due in {house.payroll_due_in_hours} hours and the house "
                        f"is burning {house.hourly_burn_rate} per hour."
                    ),
                    confidence=9,
                    source="house-state",
                    metadata={
                        "payroll_due_in_hours": house.payroll_due_in_hours,
                        "cash_on_hand": house.cash_on_hand,
                    },
                    created_at=now,
                )
            )
        if house.repair_backlog > 0 or house.weather_pressure >= 6:
            facts.append(
                TimelineFactSnapshot(
                    fact_type="repair-state",
                    subject_slug="house",
                    summary=(
                        f"Repair backlog is {house.repair_backlog} and weather pressure is "
                        f"{house.weather_pressure}."
                    ),
                    confidence=8,
                    source="house-state",
                    metadata={
                        "repair_backlog": house.repair_backlog,
                        "weather_pressure": house.weather_pressure,
                        "active_pressures": [item.label for item in house.active_pressures[:2]],
                    },
                    created_at=now,
                )
            )
        return facts


def build_room_occupancy_digest(positions: list[dict], *, max_rooms: int = 4) -> list[str]:
    occupancy: dict[str, list[str]] = defaultdict(list)
    for item in positions:
        room = item.get("location_name") or "Unknown"
        if not _is_grounded_location(room):
            continue
        occupancy[room].append(item.get("slug") or "unknown")
    digest: list[str] = []
    for room, occupants in occupancy.items():
        digest.append(f"{room}: {', '.join(occupants[:4])}")
    digest.sort()
    return digest[:max_rooms]


def _extract_alibi_facts(
    *,
    speaker_slug: str,
    speaker_name: str,
    message: str,
    positions: list[dict],
    locations: list[dict],
    now,
) -> list[TimelineFactSnapshot]:
    lowered = message.lower()
    facts: list[TimelineFactSnapshot] = []
    character_aliases = {
        item["slug"]: {
            item["slug"],
            item["full_name"].split()[0].lower(),
            item["full_name"].lower(),
        }
        for item in positions
    }
    for location in locations:
        aliases = {
            location["slug"].replace("-", " "),
            location["name"].lower(),
            *[part for part in location["slug"].split("-") if len(part) > 3],
        }
        if not any(alias in lowered for alias in aliases if alias):
            continue
        if re.search(r"\bi was\b|\bi stayed\b|\bi left\b|\bi came from\b", lowered):
            facts.append(
                TimelineFactSnapshot(
                    fact_type="alibi",
                    subject_slug=speaker_slug,
                    location_slug=location["slug"],
                    location_name=location["name"],
                    summary=f"{speaker_name} claimed prior presence at {location['name']}.",
                    confidence=5,
                    source="public-turn",
                    metadata={"message_excerpt": message[:180]},
                    created_at=now,
                )
            )
            continue
        for slug, aliases_for_character in character_aliases.items():
            if slug == speaker_slug:
                continue
            if not any(alias in lowered for alias in aliases_for_character):
                continue
            facts.append(
                TimelineFactSnapshot(
                    fact_type="alibi-claim",
                    subject_slug=slug,
                    related_slug=speaker_slug,
                    location_slug=location["slug"],
                    location_name=location["name"],
                    summary=f"{speaker_name} placed {slug} at {location['name']}.",
                    confidence=4,
                    source="public-turn",
                    metadata={"message_excerpt": message[:180]},
                    created_at=now,
                )
            )
            break
    return facts[:3]


def _extract_possession_updates(
    *,
    speaker_slug: str,
    message: str,
    current_location: str,
    locations: list[dict],
    objects: list[dict],
    now,
) -> list[ObjectPossessionSnapshot]:
    lowered = message.lower()
    updates: list[ObjectPossessionSnapshot] = []
    for item in objects:
        aliases = {
            item["slug"].replace("-", " "),
            item["name"].lower(),
            *[part for part in item["slug"].split("-") if len(part) > 3],
        }
        if not any(alias in lowered for alias in aliases if alias):
            continue
        location_slug = item.get("location_slug")
        location_name = item.get("location_name") or current_location
        status = item.get("possession_status") or "room"
        holder = item.get("holder_character_slug")
        if re.search(r"\bi have\b|\bwith me\b|\bin my pocket\b|\bi kept\b", lowered):
            holder = speaker_slug
            status = "carried"
            location_slug = _location_slug_for_name(current_location, locations)
            location_name = current_location
        elif re.search(r"\bon the\b|\bat the\b|\binside the\b|\bin the\b", lowered):
            matched_location = _match_location_from_text(message, locations)
            if matched_location:
                holder = None
                location_slug = matched_location["slug"]
                location_name = matched_location["name"]
                status = "room"
        else:
            continue
        updates.append(
            ObjectPossessionSnapshot(
                object_slug=item["slug"],
                object_name=item["name"],
                holder_character_slug=holder,
                location_slug=location_slug,
                location_name=location_name,
                possession_status=status,
                summary=(
                    f"{item['name']} was last grounded with "
                    f"{holder or location_name or 'the house'}."
                ),
                confidence=6,
                metadata={"message_excerpt": message[:180]},
                last_seen_at=now,
                created_at=now,
            )
        )
    return updates[:2]


def _location_slug_for_name(name: str, locations: list[dict]) -> str | None:
    lowered = name.lower()
    for location in locations:
        if location["name"].lower() == lowered:
            return location["slug"]
    return None


def _match_location_from_text(message: str, locations: list[dict]) -> dict | None:
    lowered = message.lower()
    for location in locations:
        aliases = {location["name"].lower(), location["slug"].replace("-", " ")}
        if any(alias in lowered for alias in aliases):
            return location
    return None


def _is_grounded_location(value: str | None) -> bool:
    if value is None:
        return False
    compact = " ".join(str(value).split()).strip().lower()
    return compact not in {"", "unknown", "unspecified", "none"}
