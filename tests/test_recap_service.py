# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.domain.contracts import EventView
from lantern_house.services.recaps import RecapService
from lantern_house.utils.time import utcnow


class FakeRepository:
    def load_events_for_window(self, *, bucket_end_at, hours: int):
        now = bucket_end_at
        if hours == 1:
            return [
                EventView(
                    event_type="clue",
                    title="Brass key resurfaces",
                    details="Nia reacted too fast when the key came up.",
                    significance=8,
                    payload={},
                    created_at=now - timedelta(minutes=30),
                ),
                EventView(
                    event_type="romance",
                    title="Near-confession stalls out",
                    details="Mara and Elias nearly admitted too much.",
                    significance=7,
                    payload={},
                    created_at=now - timedelta(minutes=10),
                ),
            ]
        return []

    def list_recent_summaries(self, limit=4):
        return []


class BrokenLLM:
    async def generate_json(self, **kwargs):
        raise RuntimeError("fail")


async def test_recap_service_fallback_uses_structured_events() -> None:
    service = RecapService(FakeRepository(), BrokenLLM(), "gemma3:4b")
    bundle = await service.generate_bundle(bucket_end_at=utcnow())
    assert "Brass key resurfaces" in bundle.one_hour.headline
    assert bundle.one_hour.clues
    assert bundle.twelve_hours.headline.startswith("Last 12 hours")


def test_recap_service_window_digest_stays_bounded() -> None:
    now = utcnow()
    service = RecapService(FakeRepository(), BrokenLLM(), "gemma3:4b")
    events = [
        EventView(
            event_type="clue" if index % 2 == 0 else "question",
            title=f"Event {index}",
            details=f"Detail {index}",
            significance=(index % 10) + 1,
            payload={},
            created_at=now - timedelta(minutes=index),
        )
        for index in range(40)
    ]
    digest = service._window_digest(events)
    assert digest["event_count"] == 40
    assert len(digest["top_events"]) == 8
    assert len(digest["latest_events"]) == 5
    assert len(digest["open_questions"]) <= 5
