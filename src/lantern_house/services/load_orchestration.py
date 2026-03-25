# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import LoadOrchestrationConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import LoadProfileSnapshot
from lantern_house.utils.time import ensure_utc, utcnow


class LoadOrchestrationService:
    def __init__(self, repository: StoryRepository, config: LoadOrchestrationConfig) -> None:
        self.repository = repository
        self.config = config

    def build_profile(
        self,
        *,
        pending_manager_prefetch: bool,
        pending_background_jobs: int,
        now=None,
    ) -> LoadProfileSnapshot:
        now = ensure_utc(now or utcnow())
        if not self.config.enabled:
            return LoadProfileSnapshot(created_at=now)

        run_state = self.repository.get_run_state()
        recent_metrics = self.repository.list_recent_message_metrics(
            limit=max(3, self.config.recent_message_window)
        )
        latencies = sorted(item["latency_ms"] for item in recent_metrics if item["latency_ms"] > 0)
        average_latency = int(sum(latencies) / len(latencies)) if latencies else 0
        p95_latency = latencies[int((len(latencies) - 1) * 0.95)] if latencies else 0
        metadata = run_state.get("metadata", {})
        recent_failures = int(metadata.get("recent_failure_count", 0))
        degraded_mode = bool(run_state.get("degraded_mode"))
        background_pressure = min(
            10,
            pending_background_jobs * 3 + int(pending_manager_prefetch) * 2,
        )
        load_tier = _tier(
            average_latency=average_latency,
            p95_latency=p95_latency,
            recent_failures=recent_failures,
            degraded_mode=degraded_mode,
            config=self.config,
        )
        recommended_actions = _actions(
            load_tier=load_tier,
            pending_manager_prefetch=pending_manager_prefetch,
            background_pressure=background_pressure,
        )
        return LoadProfileSnapshot(
            load_tier=load_tier,
            average_latency_ms=average_latency,
            p95_latency_ms=p95_latency,
            recent_failures=recent_failures,
            degraded_mode=degraded_mode,
            pending_manager_prefetch=pending_manager_prefetch,
            background_pressure=background_pressure,
            recommended_actions=recommended_actions,
            metadata={
                "measured_at": now.isoformat(),
                "sample_size": len(latencies),
            },
            created_at=now,
        )


def _tier(
    *,
    average_latency: int,
    p95_latency: int,
    recent_failures: int,
    degraded_mode: bool,
    config: LoadOrchestrationConfig,
) -> str:
    if (
        degraded_mode
        or recent_failures >= config.critical_failure_streak
        or average_latency >= config.critical_latency_ms
        or p95_latency >= config.critical_latency_ms
    ):
        return "critical"
    if (
        recent_failures >= config.high_failure_streak
        or average_latency >= config.high_latency_ms
        or p95_latency >= config.high_latency_ms
    ):
        return "high"
    if average_latency >= max(1000, config.high_latency_ms // 2) or recent_failures > 0:
        return "medium"
    return "low"


def _actions(
    *,
    load_tier: str,
    pending_manager_prefetch: bool,
    background_pressure: int,
) -> list[str]:
    if load_tier == "critical":
        return [
            "use-deterministic-fallbacks-first",
            "skip-repair-model",
            "defer-god-ai-refresh",
            "suppress-noncritical-background-work",
        ]
    if load_tier == "high":
        actions = [
            "prefer-prefetched-or-fallback-manager",
            "skip-repair-model-for-nonfatal-turns",
            "limit-background-work",
        ]
        if pending_manager_prefetch:
            actions.append("do-not-start-another-manager-prefetch")
        return actions[:4]
    if load_tier == "medium":
        actions = ["keep-manager-prefetch-ready", "allow-one-background-job"]
        if background_pressure >= 6:
            actions.append("avoid-extra-background-spikes")
        return actions[:3]
    return ["prefetch-manager", "allow-repair-model", "keep-background-strategy-warm"]
