# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import InferenceGovernorConfig
from lantern_house.domain.contracts import InferencePolicySnapshot, LoadProfileSnapshot
from lantern_house.utils.time import ensure_utc, utcnow


class InferenceGovernorService:
    def __init__(self, config: InferenceGovernorConfig) -> None:
        self.config = config

    def policy_for(
        self,
        *,
        role: str,
        load_profile: LoadProfileSnapshot | None,
        now=None,
    ) -> InferencePolicySnapshot:
        now = ensure_utc(now or utcnow())
        load_tier = (load_profile.load_tier if load_profile else "low").lower()
        base_timeout = self._base_timeout(load_tier)
        multiplier = float(self.config.role_timeout_multipliers.get(role, 1.0))
        timeout_seconds = max(4, round(base_timeout * multiplier))
        max_retries = self._retry_budget(role=role, load_tier=load_tier)
        allow_model_call = self._allow_model_call(role=role, load_tier=load_tier)
        notes: list[str] = []

        if load_profile and load_profile.recommended_actions:
            notes.extend(load_profile.recommended_actions[:2])
        if not allow_model_call:
            notes.append("Governor disabled this model call under current load.")
        if load_tier in {"high", "critical"}:
            notes.append("Prefer bounded response time over optimal prose quality.")

        return InferencePolicySnapshot(
            role=role,
            load_tier=load_tier,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            allow_model_call=allow_model_call,
            fallback_mode="service-fallback" if allow_model_call else "deterministic-fallback",
            cancellation_mode="timeout",
            keep_warm=(
                self.config.enabled
                and load_tier == "low"
                and role in self.config.prewarm_roles_when_low
            ),
            notes=notes[:4],
            metadata={
                "average_latency_ms": load_profile.average_latency_ms if load_profile else 0,
                "p95_latency_ms": load_profile.p95_latency_ms if load_profile else 0,
                "background_pressure": load_profile.background_pressure if load_profile else 0,
            },
            created_at=now,
        )

    def build_digest(self, *, load_profile: LoadProfileSnapshot | None, now=None) -> list[str]:
        roles = ("manager", "character", "repair", "god_ai")
        policies = [
            self.policy_for(role=role, load_profile=load_profile, now=now)
            for role in roles
        ]
        digest: list[str] = []
        for policy in policies:
            state = "live" if policy.allow_model_call else "fallback"
            digest.append(
                f"{policy.role}: {state}, timeout {policy.timeout_seconds}s, "
                f"retries {policy.max_retries}, tier {policy.load_tier}"
            )
        return digest

    def _base_timeout(self, load_tier: str) -> int:
        if not self.config.enabled:
            return self.config.low_timeout_seconds
        if load_tier == "critical":
            return self.config.critical_timeout_seconds
        if load_tier == "high":
            return self.config.high_timeout_seconds
        if load_tier == "medium":
            return self.config.medium_timeout_seconds
        return self.config.low_timeout_seconds

    def _retry_budget(self, *, role: str, load_tier: str) -> int:
        base = int(self.config.base_retry_budget.get(role, 1))
        if not self.config.enabled:
            return base
        if load_tier == "critical":
            return 0 if role in {"repair", "god_ai"} else min(1, base)
        if load_tier == "high":
            return min(1, base)
        if load_tier == "medium":
            return max(1, base - 1)
        return base

    def _allow_model_call(self, *, role: str, load_tier: str) -> bool:
        if not self.config.enabled:
            return True
        if load_tier == "critical" and role in self.config.disable_roles_under_critical:
            return False
        if load_tier == "high" and role in self.config.disable_roles_under_high:
            return False
        return True
