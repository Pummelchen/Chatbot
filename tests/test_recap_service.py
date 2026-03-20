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

