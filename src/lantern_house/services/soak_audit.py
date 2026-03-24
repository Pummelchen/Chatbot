# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import SoakAuditConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import ManagerContextPacket, SoakAuditSnapshot
from lantern_house.services.simulation_lab import SimulationLabService
from lantern_house.utils.time import ensure_utc, utcnow


class SoakAuditService:
    def __init__(
        self,
        repository: StoryRepository,
        simulation_lab: SimulationLabService,
        config: SoakAuditConfig,
    ) -> None:
        self.repository = repository
        self.simulation_lab = simulation_lab
        self.config = config
        self.interval = timedelta(minutes=max(1, config.refresh_interval_minutes))

    def refresh_if_due(
        self,
        context: ManagerContextPacket,
        *,
        now=None,
        force: bool = False,
    ) -> SoakAuditSnapshot | None:
        if not self.config.enabled:
            return self.repository.get_latest_soak_audit()
        now = ensure_utc(now or utcnow())
        latest = self.repository.get_latest_soak_audit()
        if (
            latest
            and not force
            and latest.created_at
            and now - ensure_utc(latest.created_at) < self.interval
        ):
            return latest
        reports = [
            self.simulation_lab.evaluate(
                context,
                horizon_hours=hours,
                turns_per_hour=self.config.turns_per_hour,
            )
            for hours in self.config.horizons_hours
        ]
        winners = [report.candidates[0].strategy_key for report in reports if report.candidates]
        recent_clip_scores = self.repository.list_recent_clip_value_scores(limit=6)
        snapshot = SoakAuditSnapshot(
            horizons_hours=self.config.horizons_hours,
            progression_miss_risk=_risk_from_reports(
                reports,
                marker="under-delivered on progression",
                baseline=25 + int(not context.hourly_ledger.contract_met) * 35,
            ),
            drift_risk=_risk_from_reports(
                reports,
                marker="drifting away",
                baseline=max(
                    context.story_gravity_state.drift_score,
                    context.strategic_brief.danger_of_drift_score if context.strategic_brief else 0,
                ),
            ),
            strategy_lock_risk=_strategy_lock_risk(
                winners, repetitive=context.pacing_health.repetitive
            ),
            recap_decay_risk=min(
                100,
                25
                + len(context.recap_quality_alerts) * 18
                + int(context.story_governance.recap_weakness) * 25,
            ),
            clip_drought_risk=_clip_drought_risk(recent_clip_scores, context=context),
            ship_stagnation_risk=min(
                100,
                22
                + int(context.pacing_health.romance_stalled) * 34
                + int(not any("romance" in item.lower() for item in context.pending_beats)) * 10,
            ),
            unresolved_overload_risk=min(
                100,
                20 + max(0, len(context.unresolved_questions) - 5) * 9,
            ),
            recommended_direction=winners[0] if winners else "house-pressure-first",
            audit_notes=_audit_notes(reports=reports, context=context, winners=winners),
            candidate_pressure=[
                candidate.next_hour_focus
                for report in reports
                for candidate in report.candidates[:1]
            ][:4],
            metadata={
                "winners": winners,
                "generated_at": now.isoformat(),
                "systemic_risks": [report.systemic_risks for report in reports],
            },
        )
        return self.repository.record_soak_audit_run(snapshot=snapshot, now=now)


def _risk_from_reports(reports, *, marker: str, baseline: int) -> int:
    hits = sum(
        1 for report in reports if any(marker in risk.lower() for risk in report.systemic_risks)
    )
    return min(100, baseline + hits * 18)


def _strategy_lock_risk(winners: list[str], *, repetitive: bool) -> int:
    if not winners:
        return 40
    dominant = max(winners.count(item) for item in set(winners))
    return min(100, 20 + dominant * 20 + int(repetitive) * 20)


def _clip_drought_risk(recent_clip_scores, *, context: ManagerContextPacket) -> int:
    if not recent_clip_scores:
        return 55
    average = sum(item["clip_value"] for item in recent_clip_scores) / len(recent_clip_scores)
    return min(
        100,
        max(
            0,
            int(70 - average * 8) + int(context.story_governance.clip_value_score < 55) * 18,
        ),
    )


def _audit_notes(*, reports, context: ManagerContextPacket, winners: list[str]) -> list[str]:
    notes: list[str] = []
    if not context.hourly_ledger.contract_met:
        notes.append(
            "The hourly contract is still open; force a shift in trust, desire, "
            "evidence, debt, power, or loyalty."
        )
    if context.story_governance.robotic_voice_risk:
        notes.append("Voice risk is rising; use concrete objects, money, shame, and interruptions.")
    if len(set(winners)) == 1 and winners:
        notes.append(
            f"All tested horizons prefer {winners[0]}; watch for sameness before locking it in."
        )
    if context.story_governance.recap_weakness:
        notes.append(
            "Recap material is weakening; bias toward clearer emotional change and one clean clue."
        )
    return notes[:4]
