from __future__ import annotations

import logging

from lantern_house.config import RuntimeConfig
from lantern_house.domain.contracts import (
    CharacterGoal,
    ManagerContextPacket,
    ManagerDirectivePlan,
    ThoughtPulseAuthorization,
)
from lantern_house.llm.ollama import OllamaClient
from lantern_house.utils.resources import render_template

logger = logging.getLogger(__name__)


class StoryManagerService:
    def __init__(self, llm: OllamaClient, model_name: str, runtime_config: RuntimeConfig) -> None:
        self.llm = llm
        self.model_name = model_name
        self.runtime_config = runtime_config

    async def plan(self, context: ManagerContextPacket, roster: list[str]) -> ManagerDirectivePlan:
        prompt = render_template(
            "lantern_house.prompts",
            "manager.md",
            {"MANAGER_CONTEXT": context.model_dump()},
        )
        try:
            payload, _stats = await self.llm.generate_json(
                model=self.model_name,
                prompt=prompt,
                temperature=0.7,
                max_output_tokens=480,
            )
            plan = ManagerDirectivePlan.model_validate(payload)
        except Exception as exc:
            logger.warning("manager fallback due to model issue: %s", exc)
            plan = self._fallback(context, roster)
        return self._normalize(plan, roster)

    def _normalize(self, plan: ManagerDirectivePlan, roster: list[str]) -> ManagerDirectivePlan:
        active = [slug for slug in plan.active_character_slugs if slug in roster]
        if not active:
            active = roster[: self.runtime_config.active_character_max]
        if len(active) < self.runtime_config.active_character_min:
            for slug in roster:
                if slug in active:
                    continue
                active.append(slug)
                if len(active) >= self.runtime_config.active_character_min:
                    break
        active = active[: self.runtime_config.active_character_max]
        speaker_weights = {slug: float(plan.speaker_weights.get(slug, 1.0)) for slug in active}
        per_character = dict(plan.per_character)
        for slug in active:
            per_character.setdefault(
                slug,
                CharacterGoal(
                    goal="Make the next exchange matter without over-explaining.",
                    pressure_point="You are one push away from saying too much.",
                    taboo_topics=["Do not resolve the oldest mystery tonight."],
                ),
            )
        thought_pulse = plan.thought_pulse
        if thought_pulse.character_slug not in active:
            thought_pulse = ThoughtPulseAuthorization(allowed=False)
        return ManagerDirectivePlan(
            objective=plan.objective,
            desired_developments=plan.desired_developments[:2],
            reveal_budget=max(0, min(3, plan.reveal_budget)),
            emotional_temperature=max(1, min(10, plan.emotional_temperature)),
            active_character_slugs=active,
            speaker_weights=speaker_weights,
            per_character=per_character,
            thought_pulse=thought_pulse,
            pacing_actions=plan.pacing_actions[:4],
            continuity_watch=plan.continuity_watch[:4],
            unresolved_questions_to_push=plan.unresolved_questions_to_push[:3],
            recentering_hint=plan.recentering_hint,
        )

    def _fallback(self, context: ManagerContextPacket, roster: list[str]) -> ManagerDirectivePlan:
        active = roster[: self.runtime_config.active_character_max]
        if len(active) < self.runtime_config.active_character_min:
            active = roster[: self.runtime_config.active_character_min]
        governance = context.story_governance
        audience = context.audience_control
        objective = (
            "Disturb the fragile calm with one practical problem "
            "and one emotionally loaded question."
        )
        if audience.active and audience.requests:
            objective = (
                "Seed the leading audience-voted change in a believable way without "
                "forcing instant payoff."
            )
        if not governance.hourly_progression_met:
            objective = (
                "Force one irreversible shift this hour in trust, evidence, money pressure, "
                "or romantic risk."
            )
        elif governance.core_drift:
            objective = (
                "Recenter the house around survival pressure, ownership conflict, "
                "hidden records, and unstable attraction."
            )
        desired = [
            "Surface a clue linked to the debt or the sealed lantern wing.",
            "Sharpen an old romantic or loyalty fault line without resolving it.",
        ]
        if audience.active and audience.requests:
            desired[0] = f"Begin gradual integration of: {audience.requests[0]}"
        if context.payoff_threads:
            desired[0] = (
                f"Revive this dormant hook in a grounded way: {context.payoff_threads[0]}"
            )
        if context.pacing_health.mystery_stalled:
            desired[0] = (
                "Force a more specific question about the vanished owner, "
                "the missing records, or the hidden route through the house."
            )
        if context.pacing_health.romance_stalled:
            desired[1] = "Push interrupted intimacy, jealousy, or an almost-confession."
        if governance.cliffhanger_pressure_low:
            desired[1] = (
                "End the exchange on an interruption, dangerous question, "
                "or emotionally loaded threat."
            )
        if audience.active and audience.tone_dials.get("romance", 0) >= 7:
            desired[1] = "Push slow-burn attraction, jealousy, or private domestic longing."
        per_character = {
            slug: CharacterGoal(
                goal=(
                    "Push the scene one inch closer to truth using concrete, "
                    "socially risky language."
                ),
                pressure_point=(
                    "You want to speak and withhold at the same time while staying specific."
                ),
                taboo_topics=["Do not solve the central mystery outright."],
            )
            for slug in active
        }
        thought = ThoughtPulseAuthorization(
            allowed=context.pacing_health.score < 55,
            character_slug=active[0],
            reason="The scene needs one brief flash of inner pressure.",
        )
        return ManagerDirectivePlan(
            objective=objective,
            desired_developments=desired,
            reveal_budget=1,
            emotional_temperature=max(6, min(9, 10 - context.pacing_health.score // 15)),
            active_character_slugs=active,
            speaker_weights={slug: 1.0 for slug in active},
            per_character=per_character,
            thought_pulse=thought,
            pacing_actions=(
                context.pacing_health.recommendations
                + governance.recommendations
                + audience.directives[:2]
            )[:4],
            continuity_watch=context.continuity_warnings[:4],
            unresolved_questions_to_push=context.unresolved_questions[:2],
            recentering_hint=(
                "If energy dips, let a practical house problem, dormant payoff thread, or "
                "document pressure expose an emotional fault line and end on a sharper question."
            ),
        )
