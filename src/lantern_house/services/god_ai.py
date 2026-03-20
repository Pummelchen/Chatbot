from __future__ import annotations

import logging
from datetime import timedelta

from lantern_house.config import GodAIConfig
from lantern_house.context.assembler import ContextAssembler
from lantern_house.domain.contracts import (
    AudienceControlReport,
    ManagerContextPacket,
    StrategicBriefPlan,
    StrategicBriefSnapshot,
)
from lantern_house.llm.ollama import OllamaClient
from lantern_house.services.audience import AudienceControlService
from lantern_house.services.simulation_lab import SimulationLabService
from lantern_house.utils.resources import render_template
from lantern_house.utils.time import ensure_utc, utcnow

logger = logging.getLogger(__name__)


class GodAIService:
    def __init__(
        self,
        *,
        config: GodAIConfig,
        assembler: ContextAssembler,
        audience_control_service: AudienceControlService,
        simulation_lab: SimulationLabService,
        llm: OllamaClient,
        model_name: str,
    ) -> None:
        self.config = config
        self.assembler = assembler
        self.audience_control_service = audience_control_service
        self.simulation_lab = simulation_lab
        self.llm = llm
        self.model_name = model_name
        self.interval = timedelta(minutes=max(1, config.refresh_interval_minutes))

    async def refresh_if_due(
        self,
        *,
        now=None,
        force: bool = False,
    ) -> StrategicBriefSnapshot | None:
        now = ensure_utc(now or utcnow())
        if not self.config.enabled:
            return self.assembler.repository.get_latest_strategic_brief(now=now, active_only=False)

        audience_control = self.audience_control_service.current_report()
        context = self.assembler.build_manager_packet(
            audience_control=audience_control,
            include_strategic=False,
        )
        latest = self.assembler.repository.get_latest_strategic_brief(now=now, active_only=True)
        if (
            latest
            and not force
            and not self._needs_refresh(latest=latest, context=context, now=now)
        ):
            return latest

        simulation = self.simulation_lab.evaluate(
            context,
            horizon_hours=self.config.simulation_horizon_hours,
            turns_per_hour=self.config.simulation_turns_per_hour,
        )
        provisional = None
        fallback_plan = self._fallback(
            context=context,
            simulation=simulation,
            audience=audience_control,
        )
        if latest is None or (latest.expires_at and ensure_utc(latest.expires_at) <= now):
            provisional = self.assembler.repository.record_strategic_brief(
                plan=fallback_plan,
                source="god-ai",
                model_name=None,
                simulation_report=simulation,
                now=now,
            )
        try:
            payload, _stats = await self.llm.generate_json(
                model=self.model_name,
                prompt=render_template(
                    "lantern_house.prompts",
                    "god_ai.md",
                    {
                        "GOD_AI_CONTEXT": {
                            "manager_context": context.model_dump(mode="json"),
                            "simulation_report": simulation.model_dump(mode="json"),
                        }
                    },
                ),
                temperature=0.45,
                max_output_tokens=700,
                max_retries=1,
            )
            plan = StrategicBriefPlan.model_validate(payload)
            model_name = self.model_name
        except Exception as exc:
            logger.warning("god-ai fallback due to model issue: %s", exc)
            return provisional or self.assembler.repository.record_strategic_brief(
                plan=fallback_plan,
                source="god-ai",
                model_name=None,
                simulation_report=simulation,
                now=now,
            )

        return self.assembler.repository.record_strategic_brief(
            plan=plan,
            source="god-ai",
            model_name=model_name,
            simulation_report=simulation,
            now=now,
        )

    def _needs_refresh(
        self,
        *,
        latest: StrategicBriefSnapshot,
        context: ManagerContextPacket,
        now,
    ) -> bool:
        created_at = ensure_utc(latest.created_at) if latest.created_at else None
        if created_at is None or now - created_at >= self.interval:
            return True
        if latest.expires_at and ensure_utc(latest.expires_at) <= now:
            return True
        if context.story_governance.viewer_value_score < 68:
            return True
        if context.pacing_health.score < 62:
            return True
        if (
            context.audience_control.active
            and context.audience_control.rollout_stage == "payoff-ready"
        ):
            return True
        return False

    def _fallback(
        self,
        *,
        context: ManagerContextPacket,
        simulation,
        audience: AudienceControlReport,
    ) -> StrategicBriefPlan:
        winner = simulation.candidates[0]
        audience_line = (
            f"Subscriber steering is active around {audience.requests[0]}"
            if audience.active and audience.requests
            else "No active subscriber vote is overriding the house's native momentum."
        )
        return StrategicBriefPlan(
            title=f"Strategic brief: {winner.strategy_key}",
            viewer_value_thesis=(
                "Maximize retention by keeping the house believable, pressurized, shippable, "
                "and easy to re-enter through one concrete progression per hour. "
                f"{audience_line}"
            ),
            urgency=max(5, min(10, 11 - context.story_governance.viewer_value_score // 10)),
            next_hour_focus=[winner.next_hour_focus, *simulation.recommended_focus[:1]],
            next_six_hours=[winner.six_hour_path, *simulation.recommended_focus[1:2]],
            recommendations=[
                *context.story_governance.recommendations[:2],
                *context.pacing_health.recommendations[:2],
                *winner.rationale[:2],
            ][:5],
            risk_alerts=simulation.systemic_risks[:4],
            house_pressure_actions=[
                signal.recommended_move
                for signal in context.house_state.active_pressures[:2]
                if signal.recommended_move
            ],
            audience_rollout_actions=[
                beat for beat in context.pending_beats if "audience" in beat.lower()
            ][:3],
            manager_biases={
                "preferred_arcs": [
                    summary.split("(", 1)[0].strip()
                    for summary in context.current_arc_summaries[:2]
                ],
                "preferred_characters": [
                    guidance.split("/", 1)[0].strip() for guidance in context.cast_guidance[:3]
                ],
                "avoid": [
                    "philosophical filler",
                    "instant payoff",
                    "generic confrontation lines",
                ],
            },
            expires_in_minutes=min(
                self.config.max_brief_age_minutes, max(30, self.config.refresh_interval_minutes * 3)
            ),
        )
