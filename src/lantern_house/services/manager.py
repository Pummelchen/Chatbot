# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import RuntimeConfig
from lantern_house.domain.contracts import (
    CharacterGoal,
    InferencePolicySnapshot,
    ManagerContextPacket,
    ManagerDirectivePlan,
    ThoughtPulseAuthorization,
)
from lantern_house.llm.ollama import OllamaClient
from lantern_house.runtime.failsafe import log_call_failure
from lantern_house.utils.resources import render_template


class StoryManagerService:
    def __init__(self, llm: OllamaClient, model_name: str, runtime_config: RuntimeConfig) -> None:
        self.llm = llm
        self.model_name = model_name
        self.runtime_config = runtime_config

    async def plan(
        self,
        context: ManagerContextPacket,
        roster: list[str],
        policy: InferencePolicySnapshot | None = None,
    ) -> ManagerDirectivePlan:
        prompt = render_template(
            "lantern_house.prompts",
            "manager.md",
            {"MANAGER_CONTEXT": context.model_dump(mode="json")},
        )
        if policy is not None and not policy.allow_model_call:
            return self._normalize(self._fallback(context, roster), roster)
        try:
            payload, _stats = await self.llm.generate_json(
                model=self.model_name,
                prompt=prompt,
                temperature=0.7,
                max_output_tokens=480,
                max_retries=policy.max_retries if policy is not None else 2,
                timeout_seconds=policy.timeout_seconds if policy is not None else None,
            )
            plan = ManagerDirectivePlan.model_validate(payload)
        except Exception as exc:
            log_call_failure(
                "manager.plan",
                exc,
                context={
                    "model": self.model_name,
                    "scene_objective": context.scene_objective,
                    "scene_location": context.scene_location,
                    "roster": roster,
                },
                expected_inputs=[
                    "A valid manager context packet.",
                    "A JSON manager plan matching ManagerDirectivePlan.",
                ],
                retry_advice=(
                    "Retry with a valid JSON planning response or allow the manager fallback "
                    "to steer the next live turn."
                ),
                fallback_used="deterministic-manager-fallback",
            )
            plan = self._fallback(context, roster)
        return self._normalize(plan, roster)

    def fallback_plan(
        self,
        context: ManagerContextPacket,
        roster: list[str],
    ) -> ManagerDirectivePlan:
        return self._normalize(self._fallback(context, roster), roster)

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
        pending_beats = context.pending_beats
        strategic = context.strategic_guidance
        strategic_brief = context.strategic_brief
        programming_grid = context.programming_grid_digest
        season_plan = context.season_plan_digest
        viewer_signals = context.viewer_signal_digest
        youtube_signals = context.youtube_adapter_digest
        contradiction_watch = context.contradiction_watch_digest
        guest_pressure = context.guest_pressure_digest
        daily_life = context.daily_life_digest
        payoff_debt = context.payoff_debt_digest
        shadow_replay = context.shadow_replay_digest
        objective = (
            "Disturb the fragile calm with one practical problem "
            "and one emotionally loaded question."
        )
        audience_objective = None
        audience_move = None
        if strategic_brief and strategic_brief.current_north_star_objective:
            objective = strategic_brief.current_north_star_objective
        if audience.active and audience.requests:
            audience_objective = (
                "Seed the leading audience-voted change in a believable way without "
                "forcing instant payoff."
            )
        hourly_objective = None
        if not context.hourly_ledger.contract_met:
            hourly_objective = (
                "Before this clock hour closes, land one concrete shift in trust, desire, "
                "evidence, debt pressure, power, or loyalty."
            )
        if programming_grid and any("[at-risk]" in item.lower() for item in programming_grid):
            objective = (
                "Protect the day plan by landing one overdue tentpole without losing realism."
            )
        if season_plan and any("[at-risk]" in item.lower() for item in season_plan):
            objective = (
                "Protect the longer season arc by seeding a durable reveal, ship, or inheritance "
                "move without forcing instant payoff."
            )
        if not governance.hourly_progression_met:
            hourly_objective = (
                "Force one irreversible shift this hour in trust, evidence, money pressure, "
                "or romantic risk."
            )
        elif governance.core_drift:
            objective = (
                "Recenter the house around survival pressure, ownership conflict, "
                "hidden records, and unstable attraction."
            )
        if audience_objective and hourly_objective:
            objective = (
                f"{audience_objective} Also, "
                f"{hourly_objective[0].lower()}{hourly_objective[1:]}"
            )
        elif hourly_objective:
            objective = hourly_objective
        elif audience_objective:
            objective = audience_objective
        desired = [
            "Surface a clue linked to the debt or the sealed lantern wing.",
            "Sharpen an old romantic or loyalty fault line without resolving it.",
        ]
        if pending_beats:
            desired[0] = f"Land this prepared beat in a grounded way: {pending_beats[0]}"
        if programming_grid:
            desired[0] = f"Serve this daily or weekly tentpole: {programming_grid[0]}"
        if context.hourly_ledger.recommended_push:
            desired[0] = context.hourly_ledger.recommended_push[0]
        if audience.active and audience.requests:
            audience_move = f"Begin gradual integration of: {audience.requests[0]}"
            desired[0] = audience_move
        if context.payoff_threads:
            desired[0] = f"Revive this dormant hook in a grounded way: {context.payoff_threads[0]}"
        if payoff_debt:
            desired[0] = f"Pay down this story debt with a believable move: {payoff_debt[0]}"
        if context.house_state.active_pressures:
            signal = context.house_state.active_pressures[0]
            objective = (
                "Use a house-pressure problem to expose loyalty, money fear, or attraction "
                "without solving the deeper issue."
            )
            desired[0] = signal.recommended_move or signal.summary or desired[0]
        if contradiction_watch:
            desired[0] = (
                "Exploit a contested alibi, room claim, or object trail without treating it as "
                f"settled fact: {contradiction_watch[0]}"
            )
        if viewer_signals:
            desired[1] = (
                "Translate current viewer energy into believable side-taking, theory, or ship "
                "fuel without acknowledging the audience."
            )
        if guest_pressure:
            desired[1] = (
                "Let an outsider, witness, or guest complication pressure the main cast "
                f"without stealing the core story: {guest_pressure[0]}"
            )
        if daily_life:
            desired[1] = (
                "Ground the next exchange in a real task or schedule collision: "
                f"{daily_life[0]}"
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
        if strategic_brief and strategic_brief.dormant_threads_to_revive:
            desired[0] = (
                "Revive this dormant thread with a grounded trigger: "
                f"{strategic_brief.dormant_threads_to_revive[0]}"
            )
        if strategic_brief and strategic_brief.clip_generation_potential >= 8:
            desired[1] = (
                "Land a quotable line or interruption that can carry a clip without "
                "breaking realism."
            )
        if context.highlight_signals:
            desired[1] = (
                "Restore clip value with a sharper interruption, confession, or leverage line."
            )
        if context.monetization_signals:
            desired[1] = (
                "Give the next exchange one cleaner quote, side-taking fault line, or "
                "debate-friendly turn."
            )
        if context.broadcast_asset_signals:
            desired[1] = (
                "Make the next turn legible enough to clip, title, and debate without sounding "
                "like manufactured content."
            )
        if youtube_signals:
            desired[1] = (
                "Convert real audience-side energy into theory fuel or ship friction without "
                "acknowledging the platform."
            )
        if context.voice_fingerprint_digest:
            desired[1] = (
                "Keep every line locked to the speaker's established cadence and conflict style."
            )
        if context.soak_audit_signals:
            desired[0] = f"Follow the latest soak warning: {context.soak_audit_signals[0]}"
        if shadow_replay and any("regression" in item.lower() for item in shadow_replay):
            desired[1] = "Keep the next turn short, concrete, and safely inside established canon."
        if context.canon_court_alerts:
            desired[0] = (
                "Keep suspicion alive without speaking as if the central truth is already proven."
            )
        if strategic_brief and strategic_brief.reveals_forbidden_for_now:
            forbidden = strategic_brief.reveals_forbidden_for_now[:2]
        else:
            forbidden = ["Do not solve the central mystery outright."]
        if audience.active and audience.tone_dials.get("romance", 0) >= 7:
            desired[1] = "Push slow-burn attraction, jealousy, or private domestic longing."
        if audience_move and not any(audience_move.lower() == item.lower() for item in desired):
            desired[1] = audience_move
        per_character = {
            slug: CharacterGoal(
                goal=(
                    "Push the scene one inch closer to truth using concrete, "
                    "socially risky language."
                ),
                pressure_point=(
                    "You want to speak and withhold at the same time while staying specific."
                ),
                taboo_topics=forbidden,
            )
            for slug in active
        }
        thought = ThoughtPulseAuthorization(
            allowed=context.pacing_health.score < 55
            or (
                strategic_brief is not None
                and strategic_brief.clip_generation_potential >= 8
                and strategic_brief.cliffhanger_urgency >= 8
            ),
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
                + context.recap_quality_alerts[:1]
                + context.public_turn_review_signals[:1]
                + context.highlight_signals[:1]
                + context.monetization_signals[:1]
                + context.broadcast_asset_signals[:1]
                + context.viewer_signal_digest[:1]
                + context.season_plan_digest[:1]
                + context.soak_audit_signals[:1]
                + context.ops_alerts[:1]
                + strategic[:2]
                + audience.directives[:2]
            )[:4],
            continuity_watch=context.continuity_warnings[:4],
            unresolved_questions_to_push=context.unresolved_questions[:2],
            recentering_hint=(
                "If energy dips, use story gravity: push the house, hidden records, inheritance "
                "conflict, or unstable attraction back into the room and end on a sharper hook."
            ),
        )
