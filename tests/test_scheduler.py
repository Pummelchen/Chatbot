from __future__ import annotations

import random
from datetime import timedelta

from lantern_house.config import RuntimeConfig, ThoughtPulseConfig, TimingConfig
from lantern_house.runtime.scheduler import TurnScheduler
from lantern_house.utils.time import utcnow


def test_scheduler_prefers_silenced_character() -> None:
    scheduler = TurnScheduler(
        runtime_config=RuntimeConfig(),
        timing_config=TimingConfig(),
        thought_pulse_config=ThoughtPulseConfig(),
        rng=random.Random(4),
    )
    decision = scheduler.select_speaker(
        directive={
            "active_character_slugs": ["mara", "nia"],
            "speaker_weights": {"mara": 1.0, "nia": 1.0},
        },
        character_states=[
            {"slug": "mara", "last_spoke_at": utcnow(), "silence_streak": 0},
            {"slug": "nia", "last_spoke_at": utcnow() - timedelta(minutes=5), "silence_streak": 4},
        ],
    )
    assert decision == "nia"


def test_scheduler_enforces_thought_pulse_budget() -> None:
    scheduler = TurnScheduler(
        runtime_config=RuntimeConfig(),
        timing_config=TimingConfig(),
        thought_pulse_config=ThoughtPulseConfig(hourly_budget=2, cooldown_minutes=20),
        rng=random.Random(1),
    )
    allowed = scheduler.allow_thought_pulse(
        directive={"thought_pulse": {"allowed": True, "character_slug": "mara"}},
        speaker_slug="mara",
        run_state={"last_thought_pulse_at": utcnow() - timedelta(minutes=25)},
        recent_pulse_count=1,
    )
    blocked = scheduler.allow_thought_pulse(
        directive={"thought_pulse": {"allowed": True, "character_slug": "mara"}},
        speaker_slug="mara",
        run_state={"last_thought_pulse_at": utcnow() - timedelta(minutes=25)},
        recent_pulse_count=2,
    )
    assert allowed is True
    assert blocked is False

