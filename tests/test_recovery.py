# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.db.repository import StoryRepository
from lantern_house.runtime.recovery import RecoveryService
from lantern_house.utils.time import floor_to_hour, utcnow


def test_repository_lists_all_missing_recap_hours_since_last_public_message() -> None:
    now = floor_to_hour(utcnow()) + timedelta(minutes=15)
    repository = StoryRepository.__new__(StoryRepository)
    repository.get_run_state = lambda: {
        "last_recap_hour": None,
        "last_public_message_at": now - timedelta(hours=3, minutes=20),
    }
    hours = repository.list_missing_recap_hours(now=now)
    assert hours == [
        floor_to_hour(now - timedelta(hours=3)),
        floor_to_hour(now - timedelta(hours=2)),
        floor_to_hour(now - timedelta(hours=1)),
        floor_to_hour(now),
    ]


def test_recovery_flags_unclean_shutdown_and_preserves_checkpoint() -> None:
    captured_flags = []

    class FakeRepository:
        def mark_runtime_starting(self, *, now=None):
            return {
                "status": "running",
                "metadata": {
                    "runtime_phase": "character-request",
                    "checkpoint": {
                        "checkpoint_at": "2026-03-21T10:59:00+00:00",
                        "reason": "heartbeat",
                    },
                },
            }

        def list_missing_recap_hours(self, *, now=None):
            return []

        def add_continuity_flags(self, flags):
            captured_flags.extend(flags)

    recovery = RecoveryService(FakeRepository()).recover()
    assert recovery["unclean_shutdown"] is True
    assert recovery["checkpoint"]["reason"] == "heartbeat"
    assert len(captured_flags) == 1
    assert captured_flags[0].flag_type == "unclean-shutdown"
