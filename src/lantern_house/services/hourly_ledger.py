# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import HourlyBeatLedgerConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import HourlyProgressLedgerSnapshot
from lantern_house.utils.time import ensure_utc, floor_to_hour, utcnow


class HourlyBeatLedgerService:
    def __init__(self, repository: StoryRepository, config: HourlyBeatLedgerConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None) -> HourlyProgressLedgerSnapshot:
        if not self.config.enabled:
            return (
                self.repository.get_latest_hourly_progress_ledger()
                or HourlyProgressLedgerSnapshot()
            )
        now = ensure_utc(now or utcnow())
        bucket_start = floor_to_hour(now)
        bucket_end = bucket_start + timedelta(hours=1)
        threshold = max(1, self.config.meaningful_significance_threshold)
        events = self.repository.list_recent_events(
            hours=max(1, self.config.enforce_progression_window_hours),
            limit=80,
            minimum_significance=1,
        )
        bucket_events = [
            event for event in events if bucket_start <= ensure_utc(event.created_at) < bucket_end
        ]

        trust_shift_count = _count_types(bucket_events, {"relationship"}, threshold)
        desire_shift_count = _count_types(bucket_events, {"romance"}, threshold)
        evidence_shift_count = _count_types(
            bucket_events, {"clue", "reveal", "question"}, threshold
        )
        debt_shift_count = _count_types(bucket_events, {"financial"}, threshold)
        power_shift_count = _count_types(bucket_events, {"conflict", "threat", "reveal"}, threshold)
        loyalty_shift_count = _count_types(
            bucket_events, {"alliance", "relationship", "conflict"}, threshold
        )
        meaningful_progressions = sum(
            1
            for value in (
                trust_shift_count,
                desire_shift_count,
                evidence_shift_count,
                debt_shift_count,
                power_shift_count,
                loyalty_shift_count,
            )
            if value > 0
        )
        contract_met = meaningful_progressions >= 1
        dominant_axis = _dominant_axis(
            {
                "trust": trust_shift_count,
                "desire": desire_shift_count,
                "evidence": evidence_shift_count,
                "debt": debt_shift_count,
                "power": power_shift_count,
                "loyalty": loyalty_shift_count,
            }
        )
        blockers = _blockers(
            contract_met=contract_met,
            bucket_events=bucket_events,
            dominant_axis=dominant_axis,
        )
        recommended_push = _recommended_push(
            trust_shift_count=trust_shift_count,
            desire_shift_count=desire_shift_count,
            evidence_shift_count=evidence_shift_count,
            debt_shift_count=debt_shift_count,
            power_shift_count=power_shift_count,
            loyalty_shift_count=loyalty_shift_count,
        )
        return self.repository.save_hourly_progress_ledger(
            snapshot=HourlyProgressLedgerSnapshot(
                bucket_start_at=bucket_start,
                bucket_end_at=bucket_end,
                meaningful_progressions=meaningful_progressions,
                trust_shift_count=trust_shift_count,
                desire_shift_count=desire_shift_count,
                evidence_shift_count=evidence_shift_count,
                debt_shift_count=debt_shift_count,
                power_shift_count=power_shift_count,
                loyalty_shift_count=loyalty_shift_count,
                contract_met=contract_met,
                dominant_axis=dominant_axis,
                blockers=blockers,
                recommended_push=recommended_push,
                metadata={
                    "event_count": len(bucket_events),
                    "event_titles": [event.title for event in bucket_events[:6]],
                },
            ),
            now=now,
        )


def _count_types(bucket_events, event_types: set[str], threshold: int) -> int:
    return sum(
        1
        for event in bucket_events
        if event.event_type in event_types and event.significance >= threshold
    )


def _dominant_axis(axis_counts: dict[str, int]) -> str:
    winner, score = max(axis_counts.items(), key=lambda item: item[1], default=("none", 0))
    return winner if score > 0 else "none"


def _blockers(*, contract_met: bool, bucket_events, dominant_axis: str) -> list[str]:
    blockers: list[str] = []
    if not contract_met:
        blockers.append("No irreversible hourly shift landed yet.")
    if len(bucket_events) >= 4 and dominant_axis == "none":
        blockers.append(
            "Events are happening, but they are not changing trust, desire, evidence, "
            "debt, power, or loyalty."
        )
    if dominant_axis in {"none", "trust", "loyalty"} and not any(
        event.event_type in {"clue", "reveal", "question"} for event in bucket_events
    ):
        blockers.append("Mystery momentum is too soft for recap and theory value.")
    return blockers[:3]


def _recommended_push(
    *,
    trust_shift_count: int,
    desire_shift_count: int,
    evidence_shift_count: int,
    debt_shift_count: int,
    power_shift_count: int,
    loyalty_shift_count: int,
) -> list[str]:
    pushes: list[str] = []
    if evidence_shift_count == 0:
        pushes.append("Plant one sharper clue, contradiction, or dangerous question.")
    if desire_shift_count == 0:
        pushes.append(
            "Use jealousy, near-confession, or interrupted intimacy to raise desire heat."
        )
    if debt_shift_count == 0:
        pushes.append("Bring money, inspections, repairs, or payroll back into the room.")
    if power_shift_count == 0:
        pushes.append("End the next exchange on a threat, leverage move, or status reversal.")
    if trust_shift_count == 0 and loyalty_shift_count == 0:
        pushes.append("Force a loyalty choice or relationship fracture with visible consequence.")
    return pushes[:4]
