# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lantern_house.config import TurnSelectionConfig
from lantern_house.domain.contracts import CharacterTurn, ManagerContextPacket, TurnCriticReport


@dataclass(slots=True)
class EvaluatedTurnCandidate:
    turn: CharacterTurn
    critic_report: TurnCriticReport
    events: list[Any]
    flags: list[Any]
    stats: Any | None
    degraded_mode: bool
    candidate_index: int


class TurnSelectionService:
    def __init__(self, config: TurnSelectionConfig) -> None:
        self.config = config

    def should_use_multi_candidate(
        self,
        *,
        manager_packet: ManagerContextPacket,
        load_tier: str,
        thought_pulse_allowed: bool,
    ) -> bool:
        if not self.config.enabled or self.config.candidate_count < 2:
            return False
        if load_tier in {"high", "critical"} and not self.config.enable_under_high_load:
            return False
        importance = self._importance_score(
            manager_packet=manager_packet,
            thought_pulse_allowed=thought_pulse_allowed,
        )
        return importance >= self.config.minimum_importance_score

    def choose_best(
        self,
        *,
        manager_packet: ManagerContextPacket,
        candidates: list[EvaluatedTurnCandidate],
    ) -> EvaluatedTurnCandidate:
        if not candidates:
            raise ValueError(
                "choose_best expected at least one evaluated candidate turn to rank."
            )
        ranked = sorted(
            candidates,
            key=lambda candidate: self._candidate_score(
                manager_packet=manager_packet,
                candidate=candidate,
            ),
            reverse=True,
        )
        return ranked[0]

    def _importance_score(
        self,
        *,
        manager_packet: ManagerContextPacket,
        thought_pulse_allowed: bool,
    ) -> int:
        score = 0
        if not manager_packet.hourly_ledger.contract_met:
            score += 3
        if manager_packet.story_governance.viewer_value_score <= 55:
            score += 2
        if manager_packet.story_governance.cliffhanger_pressure_low:
            score += 2
        if manager_packet.story_governance.recap_weakness:
            score += 1
        if manager_packet.highlight_signals or manager_packet.viewer_signal_digest:
            score += 1
        if manager_packet.broadcast_asset_signals:
            score += 1
        if manager_packet.monetization_signals:
            score += 1
        if thought_pulse_allowed:
            score += 1
        if manager_packet.season_plan_digest and any(
            "at-risk" in item.lower() for item in manager_packet.season_plan_digest
        ):
            score += 2
        return min(10, score)

    def _candidate_score(
        self,
        *,
        manager_packet: ManagerContextPacket,
        candidate: EvaluatedTurnCandidate,
    ) -> float:
        report = candidate.critic_report
        score = float(report.score)
        score += report.clip_value * 2.2
        score += report.quote_worthiness * 1.8
        score += report.fandom_discussion_value * 2.0
        score += report.novelty * 1.4
        if any(event.event_type.value == "romance" for event in candidate.events):
            score += (
                manager_packet.strategic_brief.romance_urgency
                if manager_packet.strategic_brief
                else 1
            )
        if any(
            event.event_type.value in {"clue", "question", "reveal"} for event in candidate.events
        ):
            score += (
                manager_packet.strategic_brief.mystery_urgency
                if manager_packet.strategic_brief
                else 1
            )
        if any(
            event.event_type.value in {"financial", "conflict", "threat"}
            for event in candidate.events
        ):
            score += (
                manager_packet.strategic_brief.house_pressure_priority
                if manager_packet.strategic_brief
                else 1
            )
        if candidate.turn.new_questions and manager_packet.hourly_ledger.evidence_shift_count == 0:
            score += 4
        if any(delta.desire_delta > 0 for delta in candidate.turn.relationship_updates) and (
            manager_packet.hourly_ledger.desire_shift_count == 0
        ):
            score += 4
        if any(
            delta.trust_delta != 0 or delta.obligation_delta != 0
            for delta in candidate.turn.relationship_updates
        ) and (
            manager_packet.hourly_ledger.trust_shift_count
            + manager_packet.hourly_ledger.loyalty_shift_count
            == 0
        ):
            score += 3
        if manager_packet.viewer_signal_digest:
            score += 1.5
        if manager_packet.broadcast_asset_signals:
            score += 1.0
        if candidate.degraded_mode:
            score -= 3.0
        score -= len(candidate.flags) * 2.0
        score -= candidate.candidate_index * 0.2
        return score
