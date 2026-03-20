from __future__ import annotations

import random
from datetime import timedelta

from lantern_house.config import RuntimeConfig, ThoughtPulseConfig, TimingConfig
from lantern_house.domain.contracts import PacingHealthReport, StoryGovernanceReport
from lantern_house.utils.time import ensure_utc, utcnow


class TurnScheduler:
    def __init__(
        self,
        *,
        runtime_config: RuntimeConfig,
        timing_config: TimingConfig,
        thought_pulse_config: ThoughtPulseConfig,
        rng: random.Random | None = None,
    ) -> None:
        self.runtime_config = runtime_config
        self.timing_config = timing_config
        self.thought_pulse_config = thought_pulse_config
        self.rng = rng or random.Random()

    def should_refresh_manager(
        self,
        *,
        run_state: dict,
        directive: dict | None,
        health: PacingHealthReport,
        governance: StoryGovernanceReport | None = None,
    ) -> bool:
        if directive is None:
            return True
        messages_since = max(0, run_state["last_tick_no"] - directive["tick_no"])
        if messages_since >= self.runtime_config.manager_step_interval_messages:
            return True
        if health.score < 60:
            return True
        if governance and (
            governance.viewer_value_score < 70
            or not governance.hourly_progression_met
            or governance.core_drift
            or governance.robotic_voice_risk
        ):
            return True
        created_at = directive["created_at"]
        if created_at is not None and utcnow() - ensure_utc(created_at) > timedelta(minutes=10):
            return True
        return False

    def should_prefetch_manager(
        self,
        *,
        run_state: dict,
        directive: dict | None,
        health: PacingHealthReport,
        governance: StoryGovernanceReport | None = None,
    ) -> bool:
        if directive is None:
            return False
        messages_since = max(0, run_state["last_tick_no"] - directive["tick_no"])
        if messages_since >= self.runtime_config.manager_prefetch_threshold_messages:
            return True
        if health.score < 75:
            return True
        if governance and governance.viewer_value_score < 82:
            return True
        created_at = directive.get("created_at")
        if created_at is not None and utcnow() - ensure_utc(created_at) > timedelta(minutes=6):
            return True
        return False

    def select_speaker(self, *, directive: dict, character_states: list[dict]) -> str:
        active = directive.get("active_character_slugs") or [
            item["slug"] for item in character_states
        ]
        weights = directive.get("speaker_weights", {})
        now = utcnow()
        weighted: list[tuple[str, float]] = []
        for state in character_states:
            if state["slug"] not in active:
                continue
            weight = float(weights.get(state["slug"], 1.0))
            if state["last_spoke_at"]:
                last_spoke_at = ensure_utc(state["last_spoke_at"])
                if now - last_spoke_at < timedelta(seconds=45):
                    weight *= 0.45
            weight *= 1 + min(state["silence_streak"], 5) * 0.18
            weighted.append((state["slug"], max(0.05, weight)))
        return self._weighted_choice(weighted)

    def compute_delay_seconds(self, *, health: PacingHealthReport | None = None) -> float:
        roll = self.rng.random()
        if roll < self.timing_config.burst_probability:
            return self.rng.uniform(
                self.timing_config.burst_min_delay_seconds,
                self.timing_config.burst_max_delay_seconds,
            )
        if roll < self.timing_config.burst_probability + self.timing_config.lull_probability:
            return self.rng.uniform(
                self.timing_config.lull_min_delay_seconds,
                self.timing_config.lull_max_delay_seconds,
            )

        base_min = self.timing_config.min_delay_seconds
        base_max = self.timing_config.max_delay_seconds
        if health and health.low_progression:
            base_min = max(0.7, base_min - 0.3)
            base_max = max(base_min + 0.2, base_max - 0.6)
        return self.rng.uniform(base_min, base_max)

    def allow_thought_pulse(
        self,
        *,
        directive: dict,
        speaker_slug: str,
        run_state: dict,
        recent_pulse_count: int,
    ) -> bool:
        pulse = directive.get("thought_pulse") or {}
        if not pulse.get("allowed"):
            return False
        if pulse.get("character_slug") != speaker_slug:
            return False
        if recent_pulse_count >= self.thought_pulse_config.hourly_budget:
            return False
        last_pulse = run_state.get("last_thought_pulse_at")
        if last_pulse and utcnow() - ensure_utc(last_pulse) < timedelta(
            minutes=self.thought_pulse_config.cooldown_minutes
        ):
            return False
        return True

    def _weighted_choice(self, weighted_items: list[tuple[str, float]]) -> str:
        if not weighted_items:
            raise RuntimeError("No candidate speakers were available for scheduling.")
        total = sum(weight for _, weight in weighted_items)
        if total <= 0:
            return weighted_items[0][0]
        threshold = self.rng.uniform(0, total)
        cumulative = 0.0
        for item, weight in weighted_items:
            cumulative += weight
            if cumulative >= threshold:
                return item
        return weighted_items[-1][0]
