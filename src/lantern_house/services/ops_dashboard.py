# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import OpsDashboardConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import LoadProfileSnapshot, OpsTelemetrySnapshot
from lantern_house.utils.time import ensure_utc, utcnow


class OpsDashboardService:
    def __init__(self, repository: StoryRepository, config: OpsDashboardConfig) -> None:
        self.repository = repository
        self.config = config

    def capture(
        self,
        *,
        load_profile: LoadProfileSnapshot,
        now=None,
    ) -> OpsTelemetrySnapshot:
        now = ensure_utc(now or utcnow())
        latest = self.repository.get_latest_ops_telemetry()
        if (
            latest
            and latest.created_at
            and now - ensure_utc(latest.created_at)
            < timedelta(seconds=max(1, self.config.telemetry_interval_seconds))
        ):
            return latest
        run_state = self.repository.get_run_state()
        strategic_brief = self.repository.get_latest_strategic_brief(now=now, active_only=False)
        latest_hour = self.repository.get_latest_hourly_progress_ledger()
        story_gravity = self.repository.get_story_gravity_state_snapshot()
        last_recap_hour = run_state.get("last_recap_hour")
        last_checkpoint_at = run_state.get("last_checkpoint_at")
        checkpoint_age = (
            int((now - ensure_utc(last_checkpoint_at)).total_seconds())
            if last_checkpoint_at
            else 999999
        )
        recap_age = (
            int((now - ensure_utc(last_recap_hour)).total_seconds() // 60)
            if last_recap_hour
            else 999999
        )
        strategy_age = (
            int((now - ensure_utc(strategic_brief.created_at)).total_seconds() // 60)
            if strategic_brief and strategic_brief.created_at
            else 999999
        )
        metadata = run_state.get("metadata", {})
        restart_count = int(metadata.get("restart_count", 0))
        auto_remediations = _auto_remediations(
            config=self.config,
            checkpoint_age=checkpoint_age,
            recap_age=recap_age,
            strategy_age=strategy_age,
            load_profile=load_profile,
            latest_hour=latest_hour,
        )
        snapshot = OpsTelemetrySnapshot(
            runtime_status=run_state["status"],
            phase=metadata.get("runtime_phase", "unknown"),
            degraded_mode=bool(run_state.get("degraded_mode")),
            load_tier=load_profile.load_tier,
            average_latency_ms=load_profile.average_latency_ms,
            checkpoint_age_seconds=max(0, checkpoint_age),
            recap_age_minutes=max(0, recap_age),
            strategy_age_minutes=max(0, strategy_age),
            drift_risk=story_gravity.drift_score,
            progression_contract_open=not bool(latest_hour.contract_met) if latest_hour else True,
            restart_count=restart_count,
            active_strategy=strategic_brief.title if strategic_brief else "manager-only",
            auto_remediations=auto_remediations,
            metadata={
                "last_tick_no": run_state["last_tick_no"],
                "last_public_message_at": (
                    ensure_utc(run_state["last_public_message_at"]).isoformat()
                    if run_state.get("last_public_message_at")
                    else None
                ),
                "load_actions": load_profile.recommended_actions,
            },
            created_at=now,
        )
        return self.repository.record_ops_telemetry(snapshot=snapshot, now=now)

    def render_text(self, *, snapshot: OpsTelemetrySnapshot | None = None) -> str:
        current = snapshot or self.repository.get_latest_ops_telemetry()
        if current is None:
            return "No ops telemetry recorded yet."
        lines = [
            (
                f"runtime={current.runtime_status} phase={current.phase} "
                f"degraded={current.degraded_mode}"
            ),
            (
                f"load={current.load_tier} avg_latency_ms={current.average_latency_ms} "
                f"drift_risk={current.drift_risk} strategy={current.active_strategy or 'n/a'}"
            ),
            (
                f"checkpoint_age_s={current.checkpoint_age_seconds} "
                f"recap_age_min={current.recap_age_minutes} "
                f"strategy_age_min={current.strategy_age_minutes} "
                f"restarts={current.restart_count}"
            ),
        ]
        if current.auto_remediations:
            lines.append("auto_remediations=" + ", ".join(current.auto_remediations))
        return "\n".join(lines)


def _auto_remediations(
    *,
    config: OpsDashboardConfig,
    checkpoint_age: int,
    recap_age: int,
    strategy_age: int,
    load_profile: LoadProfileSnapshot,
    latest_hour,
) -> list[str]:
    actions: list[str] = []
    if checkpoint_age >= config.stale_checkpoint_seconds:
        actions.append("force-checkpoint")
    if recap_age >= config.stale_recap_minutes:
        actions.append("backfill-hourly-recaps")
    if strategy_age >= config.stale_strategy_minutes:
        actions.append("refresh-strategic-brief")
    if load_profile.load_tier in {"high", "critical"}:
        actions.append("throttle-background-work")
    if latest_hour and not latest_hour.contract_met:
        actions.append("force-hourly-progression")
    return actions[:5]
