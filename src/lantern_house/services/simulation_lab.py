# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import SimulationConfig
from lantern_house.domain.contracts import (
    ManagerContextPacket,
    SimulationCandidateScore,
    SimulationLabReport,
)
from lantern_house.utils.time import utcnow


class SimulationLabService:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config

    def evaluate(
        self,
        context: ManagerContextPacket,
        *,
        horizon_hours: int | None = None,
        turns_per_hour: int | None = None,
    ) -> SimulationLabReport:
        horizon = max(1, horizon_hours or self.config.default_horizon_hours)
        cadence = max(1, turns_per_hour or self.config.default_turns_per_hour)
        candidates = [
            self._score_house_pressure(context),
            self._score_mystery(context),
            self._score_romance(context),
            self._score_audience_rollout(context),
            self._score_ensemble_refresh(context),
        ]
        candidates.sort(key=lambda item: item.score, reverse=True)
        recommended_focus = [
            candidates[0].next_hour_focus,
            candidates[0].six_hour_path,
        ]
        if len(candidates) > 1:
            recommended_focus.append(candidates[1].next_hour_focus)
        return SimulationLabReport(
            generated_at=utcnow(),
            horizon_hours=horizon,
            turns_per_hour=cadence,
            candidates=candidates,
            systemic_risks=self._systemic_risks(context),
            recommended_focus=recommended_focus,
        )

    def _score_house_pressure(self, context: ManagerContextPacket) -> SimulationCandidateScore:
        score = 50
        rationale: list[str] = []
        state = context.house_state
        if state.cash_on_hand and state.hourly_burn_rate:
            reserve_hours = state.cash_on_hand // max(1, state.hourly_burn_rate)
            if reserve_hours < 72:
                score += 18
                rationale.append("Cash reserve is tight enough to justify practical urgency.")
        if state.repair_backlog >= 6:
            score += 14
            rationale.append("Repair backlog can generate grounded, visible tension quickly.")
        if state.inspection_risk >= 6 or state.reputation_risk >= 6:
            score += 10
            rationale.append("Inspection or reputation pressure can create public stakes.")
        if context.story_governance.core_drift:
            score += 8
            rationale.append("House pressure is the safest way to recenter the core promise.")
        next_focus = (
            context.pending_beats[0]
            if context.pending_beats
            else "Trigger one guesthouse problem that costs money, status, or cover."
        )
        return SimulationCandidateScore(
            strategy_key="house-pressure-first",
            score=min(100, score),
            rationale=rationale
            or ["The house can always generate concrete tension without lore dumping."],
            next_hour_focus=next_focus,
            six_hour_path=(
                "Escalate from visible breakdown to blame, then force a loyalty "
                "or romance choice under cost."
            ),
        )

    def _score_mystery(self, context: ManagerContextPacket) -> SimulationCandidateScore:
        score = 48
        rationale: list[str] = []
        if context.pacing_health.mystery_stalled:
            score += 20
            rationale.append("Mystery is stalled and needs a fresh inconsistency or clue.")
        if context.unresolved_questions:
            score += min(12, len(context.unresolved_questions) * 3)
            rationale.append("Open questions are available for re-entry and comment debate.")
        if context.story_governance.cliffhanger_pressure_low:
            score += 9
            rationale.append("Evidence and sharper questions restore cliffhanger pressure cleanly.")
        next_focus = (
            context.unresolved_questions[0]
            if context.unresolved_questions
            else "Introduce a clue that complicates an existing suspect map."
        )
        return SimulationCandidateScore(
            strategy_key="mystery-evidence-first",
            score=min(100, score),
            rationale=rationale or ["Mystery remains one of the house's permanent engines."],
            next_hour_focus=next_focus,
            six_hour_path=(
                "Use one clue, one contradiction, and one interrupted "
                "admission to deepen rather than solve."
            ),
        )

    def _score_romance(self, context: ManagerContextPacket) -> SimulationCandidateScore:
        score = 46
        rationale: list[str] = []
        if context.pacing_health.romance_stalled:
            score += 18
            rationale.append("Romance energy is down and needs unstable intimacy or jealousy.")
        if context.audience_control.tone_dials.get("romance", 0) >= 7:
            score += 14
            rationale.append("Subscriber steering is actively asking for more romance weight.")
        if any(
            "desire" in item.lower() or "romance" in item.lower()
            for item in context.current_arc_summaries
        ):
            score += 10
            rationale.append("The current arc mix already supports emotional acceleration.")
        next_focus = (
            "Force a useful task or public interruption to expose attraction "
            "without giving full payoff."
        )
        return SimulationCandidateScore(
            strategy_key="romance-faultline-first",
            score=min(100, score),
            rationale=rationale or ["Slow-burn romance remains a top retention mechanic."],
            next_hour_focus=next_focus,
            six_hour_path=(
                "Move from subtext to near-confession, then let guilt, duty, "
                "or jealousy raise the price."
            ),
        )

    def _score_audience_rollout(self, context: ManagerContextPacket) -> SimulationCandidateScore:
        score = 44
        rationale: list[str] = []
        if context.audience_control.active:
            score += 16
            rationale.append(
                "Active subscriber steering should produce visible but believable adaptation."
            )
        if any(
            "audience" in item.lower() or "phase" in item.lower() for item in context.pending_beats
        ):
            score += 12
            rationale.append("There are already staged rollout beats ready to use.")
        if context.audience_control.requests:
            score += 10
            rationale.append("Votes already define a discussion-friendly destination.")
        next_focus = (
            context.pending_beats[0]
            if context.pending_beats
            else "Seed the first prerequisite for the leading subscriber-voted shift."
        )
        return SimulationCandidateScore(
            strategy_key="audience-rollout-first",
            score=min(100, score),
            rationale=rationale
            or ["Audience steering is present but should not override core canon."],
            next_hour_focus=next_focus,
            six_hour_path=(
                "Use staged prerequisites so the vote feels absorbed into canon "
                "rather than bolted on."
            ),
        )

    def _score_ensemble_refresh(self, context: ManagerContextPacket) -> SimulationCandidateScore:
        score = 42
        rationale: list[str] = []
        if context.pacing_health.repetitive:
            score += 18
            rationale.append("Repetition risk is rising and needs new pairings or tonal contrast.")
        if context.pacing_health.too_agreeable:
            score += 12
            rationale.append("The room needs sharper disagreements and more active camps.")
        if context.story_governance.robotic_voice_risk:
            score += 8
            rationale.append("A broader ensemble rotation can restore voice contrast.")
        next_focus = (
            "Bring in a quieter character with a concrete agenda and let them "
            "disrupt the current rhythm."
        )
        return SimulationCandidateScore(
            strategy_key="ensemble-refresh-first",
            score=min(100, score),
            rationale=rationale or ["A fresh pairing can reset tone without breaking canon."],
            next_hour_focus=next_focus,
            six_hour_path=(
                "Rotate pairings, spread suspicion, and refresh humor without "
                "losing the house center."
            ),
        )

    def _systemic_risks(self, context: ManagerContextPacket) -> list[str]:
        risks: list[str] = []
        if not context.story_governance.hourly_progression_met:
            risks.append(
                "The last hour under-delivered on progression and needs an irreversible shift."
            )
        if context.story_governance.core_drift:
            risks.append(
                "The drama is drifting away from house survival, ownership, "
                "or hidden-record pressure."
            )
        if context.story_governance.robotic_voice_risk:
            risks.append("Dialogue quality is flattening toward generic AI-sounding conflict.")
        if context.pacing_health.too_agreeable:
            risks.append("Active characters are agreeing too easily and lowering comment tension.")
        if context.house_state.staff_fatigue >= 7:
            risks.append(
                "Staff fatigue is high enough to justify mistakes, slips, and brittle reactions."
            )
        return risks[:4]
