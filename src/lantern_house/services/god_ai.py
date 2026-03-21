# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

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
from lantern_house.runtime.failsafe import log_call_failure
from lantern_house.services.audience import AudienceControlService
from lantern_house.services.simulation_lab import SimulationLabService
from lantern_house.utils.resources import render_template
from lantern_house.utils.time import ensure_utc, utcnow


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
        record_simulation = getattr(self.assembler.repository, "record_simulation_lab_run", None)
        if callable(record_simulation):
            simulation = record_simulation(
                report=simulation,
                source="god-ai",
                now=now,
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
                max_output_tokens=900,
                max_retries=1,
            )
            plan = StrategicBriefPlan.model_validate(
                self._coerce_plan_payload(
                    payload=payload,
                    context=context,
                    simulation=simulation,
                    audience=audience_control,
                )
            )
            model_name = self.model_name
        except Exception as exc:
            log_call_failure(
                "god_ai.refresh_if_due",
                exc,
                context={
                    "model": self.model_name,
                    "scene_objective": context.scene_objective,
                    "audience_active": audience_control.active,
                },
                expected_inputs=[
                    "A valid manager context packet and simulation report.",
                    "A JSON strategic brief matching StrategicBriefPlan.",
                ],
                retry_advice=(
                    "Retry with a valid strategic brief or continue on the provisional "
                    "deterministic brief until the model recovers."
                ),
                fallback_used="deterministic-strategic-brief",
            )
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
        if context.story_gravity_state.drift_score >= 55:
            return True
        if context.story_governance.recap_weakness:
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
        arc_ranking = [
            summary.split("(", 1)[0].strip() for summary in context.current_arc_summaries[:3]
        ]
        dormant_threads = [
            thread.split(":", 1)[-1].strip() if ":" in thread else thread
            for thread in context.dormant_threads[:3]
        ]
        return StrategicBriefPlan(
            title=f"Strategic brief: {winner.strategy_key}",
            current_north_star_objective=(
                context.story_gravity_state.north_star_objective
                or context.scene_objective
                or "Keep the house anchored to debt, hidden records, and unstable attraction."
            ),
            viewer_value_thesis=(
                "Maximize retention by keeping the house believable, pressurized, shippable, "
                "and easy to re-enter through one concrete progression per hour. "
                f"{audience_line}"
            ),
            urgency=max(5, min(10, 11 - context.story_governance.viewer_value_score // 10)),
            arc_priority_ranking=arc_ranking,
            danger_of_drift_score=max(
                0,
                min(
                    100,
                    context.story_gravity_state.drift_score
                    or (100 - context.story_governance.viewer_value_score),
                ),
            ),
            cliffhanger_urgency=max(
                4,
                min(10, 7 + int(context.story_governance.cliffhanger_pressure_low)),
            ),
            romance_urgency=max(
                4,
                min(
                    10,
                    6
                    + int(context.pacing_health.romance_stalled)
                    + int(context.audience_control.tone_dials.get("romance", 0) >= 7),
                ),
            ),
            mystery_urgency=max(
                4,
                min(10, 6 + int(context.pacing_health.mystery_stalled)),
            ),
            house_pressure_priority=max(
                4,
                min(10, 5 + len(context.house_state.active_pressures)),
            ),
            audience_rollout_priority=max(
                3,
                min(10, 4 + int(context.audience_control.active) * 3),
            ),
            dormant_threads_to_revive=dormant_threads,
            reveals_allowed_soon=[
                item for item in context.unresolved_questions[:2] if item
            ],
            reveals_forbidden_for_now=[
                "Do not solve Evelyn Vale's disappearance outright.",
                "Do not fully validate or destroy the top ship in one jump.",
            ],
            next_one_hour_intention=winner.next_hour_focus,
            next_six_hour_intention=winner.six_hour_path,
            next_twenty_four_hour_intention=(
                "Create a day with one practical setback, one emotional reversal, "
                "and one clue viewers can debate across time zones."
            ),
            next_hour_focus=[winner.next_hour_focus, *simulation.recommended_focus[:1]],
            next_six_hours=[winner.six_hour_path, *simulation.recommended_focus[1:2]],
            recap_priorities=[
                "Make the recap name the biggest emotional shift clearly.",
                "Give re-entry viewers one clue and one open question worth following.",
            ],
            fan_theory_potential=min(
                10,
                max(4, winner.value_profile.get("theory_value", 5)),
            ),
            clip_generation_potential=min(
                10,
                max(4, winner.value_profile.get("clip_worthiness", 5)),
            ),
            reentry_clarity_priority=max(
                4,
                min(10, context.story_gravity_state.reentry_priority),
            ),
            quote_worthiness=min(
                10,
                max(4, winner.value_profile.get("quote_worthiness", 5)),
            ),
            betrayal_value=min(
                10,
                max(4, winner.value_profile.get("betrayal_value", 5)),
            ),
            daily_uniqueness=min(
                10,
                max(4, winner.value_profile.get("daily_uniqueness", 5)),
            ),
            fandom_discussion_value=min(
                10,
                max(4, winner.value_profile.get("fandom_discussion_value", 5)),
            ),
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

    def _coerce_plan_payload(
        self,
        *,
        payload: dict,
        context: ManagerContextPacket,
        simulation,
        audience: AudienceControlReport,
    ) -> dict:
        fallback = self._fallback(
            context=context,
            simulation=simulation,
            audience=audience,
        ).model_dump()
        merged = dict(fallback)
        if isinstance(payload, dict):
            merged.update(payload)
        if not merged.get("current_north_star_objective"):
            merged["current_north_star_objective"] = fallback["current_north_star_objective"]
        merged.setdefault("arc_priority_ranking", fallback["arc_priority_ranking"])
        merged.setdefault("danger_of_drift_score", fallback["danger_of_drift_score"])
        merged.setdefault("cliffhanger_urgency", fallback["cliffhanger_urgency"])
        merged.setdefault("romance_urgency", fallback["romance_urgency"])
        merged.setdefault("mystery_urgency", fallback["mystery_urgency"])
        merged.setdefault("house_pressure_priority", fallback["house_pressure_priority"])
        merged.setdefault("audience_rollout_priority", fallback["audience_rollout_priority"])
        merged.setdefault(
            "dormant_threads_to_revive",
            fallback["dormant_threads_to_revive"],
        )
        merged.setdefault("reveals_allowed_soon", fallback["reveals_allowed_soon"])
        merged.setdefault(
            "reveals_forbidden_for_now",
            fallback["reveals_forbidden_for_now"],
        )
        merged.setdefault("next_one_hour_intention", fallback["next_one_hour_intention"])
        merged.setdefault("next_six_hour_intention", fallback["next_six_hour_intention"])
        merged.setdefault(
            "next_twenty_four_hour_intention",
            fallback["next_twenty_four_hour_intention"],
        )
        merged.setdefault("recap_priorities", fallback["recap_priorities"])
        merged.setdefault("fan_theory_potential", fallback["fan_theory_potential"])
        merged.setdefault("clip_generation_potential", fallback["clip_generation_potential"])
        merged.setdefault(
            "reentry_clarity_priority",
            fallback["reentry_clarity_priority"],
        )
        merged.setdefault("quote_worthiness", fallback["quote_worthiness"])
        merged.setdefault("betrayal_value", fallback["betrayal_value"])
        merged.setdefault("daily_uniqueness", fallback["daily_uniqueness"])
        merged.setdefault(
            "fandom_discussion_value",
            fallback["fandom_discussion_value"],
        )
        return merged
