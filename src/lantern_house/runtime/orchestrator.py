# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
from importlib import import_module
from pathlib import Path
from typing import Any

from lantern_house.config import AppConfig, build_hot_patch_config
from lantern_house.context.assembler import ContextAssembler
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import (
    AudienceControlReport,
    LoadProfileSnapshot,
    ManagerContextPacket,
    ManagerDirectivePlan,
    OpsTelemetrySnapshot,
    StoryProgressionPlan,
    TurnCriticReport,
)
from lantern_house.quality.pacing import ContinuityGuard
from lantern_house.rendering.terminal import TerminalRenderer
from lantern_house.runtime.failsafe import FailSafeExecutor, log_call_failure
from lantern_house.runtime.hotpatch import HotPatchController
from lantern_house.runtime.recovery import RecoveryService
from lantern_house.runtime.scheduler import TurnScheduler
from lantern_house.services.audience import AudienceControlService
from lantern_house.services.beats import StoryBeatService
from lantern_house.services.broadcast_assets import BroadcastAssetService
from lantern_house.services.canon import CanonDistillationService
from lantern_house.services.canon_court import CanonCourtService
from lantern_house.services.character import CharacterService
from lantern_house.services.chronology_graph import ChronologyGraphService
from lantern_house.services.critic import TurnCriticService
from lantern_house.services.event_extractor import EventExtractor
from lantern_house.services.god_ai import GodAIService
from lantern_house.services.guest_circulation import GuestCirculationService
from lantern_house.services.highlights import HighlightPackagingService
from lantern_house.services.hourly_ledger import HourlyBeatLedgerService
from lantern_house.services.house import HousePressureService
from lantern_house.services.load_orchestration import LoadOrchestrationService
from lantern_house.services.manager import StoryManagerService
from lantern_house.services.monetization import MonetizationPackagingService
from lantern_house.services.ops_dashboard import OpsDashboardService
from lantern_house.services.programming_grid import ProgrammingGridService
from lantern_house.services.progression import StoryProgressionService
from lantern_house.services.recaps import RecapService
from lantern_house.services.season_planner import SeasonPlannerService
from lantern_house.services.story_gravity import StoryGravityService
from lantern_house.services.turn_selection import EvaluatedTurnCandidate, TurnSelectionService
from lantern_house.services.viewer_signals import ViewerSignalIngestionService
from lantern_house.services.voice_fingerprints import VoiceFingerprintService
from lantern_house.services.world_tracking import WorldTrackingService
from lantern_house.utils.time import ensure_utc, utcnow

logger = logging.getLogger(__name__)


class RuntimeOrchestrator:
    def __init__(
        self,
        *,
        config: AppConfig,
        repository: StoryRepository,
        assembler: ContextAssembler,
        audience_control_service: AudienceControlService,
        viewer_signal_service: ViewerSignalIngestionService,
        beat_service: StoryBeatService,
        hourly_ledger_service: HourlyBeatLedgerService,
        programming_grid_service: ProgrammingGridService,
        season_planner_service: SeasonPlannerService,
        canon_service: CanonDistillationService,
        canon_court_service: CanonCourtService,
        chronology_graph_service: ChronologyGraphService,
        house_pressure_service: HousePressureService,
        world_tracking_service: WorldTrackingService,
        story_gravity_service: StoryGravityService,
        god_ai_service: GodAIService,
        manager_service: StoryManagerService,
        character_service: CharacterService,
        voice_fingerprint_service: VoiceFingerprintService,
        turn_selection_service: TurnSelectionService,
        critic_service: TurnCriticService,
        highlight_service: HighlightPackagingService,
        monetization_service: MonetizationPackagingService,
        broadcast_asset_service: BroadcastAssetService,
        guest_circulation_service: GuestCirculationService,
        recap_service: RecapService,
        progression_service: StoryProgressionService,
        load_orchestration_service: LoadOrchestrationService,
        ops_dashboard_service: OpsDashboardService,
        scheduler: TurnScheduler,
        recovery_service: RecoveryService,
        event_extractor: EventExtractor,
        continuity_guard: ContinuityGuard,
        renderer: TerminalRenderer,
        llm_client,
        fail_safe_executor: FailSafeExecutor,
        hot_patch_controller: HotPatchController | None = None,
        hot_patch_validator: Any | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.assembler = assembler
        self.audience_control_service = audience_control_service
        self.viewer_signal_service = viewer_signal_service
        self.beat_service = beat_service
        self.hourly_ledger_service = hourly_ledger_service
        self.programming_grid_service = programming_grid_service
        self.season_planner_service = season_planner_service
        self.canon_service = canon_service
        self.canon_court_service = canon_court_service
        self.chronology_graph_service = chronology_graph_service
        self.house_pressure_service = house_pressure_service
        self.world_tracking_service = world_tracking_service
        self.story_gravity_service = story_gravity_service
        self.god_ai_service = god_ai_service
        self.manager_service = manager_service
        self.character_service = character_service
        self.voice_fingerprint_service = voice_fingerprint_service
        self.turn_selection_service = turn_selection_service
        self.critic_service = critic_service
        self.highlight_service = highlight_service
        self.monetization_service = monetization_service
        self.broadcast_asset_service = broadcast_asset_service
        self.guest_circulation_service = guest_circulation_service
        self.recap_service = recap_service
        self.progression_service = progression_service
        self.load_orchestration_service = load_orchestration_service
        self.ops_dashboard_service = ops_dashboard_service
        self.scheduler = scheduler
        self.recovery_service = recovery_service
        self.event_extractor = event_extractor
        self.continuity_guard = continuity_guard
        self.renderer = renderer
        self.llm_client = llm_client
        self.fail_safe = fail_safe_executor
        self.hot_patch_controller = hot_patch_controller
        self.hot_patch_validator = hot_patch_validator
        self._stop_event = asyncio.Event()
        self._checkpoint_task: asyncio.Task[None] | None = None
        self._god_ai_task: asyncio.Task[None] | None = None
        self._pending_manager_task: asyncio.Task[ManagerDirectivePlan] | None = None
        self._prefetched_plan: ManagerDirectivePlan | None = None
        self._prefetched_at = None
        self._last_audience_sync_key: tuple[str | None, str] | None = None
        self._last_viewer_signals: list[Any] = []
        self._roster: list[str] = []
        self._color_map: dict[str, str] = {}
        self._last_good_audience_control = AudienceControlReport()
        self._last_good_manager_packet: ManagerContextPacket | None = None
        self._last_good_character_packet_by_slug: dict[str, Any] = {}
        self._last_good_run_state: dict[str, Any] | None = None
        self._last_load_profile = LoadProfileSnapshot()
        self._last_ops_snapshot: OpsTelemetrySnapshot | None = None

    def attach_hot_patch_controller(self, controller: HotPatchController) -> None:
        self.hot_patch_controller = controller

    async def run(self, *, once: bool = False) -> None:
        roster_result = self.fail_safe.call(
            "runtime.load_roster",
            lambda: [item["slug"] for item in self.repository.list_characters()],
            context={"phase": "startup"},
            expected_inputs=["A seeded character roster in MySQL."],
            retry_advice="Run `lantern-house seed` or repair the database seed state.",
            fallback=[],
            fallback_label="empty-roster",
        )
        self._roster = roster_result.value or []
        if not self._roster:
            raise RuntimeError("No story seed found. Run `lantern-house seed` first.")

        color_result = self.fail_safe.call(
            "runtime.load_color_map",
            self.repository.get_character_color_map,
            context={"phase": "startup"},
            expected_inputs=["A character color map persisted in MySQL."],
            retry_advice="Repair the seed data or let the renderer fall back to default colors.",
            fallback={},
            fallback_label="default-render-colors",
        )
        self._color_map = color_result.value or {}
        self.renderer.register_characters(self._color_map)
        self._install_signal_handlers()
        if self.hot_patch_controller is not None:
            self.hot_patch_controller.bootstrap()

        try:
            await self._initialize_runtime(once=once)
            while not self._stop_event.is_set():
                try:
                    should_stop = await self._run_iteration(once=once)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._note_runtime_failure(now=utcnow(), reason=str(exc))
                    log_call_failure(
                        "runtime.iteration",
                        exc,
                        context={
                            "once": once,
                            "last_tick_no": (self._last_good_run_state or {}).get("last_tick_no"),
                        },
                        expected_inputs=[
                            "A consistent repository state, valid runtime services, and a live "
                            "Ollama response or fallback path."
                        ],
                        retry_advice=(
                            "Fix the failing code or dependency issue. The runtime will pause "
                            "briefly and continue without exposing the failure publicly."
                        ),
                        fallback_used="live-loop-continue",
                    )
                    if once:
                        break
                    await asyncio.sleep(
                        max(1, self.config.failsafe.unexpected_iteration_delay_seconds)
                    )
                    continue
                if should_stop:
                    break
        finally:
            await self._cancel_background_task(self._pending_manager_task)
            await self._cancel_background_task(self._checkpoint_task)
            await self._cancel_background_task(self._god_ai_task)
            self.fail_safe.call(
                "runtime.write_shutdown_checkpoint",
                lambda: self.repository.write_checkpoint(reason="shutdown", phase="shutdown"),
                context={"phase": "shutdown"},
                expected_inputs=["A writable run_state row in MySQL."],
                retry_advice="Restore database connectivity so the runtime can checkpoint again.",
            )
            self.fail_safe.call(
                "runtime.set_idle_status",
                lambda: self.repository.set_runtime_status(
                    "idle",
                    degraded_mode=False,
                    phase="idle",
                ),
                context={"phase": "shutdown"},
                expected_inputs=["A writable run_state row in MySQL."],
                retry_advice="Restore database connectivity so the runtime can record idle state.",
            )

    async def _initialize_runtime(self, *, once: bool) -> None:
        recovery_result = self.fail_safe.call(
            "recovery.recover",
            self.recovery_service.recover,
            context={"phase": "startup"},
            expected_inputs=["A seeded run_state row and checkpoint metadata when available."],
            retry_advice="Repair run_state persistence and retry recovery.",
            fallback={
                "previous_run_state": {},
                "unclean_shutdown": False,
                "checkpoint": None,
                "missed_recap_hours": [],
            },
            fallback_label="empty-recovery-state",
        )
        recovery = recovery_result.value or {}
        if recovery.get("unclean_shutdown"):
            logger.warning("Recovered from unclean shutdown using persisted checkpoint state.")
        self.fail_safe.call(
            "runtime.write_startup_checkpoint",
            lambda: self.repository.write_checkpoint(reason="startup", phase="recovery"),
            context={"phase": "startup"},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so startup checkpoints can resume.",
        )
        for bucket in recovery.get("missed_recap_hours", []):
            await self._emit_recap(bucket)

        startup_now = utcnow()
        audience_control = self._refresh_audience_control(now=startup_now, force=True)
        self._refresh_viewer_signals(now=startup_now, force=True)
        self._last_audience_sync_key = self._sync_audience_rollout(
            audience_control=audience_control,
            last_key=self._last_audience_sync_key,
            now=startup_now,
        )
        self._refresh_hourly_ledger(now=startup_now)
        self._refresh_programming_grid(now=startup_now, force=True)
        self._refresh_season_planner(now=startup_now, force=True)
        self._refresh_house_pressure(now=startup_now, force=True)
        self._refresh_story_gravity(now=startup_now, force=True)
        self._refresh_canon(now=startup_now)
        self._refresh_voice_fingerprints(now=startup_now, force=True)
        self._refresh_world_tracking(now=startup_now, force=True)
        self._refresh_chronology_graph(now=startup_now, force=True)
        self._refresh_guest_circulation(now=startup_now, force=True)
        startup_load = self._capture_load_profile(now=startup_now)
        self._capture_ops_snapshot(load_profile=startup_load, now=startup_now)
        self.fail_safe.call(
            "runtime.set_loop_ready",
            lambda: self.repository.set_runtime_status(
                "running",
                degraded_mode=False,
                phase="loop-ready",
            ),
            context={"phase": "startup"},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so loop status can be tracked.",
        )
        self._checkpoint_task = asyncio.create_task(self._checkpoint_loop())
        if not once:
            self._god_ai_task = asyncio.create_task(self._god_ai_loop())

    async def _run_iteration(self, *, once: bool) -> bool:
        now = utcnow()
        self._refresh_hot_patch(now=now)

        if self.config.recaps.enabled:
            recap_hours_result = self.fail_safe.call(
                "runtime.list_missing_recap_hours",
                lambda: self.repository.list_missing_recap_hours(now=now),
                context={"phase": "recap-check"},
                expected_inputs=["A readable run_state row and recap summary history."],
                retry_advice="Restore recap persistence so missed buckets can be detected again.",
                fallback=[],
                fallback_label="skip-missed-recaps",
            )
            for bucket in recap_hours_result.value or []:
                await self._emit_recap(bucket)

        audience_control = self._refresh_audience_control(now=now)
        viewer_signals = self._refresh_viewer_signals(now=now)
        self._last_audience_sync_key = self._sync_audience_rollout(
            audience_control=audience_control,
            last_key=self._last_audience_sync_key,
            now=now,
        )
        self._refresh_hourly_ledger(now=now)
        self._refresh_programming_grid(now=now)
        self._refresh_season_planner(now=now)
        self._refresh_house_pressure(now=now)
        self._refresh_story_gravity(now=now)
        self._refresh_canon(now=now)
        self._refresh_voice_fingerprints(now=now)
        self._refresh_chronology_graph(now=now)
        self._refresh_guest_circulation(now=now)
        load_profile = self._capture_load_profile(now=now)
        ops_snapshot = self._capture_ops_snapshot(load_profile=load_profile, now=now)
        self._apply_ops_remediations(snapshot=ops_snapshot, now=now)

        directive_result = self.fail_safe.call(
            "manager.get_latest_directive",
            self.repository.get_latest_manager_directive,
            context={"phase": "directive-load"},
            expected_inputs=["A readable manager_directives table or a refresh path."],
            retry_advice="Restore manager directive persistence or allow the manager to replan.",
            fallback=None,
        )
        directive = directive_result.value

        if self._pending_manager_task is not None and self._pending_manager_task.done():
            try:
                self._prefetched_plan = self._pending_manager_task.result()
                self._prefetched_at = now
            except Exception as exc:
                log_call_failure(
                    "manager.prefetch_result",
                    exc,
                    context={"phase": "directive-prefetch"},
                    expected_inputs=["A valid prefetched manager directive plan."],
                    retry_advice="Let the next manager refresh rebuild a fresh directive.",
                    fallback_used="discard-prefetch",
                )
            self._pending_manager_task = None

        manager_packet = self._build_manager_packet(
            audience_control=audience_control,
            load_profile=load_profile,
            ops_snapshot=ops_snapshot,
        )
        if manager_packet is None:
            return await self._pause_after_failed_iteration(once=once)

        run_state = self._get_run_state()
        if run_state is None:
            return await self._pause_after_failed_iteration(once=once)

        needs_refresh = self.scheduler.should_refresh_manager(
            run_state=run_state,
            directive=directive,
            health=manager_packet.pacing_health,
            governance=manager_packet.story_governance,
        )
        if needs_refresh:
            if self._prefetched_plan_is_fresh(self._prefetched_plan, self._prefetched_at, now):
                directive_result = self.fail_safe.call(
                    "manager.record_prefetched_directive",
                    lambda: self.repository.record_manager_directive(
                        self._prefetched_plan,
                        tick_no=run_state["last_tick_no"] + 1,
                        now=now,
                    ),
                    context={"phase": "directive-refresh", "source": "prefetch"},
                    expected_inputs=["A valid prefetched manager plan and writable MySQL state."],
                    retry_advice="Allow the manager to replan and retry directive persistence.",
                    fallback=directive,
                    fallback_label="existing-directive",
                )
                directive = directive_result.value
                self._prefetched_plan = None
                self._prefetched_at = None
            else:
                urgent_refresh = (
                    directive is None
                    or manager_packet.pacing_health.score < 42
                    or manager_packet.story_governance.viewer_value_score < 45
                    or load_profile.load_tier == "critical"
                )
                if urgent_refresh or self._pending_manager_task is None:
                    self.fail_safe.call(
                        "runtime.set_manager_request_phase",
                        lambda: self.repository.set_runtime_status(
                            "running",
                            phase="manager-request",
                            extra_metadata={"manager_requested_at": now.isoformat()},
                            now=now,
                        ),
                        context={"phase": "directive-refresh"},
                        expected_inputs=["A writable run_state row in MySQL."],
                        retry_advice="Restore database connectivity so runtime phases can update.",
                    )
                    plan_result = await self.fail_safe.call_async(
                        "manager.plan_sync",
                        lambda: self.manager_service.plan(manager_packet, self._roster),
                        context={
                            "phase": "directive-refresh",
                            "scene_objective": manager_packet.scene_objective,
                        },
                        expected_inputs=[
                            "A valid manager context packet and a manager service with fallback."
                        ],
                        retry_advice="Allow the manager fallback to steer the next turn.",
                        fallback=lambda: self.manager_service.fallback_plan(
                            manager_packet,
                            self._roster,
                        ),
                        fallback_label="deterministic-manager-fallback",
                    )
                    directive_plan = plan_result.value
                    if load_profile.load_tier in {"high", "critical"} and not urgent_refresh:
                        directive_plan = self.manager_service.fallback_plan(
                            manager_packet,
                            self._roster,
                        )
                    if directive_plan is not None:
                        directive_result = self.fail_safe.call(
                            "manager.record_directive",
                            lambda: self.repository.record_manager_directive(
                                directive_plan,
                                tick_no=run_state["last_tick_no"] + 1,
                                now=now,
                            ),
                            context={"phase": "directive-refresh", "source": "sync"},
                            expected_inputs=["A valid manager plan and writable MySQL state."],
                            retry_advice=(
                                "Repair manager directive persistence or keep using the previous "
                                "directive until the next refresh."
                            ),
                            fallback=directive,
                            fallback_label="existing-directive",
                        )
                        directive = directive_result.value
                        self._prefetched_plan = None
                        self._prefetched_at = None

        if (
            self._pending_manager_task is None
            and self._prefetched_plan is None
            and directive is not None
            and load_profile.load_tier not in {"high", "critical"}
            and self.scheduler.should_prefetch_manager(
                run_state=run_state,
                directive=directive,
                health=manager_packet.pacing_health,
                governance=manager_packet.story_governance,
            )
        ):
            self.fail_safe.call(
                "runtime.set_manager_prefetch_phase",
                lambda: self.repository.set_runtime_status(
                    "running",
                    phase="manager-prefetch",
                    extra_metadata={"manager_prefetch_at": now.isoformat()},
                    now=now,
                ),
                context={"phase": "directive-prefetch"},
                expected_inputs=["A writable run_state row in MySQL."],
                retry_advice="Restore database connectivity so runtime phases can update.",
            )
            self._pending_manager_task = asyncio.create_task(
                self.manager_service.plan(manager_packet, self._roster)
            )

        if directive is None:
            log_call_failure(
                "manager.directive_missing",
                RuntimeError("Manager directive unavailable after refresh attempt"),
                context={"phase": "directive-refresh"},
                expected_inputs=["A persisted manager directive or a valid manager fallback plan."],
                retry_advice="Allow the next iteration to rebuild the directive path.",
                fallback_used="skip-turn",
            )
            return await self._pause_after_failed_iteration(once=once)

        states_result = self.fail_safe.call(
            "runtime.list_character_states",
            self.repository.list_character_states,
            context={"phase": "speaker-selection"},
            expected_inputs=["Readable character_state rows for the active roster."],
            retry_advice="Restore character_state persistence so speaker selection can recover.",
            fallback=self._fallback_character_states(),
            fallback_label="synthetic-character-states",
        )
        character_states = states_result.value or self._fallback_character_states()
        speaker_result = self.fail_safe.call(
            "runtime.select_speaker",
            lambda: self.scheduler.select_speaker(
                directive=directive,
                character_states=character_states,
            ),
            context={"phase": "speaker-selection", "directive_id": directive.get("id")},
            expected_inputs=[
                "A valid directive with active characters and readable character states."
            ],
            retry_advice="Allow the scheduler to retry on the next iteration.",
            fallback=(directive.get("active_character_slugs") or self._roster)[0],
            fallback_label="first-active-character",
        )
        speaker_slug = speaker_result.value or self._roster[0]
        packet = self._build_character_packet(speaker_slug=speaker_slug, directive=directive)
        if packet is None:
            return await self._pause_after_failed_iteration(once=once)

        pulse_count_result = self.fail_safe.call(
            "runtime.count_recent_thought_pulses",
            lambda: self.repository.count_recent_thought_pulses(hours=1),
            context={"phase": "thought-pulse"},
            expected_inputs=["Readable thought_pulses history in MySQL."],
            retry_advice="Restore thought pulse persistence so the cooldown can recover.",
            fallback=0,
            fallback_label="no-recent-thought-pulses",
        )
        thought_pulse_allowed = self.scheduler.allow_thought_pulse(
            directive=directive,
            speaker_slug=speaker_slug,
            run_state=run_state,
            recent_pulse_count=pulse_count_result.value or 0,
        )

        self.fail_safe.call(
            "runtime.set_character_request_phase",
            lambda: self.repository.set_runtime_status(
                "running",
                phase="character-request",
                extra_metadata={"candidate_speaker": speaker_slug},
                now=now,
            ),
            context={"phase": "character-request", "speaker_slug": speaker_slug},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so runtime phases can update.",
        )
        use_multi_candidate = self.turn_selection_service.should_use_multi_candidate(
            manager_packet=manager_packet,
            load_tier=load_profile.load_tier,
            thought_pulse_allowed=thought_pulse_allowed,
        )
        candidate_result = await self.fail_safe.call_async(
            "character.generate_candidates",
            lambda: self.character_service.generate_candidates(
                packet=packet,
                thought_pulse_allowed=thought_pulse_allowed,
                candidate_count=(
                    self.config.turn_selection.candidate_count if use_multi_candidate else 1
                ),
            ),
            context={"speaker_slug": speaker_slug, "phase": "character-request"},
            expected_inputs=[
                "A valid character context packet and a character service with fallback."
            ],
            retry_advice="Allow the character fallback to keep the scene alive.",
            fallback=lambda: [
                (
                    self.character_service.repair(
                        packet=packet,
                        thought_pulse_allowed=thought_pulse_allowed,
                    ),
                    None,
                    True,
                )
            ],
            fallback_label="deterministic-character-fallback",
        )
        generated_candidates = candidate_result.value or [
            (
                self.character_service.repair(
                    packet=packet,
                    thought_pulse_allowed=thought_pulse_allowed,
                ),
                None,
                True,
            )
        ]
        selected_candidate = generated_candidates[0]
        if use_multi_candidate and len(generated_candidates) > 1:
            preview_candidates = [
                self._preview_candidate(
                    packet=packet,
                    directive=directive,
                    turn=candidate_turn,
                    stats=candidate_stats,
                    degraded_mode=candidate_degraded,
                    candidate_index=index,
                    speaker_slug=speaker_slug,
                )
                for index, (candidate_turn, candidate_stats, candidate_degraded) in enumerate(
                    generated_candidates
                )
            ]
            selected = self.turn_selection_service.choose_best(
                manager_packet=manager_packet,
                candidates=preview_candidates,
            )
            selected_candidate = (selected.turn, selected.stats, selected.degraded_mode)
        turn_value = selected_candidate or (
            self.character_service.repair(
                packet=packet,
                thought_pulse_allowed=thought_pulse_allowed,
            ),
            None,
            True,
        )
        turn, stats, degraded_mode = turn_value

        events_result = self.fail_safe.call(
            "event_extractor.extract",
            lambda: self.event_extractor.extract(speaker_slug=speaker_slug, turn=turn),
            context={"speaker_slug": speaker_slug},
            expected_inputs=["A valid CharacterTurn with structured event candidates."],
            retry_advice="Retry with a valid turn or let progression continue without new events.",
            fallback=[],
            fallback_label="empty-event-list",
        )
        events = events_result.value or []
        flags_result = self.fail_safe.call(
            "continuity_guard.review_turn",
            lambda: self.continuity_guard.review_turn(
                packet=packet,
                directive=directive,
                turn=turn,
            ),
            context={"speaker_slug": speaker_slug},
            expected_inputs=["A valid packet, directive, and turn."],
            retry_advice="Retry the continuity review or continue conservatively without flags.",
            fallback=[],
            fallback_label="no-continuity-flags",
        )
        flags = flags_result.value or []
        canon_court_result = self.fail_safe.call(
            "canon_court.review",
            lambda: self.canon_court_service.review(
                packet=packet,
                turn=turn,
                events=events,
            ),
            context={"speaker_slug": speaker_slug},
            expected_inputs=["A valid packet, turn, and extracted event list."],
            retry_advice=(
                "Retry canon adjudication or continue conservatively without contradiction repair."
            ),
            fallback=None,
            fallback_label="skip-canon-court",
        )
        canon_report = canon_court_result.value
        if canon_report is not None:
            flags.extend(canon_report.additional_flags)
            if canon_report.revised_turn is not None and not canon_report.requires_repair:
                turn = canon_report.revised_turn
                events = canon_report.revised_events or events
                if canon_report.revised_questions:
                    turn = turn.model_copy(update={"new_questions": canon_report.revised_questions})
        critic_result = self.fail_safe.call(
            "critic.review",
            lambda: self.critic_service.review(
                packet=packet,
                turn=turn,
                flags=flags,
            ),
            context={"speaker_slug": speaker_slug},
            expected_inputs=["A valid packet, turn, and continuity flag list."],
            retry_advice="Retry critic scoring or continue without critic repair.",
            fallback=TurnCriticReport(),
            fallback_label="neutral-critic-report",
        )
        critic_report = critic_result.value or TurnCriticReport()
        repair_applied = False
        must_repair = bool(canon_report and canon_report.requires_repair)
        if must_repair or self._should_repair_turn(flags=flags, critic_score=critic_report.score):
            repair_applied = True
            if load_profile.load_tier in {"high", "critical"} and not must_repair:
                repaired_value = (
                    self.character_service.repair(
                        packet=packet,
                        thought_pulse_allowed=thought_pulse_allowed,
                    ),
                    None,
                    True,
                )
            else:
                repair_result = await self.fail_safe.call_async(
                    "character.repair_with_model",
                    lambda: self.character_service.repair_with_model(
                        packet=packet,
                        original_turn=turn,
                        critic_report=critic_report,
                        thought_pulse_allowed=thought_pulse_allowed,
                    ),
                    context={"speaker_slug": speaker_slug, "phase": "character-repair"},
                    expected_inputs=[
                        "A valid packet, original turn, and critic report for repair."
                    ],
                    retry_advice=(
                        "Retry with a valid repaired turn or let deterministic fallback keep "
                        "the stream safe."
                    ),
                    fallback=lambda: (
                        self.character_service.repair(
                            packet=packet,
                            thought_pulse_allowed=thought_pulse_allowed,
                        ),
                        None,
                        True,
                    ),
                    fallback_label="deterministic-character-fallback",
                )
                repaired_value = repair_result.value or (
                    self.character_service.repair(
                        packet=packet,
                        thought_pulse_allowed=thought_pulse_allowed,
                    ),
                    None,
                    True,
                )
            turn, repair_stats, repair_degraded = repaired_value
            degraded_mode = degraded_mode or repair_degraded
            if stats is None:
                stats = repair_stats
            events = self.event_extractor.extract(speaker_slug=speaker_slug, turn=turn)
            flags = self.continuity_guard.review_turn(
                packet=packet,
                directive=directive,
                turn=turn,
            )
            critic_report = self.critic_service.review(
                packet=packet,
                turn=turn,
                flags=flags,
            )

        persisted_result = self.fail_safe.call(
            "repository.record_turn",
            lambda: self.repository.record_turn(
                speaker_slug=speaker_slug,
                speaker_label=packet.full_name.split()[0],
                turn=turn,
                events=events,
                flags=flags,
                directive_id=directive.get("id"),
                degraded_mode=degraded_mode,
                latency_ms=stats.latency_ms if stats else None,
                now=now,
            ),
            context={
                "speaker_slug": speaker_slug,
                "directive_id": directive.get("id"),
                "phase": "turn-persist",
            },
            expected_inputs=["A writable MySQL state and a valid character turn payload."],
            retry_advice=(
                "Restore persistence. The runtime will avoid printing unpersisted chat lines and "
                "will try the next iteration."
            ),
            fallback=None,
        )
        persisted = persisted_result.value
        if persisted is None:
            return await self._pause_after_failed_iteration(once=once)

        if canon_report and canon_report.findings:
            self.fail_safe.call(
                "repository.record_canon_court_findings",
                lambda: self.repository.record_canon_court_findings(
                    findings=canon_report.findings,
                    message_id=persisted["message_id"],
                    now=now,
                ),
                context={"speaker_slug": speaker_slug, "message_id": persisted["message_id"]},
                expected_inputs=["A persisted message id and writable canon_court_findings table."],
                retry_advice="Restore canon-court persistence so contradiction telemetry resumes.",
            )

        self.fail_safe.call(
            "repository.record_public_turn_review",
            lambda: self.repository.record_public_turn_review(
                message_id=persisted["message_id"],
                speaker_slug=speaker_slug,
                report=critic_report,
                turn=turn,
                repaired=repair_applied,
                strategic_brief=manager_packet.strategic_brief,
                now=now,
            ),
            context={"speaker_slug": speaker_slug, "message_id": persisted["message_id"]},
            expected_inputs=[
                "A persisted message id, final critic report, and writable review tables."
            ],
            retry_advice="Restore review persistence so critique telemetry can resume.",
        )
        highlight_result = self.fail_safe.call(
            "highlights.maybe_record",
            lambda: self.highlight_service.maybe_record(
                message_id=persisted["message_id"],
                speaker_slug=speaker_slug,
                turn=turn,
                report=critic_report,
                strategic_brief=manager_packet.strategic_brief,
                now=now,
            ),
            context={"speaker_slug": speaker_slug, "message_id": persisted["message_id"]},
            expected_inputs=[
                "A persisted message id, critic report, and writable highlight package tables."
            ],
            retry_advice="Restore highlight persistence so clip packaging can resume.",
        )
        latest_highlight = highlight_result.value
        monetization_result = self.fail_safe.call(
            "monetization.maybe_record",
            lambda: self.monetization_service.maybe_record(
                message_id=persisted["message_id"],
                speaker_slug=speaker_slug,
                turn=turn,
                report=critic_report,
                strategic_brief=manager_packet.strategic_brief,
                highlight_package=latest_highlight,
                programming_grid_digest=manager_packet.programming_grid_digest,
                now=now,
            ),
            context={"speaker_slug": speaker_slug, "message_id": persisted["message_id"]},
            expected_inputs=[
                "A persisted message id, critic report, and writable monetization tables."
            ],
            retry_advice="Restore monetization persistence so packaging telemetry can resume.",
        )
        latest_monetization = monetization_result.value

        self.fail_safe.call(
            "beats.reconcile_turn",
            lambda: self.beat_service.reconcile_turn(turn=turn, events=events, now=now),
            context={"speaker_slug": speaker_slug},
            expected_inputs=["A valid turn, extracted events, and writable beats table."],
            retry_advice="Retry beat reconciliation on the next iteration.",
        )
        arcs_result = self.fail_safe.call(
            "repository.list_open_arcs",
            lambda: self.repository.list_open_arcs(limit=12),
            context={"phase": "progression"},
            expected_inputs=["Readable story_arcs rows in MySQL."],
            retry_advice="Restore story arc persistence so progression can resume.",
            fallback=[],
            fallback_label="no-open-arcs",
        )
        progression_result = self.fail_safe.call(
            "progression.plan",
            lambda: self.progression_service.plan(
                arcs=arcs_result.value or [],
                events=events,
                now=now,
            ),
            context={"speaker_slug": speaker_slug},
            expected_inputs=["Readable arc snapshots and extracted events."],
            retry_advice="Retry progression planning or continue without arc updates.",
            fallback=StoryProgressionPlan(),
            fallback_label="empty-progression-plan",
        )
        progression = progression_result.value or StoryProgressionPlan()
        self.fail_safe.call(
            "repository.apply_story_progression",
            lambda: self.repository.apply_story_progression(progression, now=now),
            context={"speaker_slug": speaker_slug},
            expected_inputs=["A valid StoryProgressionPlan and writable MySQL state."],
            retry_advice="Retry progression persistence on the next iteration.",
        )
        self.fail_safe.call(
            "world_tracking.capture_turn",
            lambda: self.world_tracking_service.capture_turn(
                packet=packet,
                turn=turn,
                events=events,
                now=now,
            ),
            context={"speaker_slug": speaker_slug, "phase": "world-tracking"},
            expected_inputs=["Readable world-tracking state and a valid persisted turn payload."],
            retry_advice="Retry world tracking on the next iteration.",
        )
        self._refresh_chronology_graph(now=now, force=True)
        self._refresh_hourly_ledger(now=now)
        self._refresh_programming_grid(now=now)
        self._refresh_season_planner(now=now)
        self._refresh_canon(now=now)

        self.fail_safe.call(
            "renderer.render_message",
            lambda: self.renderer.render_message(
                when=persisted["created_at"],
                speaker_slug=speaker_slug,
                speaker_label=packet.full_name.split()[0],
                content=turn.public_message,
            ),
            context={"speaker_slug": speaker_slug},
            expected_inputs=["A valid renderer and persisted public message."],
            retry_advice="Retry rendering after the next successful persisted turn.",
        )
        if persisted["thought_pulse"]:
            self.fail_safe.call(
                "renderer.render_thought_pulse",
                lambda: self.renderer.render_thought_pulse(
                    when=persisted["created_at"],
                    speaker_label=packet.full_name.split()[0],
                    content=persisted["thought_pulse"],
                ),
                context={"speaker_slug": speaker_slug},
                expected_inputs=["A valid renderer and persisted thought pulse."],
                retry_advice="Retry rendering after the next successful persisted turn.",
            )

        flush_every = max(1, self.config.runtime.periodic_flush_messages)
        if persisted["tick_no"] % flush_every == 0:
            self.fail_safe.call(
                "runtime.write_turn_checkpoint",
                lambda: self.repository.write_checkpoint(reason="turn-flush"),
                context={"tick_no": persisted["tick_no"]},
                expected_inputs=["A writable run_state row in MySQL."],
                retry_advice="Restore database connectivity so checkpoints can resume.",
            )

        self.fail_safe.call(
            "broadcast_assets.maybe_record",
            lambda: self.broadcast_asset_service.maybe_record(
                message_id=persisted["message_id"],
                speaker_slug=speaker_slug,
                turn=turn,
                report=critic_report,
                highlight_package=latest_highlight,
                monetization_package=latest_monetization,
                strategic_brief=manager_packet.strategic_brief,
                viewer_signals=viewer_signals,
                now=now,
            ),
            context={"speaker_slug": speaker_slug, "message_id": persisted["message_id"]},
            expected_inputs=[
                "A persisted message id, recent monetization context, "
                "and writable broadcast asset tables."
            ],
            retry_advice="Restore broadcast-asset persistence so export packaging can resume.",
        )

        self._note_runtime_success(now=now, load_profile=load_profile)

        if once:
            return True

        await self._sleep_between_turns(manager_packet=manager_packet)
        return False

    async def _emit_recap(self, bucket_end_at) -> None:
        self.fail_safe.call(
            "runtime.set_recap_phase",
            lambda: self.repository.set_runtime_status(
                "running",
                phase="recap-generation",
                extra_metadata={"recap_bucket_end_at": bucket_end_at.isoformat()},
            ),
            context={"bucket_end_at": bucket_end_at.isoformat()},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so recap phase tracking can recover.",
        )
        bundle_result = await self.fail_safe.call_async(
            "recap.generate_bundle",
            lambda: self.recap_service.generate_bundle(bucket_end_at=bucket_end_at),
            context={"bucket_end_at": bucket_end_at.isoformat()},
            expected_inputs=["Stored events, summaries, and a recap-capable announcer model."],
            retry_advice="Retry recap generation or rely on the deterministic recap fallback.",
            fallback=None,
        )
        bundle = bundle_result.value
        if bundle is None:
            return
        self.fail_safe.call(
            "repository.save_recap_bundle",
            lambda: self.repository.save_recap_bundle(
                bucket_end_at=bucket_end_at,
                bundle=bundle,
            ),
            context={"bucket_end_at": bucket_end_at.isoformat()},
            expected_inputs=["A valid RecapBundle and writable summary tables."],
            retry_advice="Restore summary persistence so recap bundles can be saved again.",
        )
        self.fail_safe.call(
            "repository.record_recap_quality_scores",
            lambda: self.repository.record_recap_quality_scores(
                bucket_end_at=bucket_end_at,
                quality_scores=self.recap_service.evaluate_quality(bundle=bundle),
            ),
            context={"bucket_end_at": bucket_end_at.isoformat()},
            expected_inputs=["A recap bundle and writable recap_quality_scores table."],
            retry_advice=(
                "Restore recap-quality persistence so the strategist can score recap health again."
            ),
        )
        self.fail_safe.call(
            "runtime.write_recap_checkpoint",
            lambda: self.repository.write_checkpoint(reason="recap"),
            context={"bucket_end_at": bucket_end_at.isoformat()},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so recap checkpoints can resume.",
        )
        self.fail_safe.call(
            "renderer.render_recap",
            lambda: self.renderer.render_recap(when=bucket_end_at, bundle=bundle),
            context={"bucket_end_at": bucket_end_at.isoformat()},
            expected_inputs=["A valid renderer and recap bundle."],
            retry_advice="Retry recap rendering after the next generated bundle.",
        )

    async def _checkpoint_loop(self) -> None:
        interval = max(1, self.config.runtime.checkpoint_interval_seconds)
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                self.fail_safe.call(
                    "runtime.write_heartbeat_checkpoint",
                    lambda: self.repository.write_checkpoint(reason="heartbeat"),
                    context={"phase": "heartbeat"},
                    expected_inputs=["A writable run_state row in MySQL."],
                    retry_advice="Restore database connectivity so heartbeat checkpoints resume.",
                )

    async def _god_ai_loop(self) -> None:
        force = True
        while not self._stop_event.is_set():
            load_profile = self._capture_load_profile(now=utcnow())
            if load_profile.load_tier in {"high", "critical"} and not force:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=60)
                except TimeoutError:
                    continue
            refresh_result = await self.fail_safe.call_async(
                "god_ai.refresh_background",
                lambda force_now=force: self.god_ai_service.refresh_if_due(
                    now=utcnow(),
                    force=force_now,
                ),
                context={"force": force},
                expected_inputs=[
                    "A valid manager packet, simulation report, and strategic brief persistence."
                ],
                retry_advice=(
                    "Allow the deterministic strategic brief to stand until the background "
                    "planner recovers."
                ),
                fallback=None,
                fallback_label="existing-strategic-brief",
            )
            force = False
            if refresh_result.failure is not None:
                logger.debug("background God-AI recovered via failsafe")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=60)
            except TimeoutError:
                continue

    def stop(self) -> None:
        self._stop_event.set()

    def _refresh_hot_patch(self, *, now) -> None:
        if self.hot_patch_controller is None:
            return
        report_result = self.fail_safe.call(
            "hotpatch.refresh_if_due",
            lambda: self.hot_patch_controller.refresh_if_due(now=now),
            context={"phase": "hot-patch-check"},
            expected_inputs=["Readable watched files and a valid runtime rebuild callback."],
            retry_advice="Fix the patched file and save again. The runtime will retry shortly.",
            fallback=None,
            fallback_label="unchanged-runtime-components",
        )
        report = report_result.value
        if report is None:
            return
        self.fail_safe.call(
            "runtime.record_hot_patch_metadata",
            lambda: self.repository.merge_runtime_metadata(
                {
                    "hot_patch": {
                        "applied_at": now.isoformat(),
                        "changed_files": report.changed_files,
                        "reloaded_modules": report.reloaded_modules,
                        "shadow_validated": report.shadow_validated,
                        "validation_checks": report.validation_checks,
                    }
                },
                now=now,
            ),
            context={"changed_files": report.changed_files},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so hot patch metadata can be tracked.",
        )
        logger.info("Applied hot patch for %s", ", ".join(report.changed_files))

    def _refresh_audience_control(self, *, now, force: bool = False) -> AudienceControlReport:
        result = self.fail_safe.call(
            "audience.refresh_if_due",
            lambda: self.audience_control_service.refresh_if_due(now=now, force=force),
            context={"path": self.config.audience.update_file_path, "force": force},
            expected_inputs=[
                "A readable update.txt file or a recoverable persisted audience-control block."
            ],
            retry_advice="Fix update.txt syntax or wait for the next audience poll.",
            fallback=lambda: self._last_good_audience_control,
            fallback_label="last-good-audience-control",
        )
        report = result.value or self._last_good_audience_control
        self._last_good_audience_control = report
        return report

    def _refresh_viewer_signals(self, *, now, force: bool = False) -> list[Any]:
        result = self.fail_safe.call(
            "viewer_signals.refresh_if_due",
            lambda: self.viewer_signal_service.refresh_if_due(now=now, force=force),
            context={"path": self.config.viewer_signals.source_file_path, "force": force},
            expected_inputs=[
                "A readable viewer_signals.yaml file or a recoverable "
                "persisted viewer signal state."
            ],
            retry_advice="Fix viewer_signals.yaml syntax or wait for the next ingestion poll.",
            fallback=lambda: self._last_viewer_signals,
            fallback_label="last-active-viewer-signals",
        )
        signals = result.value or self._last_viewer_signals
        self._last_viewer_signals = signals
        return signals

    def _refresh_hourly_ledger(self, *, now) -> None:
        self.fail_safe.call(
            "hourly_ledger.refresh",
            lambda: self.hourly_ledger_service.refresh(now=now),
            context={"phase": "hourly-ledger"},
            expected_inputs=["Readable recent events and a writable hourly_progress_ledger table."],
            retry_advice=(
                "Restore repository access so the hourly progression contract can refresh."
            ),
        )

    def _refresh_programming_grid(self, *, now, force: bool = False) -> None:
        self.fail_safe.call(
            "programming_grid.refresh",
            lambda: self.programming_grid_service.refresh(now=now, force=force),
            context={"phase": "programming-grid", "force": force},
            expected_inputs=["Readable recent events and a writable programming_grid_slots table."],
            retry_advice=(
                "Restore repository access so the daily and weekly programming grid can refresh."
            ),
        )

    def _refresh_season_planner(self, *, now, force: bool = False) -> None:
        self.fail_safe.call(
            "season_planner.refresh",
            lambda: self.season_planner_service.refresh(now=now, force=force),
            context={"phase": "season-planner", "force": force},
            expected_inputs=["Readable arcs, events, and programming grid persistence."],
            retry_advice="Restore repository access so the season planner can refresh.",
        )

    def _refresh_house_pressure(self, *, now, force: bool = False) -> None:
        self.fail_safe.call(
            "house.refresh",
            lambda: self.house_pressure_service.refresh(now=now, force=force),
            context={"force": force},
            expected_inputs=["A seeded house_state, scene_state, and readable recent events."],
            retry_advice="Restore house state persistence so deterministic pressure can recover.",
            fallback=lambda: self.repository.get_house_state_snapshot(),
            fallback_label="last-house-state",
        )

    def _refresh_story_gravity(self, *, now, force: bool = False) -> None:
        self.fail_safe.call(
            "story_gravity.refresh",
            lambda: self.story_gravity_service.refresh(now=now, force=force),
            context={"force": force},
            expected_inputs=[
                "Readable world memory, summaries, events, and a writable story_gravity_state."
            ],
            retry_advice="Restore story gravity persistence so the north star can refresh.",
        )

    def _refresh_canon(self, *, now) -> None:
        self.fail_safe.call(
            "canon.refresh",
            lambda: self.canon_service.refresh(now=now),
            context={"phase": "canon-refresh"},
            expected_inputs=[
                "Readable world, scene, event, and summary state plus writable canon_capsules."
            ],
            retry_advice="Restore repository access so bounded canon memory can refresh.",
        )

    def _refresh_voice_fingerprints(self, *, now, force: bool = False) -> None:
        self.fail_safe.call(
            "voice_fingerprints.refresh",
            lambda: self.voice_fingerprint_service.refresh(now=now, force=force),
            context={"phase": "voice-fingerprints", "force": force},
            expected_inputs=[
                "Readable character roster, recent messages, and a writable "
                "voice_fingerprints table."
            ],
            retry_advice="Restore repository access so voice fingerprinting can refresh.",
        )

    def _refresh_world_tracking(self, *, now, force: bool = False) -> None:
        self.fail_safe.call(
            "world_tracking.refresh",
            lambda: self.world_tracking_service.refresh(now=now, force=force),
            context={"phase": "world-tracking", "force": force},
            expected_inputs=[
                "Readable character positions, story objects, and writable timeline tables."
            ],
            retry_advice="Restore repository access so deterministic world tracking can refresh.",
        )

    def _refresh_chronology_graph(self, *, now, force: bool = False) -> None:
        self.fail_safe.call(
            "chronology_graph.refresh",
            lambda: self.chronology_graph_service.refresh(now=now, force=force),
            context={"phase": "chronology-graph", "force": force},
            expected_inputs=[
                "Readable timeline facts, object possession state, and writable "
                "chronology graph tables."
            ],
            retry_advice="Restore repository access so chronology graph updates can resume.",
        )

    def _refresh_guest_circulation(self, *, now, force: bool = False) -> None:
        self.fail_safe.call(
            "guest_circulation.refresh",
            lambda: self.guest_circulation_service.refresh(now=now, force=force),
            context={"phase": "guest-circulation", "force": force},
            expected_inputs=[
                "Readable world and house state, plus writable guest profile and beat tables."
            ],
            retry_advice="Restore repository access so guest circulation can refresh.",
        )

    def _build_manager_packet(
        self,
        *,
        audience_control: AudienceControlReport,
        load_profile: LoadProfileSnapshot | None = None,
        ops_snapshot: OpsTelemetrySnapshot | None = None,
    ) -> ManagerContextPacket | None:
        result = self.fail_safe.call(
            "context.build_manager_packet",
            lambda: self.assembler.build_manager_packet(
                audience_control=audience_control,
                load_profile=load_profile,
                ops_snapshot=ops_snapshot,
            ),
            context={"phase": "manager-context"},
            expected_inputs=[
                "Readable world_state, scene_state, summaries, events, and character state."
            ],
            retry_advice=(
                "Restore repository reads or allow the runtime to use the last good manager "
                "packet until fresh context is available."
            ),
            fallback=lambda: self._last_good_manager_packet,
            fallback_label="last-good-manager-packet",
        )
        packet = result.value
        if packet is not None:
            self._last_good_manager_packet = packet
        return packet

    def _capture_load_profile(self, *, now) -> LoadProfileSnapshot:
        pending_jobs = int(self._pending_manager_task is not None) + int(
            self._god_ai_task is not None
        )
        result = self.fail_safe.call(
            "load_orchestration.build_profile",
            lambda: self.load_orchestration_service.build_profile(
                pending_manager_prefetch=self._pending_manager_task is not None,
                pending_background_jobs=pending_jobs,
                now=now,
            ),
            context={"phase": "load-profile"},
            expected_inputs=["Readable run_state metadata and recent message latencies."],
            retry_advice=(
                "Restore repository reads so load-aware orchestration can fall back cleanly."
            ),
            fallback=lambda: self._last_load_profile,
            fallback_label="last-load-profile",
        )
        profile = result.value or self._last_load_profile
        self._last_load_profile = profile
        return profile

    def _capture_ops_snapshot(
        self,
        *,
        load_profile: LoadProfileSnapshot,
        now,
    ) -> OpsTelemetrySnapshot | None:
        result = self.fail_safe.call(
            "ops_dashboard.capture",
            lambda: self.ops_dashboard_service.capture(load_profile=load_profile, now=now),
            context={"phase": "ops-dashboard", "load_tier": load_profile.load_tier},
            expected_inputs=[
                "Readable run_state, strategy state, and a writable ops_telemetry table."
            ],
            retry_advice="Restore repository access so operational telemetry can refresh.",
            fallback=lambda: self._last_ops_snapshot,
            fallback_label="last-ops-snapshot",
        )
        snapshot = result.value or self._last_ops_snapshot
        if snapshot is not None:
            self._last_ops_snapshot = snapshot
        return snapshot

    def _build_character_packet(self, *, speaker_slug: str, directive: dict) -> Any | None:
        result = self.fail_safe.call(
            "context.build_character_packet",
            lambda: self.assembler.build_character_packet(speaker_slug, directive),
            context={"speaker_slug": speaker_slug},
            expected_inputs=[
                "Readable character, relationship, location, and scene state for the speaker."
            ],
            retry_advice=(
                "Restore repository reads or allow the runtime to reuse the last good packet "
                "for this speaker."
            ),
            fallback=lambda: self._last_good_character_packet_by_slug.get(speaker_slug),
            fallback_label="last-good-character-packet",
        )
        packet = result.value
        if packet is not None:
            self._last_good_character_packet_by_slug[speaker_slug] = packet
        return packet

    def _get_run_state(self) -> dict[str, Any] | None:
        result = self.fail_safe.call(
            "runtime.get_run_state",
            self.repository.get_run_state,
            context={"phase": "run-state"},
            expected_inputs=["A persisted run_state row in MySQL."],
            retry_advice=(
                "Restore run_state persistence or allow the runtime to reuse the last good "
                "run-state snapshot."
            ),
            fallback=lambda: self._last_good_run_state or self.repository.ensure_run_state(),
            fallback_label="last-good-run-state",
        )
        run_state = result.value
        if run_state is not None:
            self._last_good_run_state = run_state
        return run_state

    async def _sleep_between_turns(self, *, manager_packet: ManagerContextPacket) -> None:
        delay = self.scheduler.compute_delay_seconds(health=manager_packet.pacing_health)
        if self._last_load_profile.load_tier == "critical":
            delay = max(0.4, delay - 0.6)
        elif self._last_load_profile.load_tier == "high":
            delay = max(0.5, delay - 0.3)
        self.fail_safe.call(
            "runtime.set_sleep_phase",
            lambda: self.repository.set_runtime_status(
                "running",
                phase="sleeping",
                extra_metadata={"next_delay_seconds": round(delay, 3)},
            ),
            context={"delay_seconds": round(delay, 3)},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so runtime phases can update.",
        )
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
        except TimeoutError:
            return

    async def _pause_after_failed_iteration(self, *, once: bool) -> bool:
        if once:
            return True
        await asyncio.sleep(max(1, self.config.failsafe.unexpected_iteration_delay_seconds))
        return False

    def _apply_ops_remediations(self, *, snapshot: OpsTelemetrySnapshot | None, now) -> None:
        if snapshot is None:
            return
        actions = set(snapshot.auto_remediations)
        if "force-checkpoint" in actions:
            self.fail_safe.call(
                "runtime.ops_force_checkpoint",
                lambda: self.repository.write_checkpoint(reason="ops-remediation", phase="ops"),
                context={"phase": "ops-remediation"},
                expected_inputs=["A writable run_state row in MySQL."],
                retry_advice="Restore database connectivity so ops checkpoints can resume.",
            )
        if (
            "refresh-strategic-brief" in actions
            and self.config.god_ai.enabled
            and self._god_ai_task is None
            and not self._stop_event.is_set()
        ):
            self._god_ai_task = asyncio.create_task(self._god_ai_loop())

    def _note_runtime_failure(self, *, now, reason: str) -> None:
        self.fail_safe.call(
            "runtime.note_failure",
            lambda: self.repository.merge_runtime_metadata(
                {
                    "recent_failure_count": int(
                        (self._last_good_run_state or {})
                        .get("metadata", {})
                        .get(
                            "recent_failure_count",
                            0,
                        )
                    )
                    + 1,
                    "last_failure_at": now.isoformat(),
                    "last_failure_reason": reason[:220],
                },
                now=now,
            ),
            context={"reason": reason[:120]},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so runtime failure metadata can update.",
        )

    def _note_runtime_success(self, *, now, load_profile: LoadProfileSnapshot) -> None:
        self.fail_safe.call(
            "runtime.note_success",
            lambda: self.repository.merge_runtime_metadata(
                {
                    "recent_failure_count": 0,
                    "last_success_at": now.isoformat(),
                    "load_profile": load_profile.model_dump(mode="json"),
                },
                now=now,
            ),
            context={"load_tier": load_profile.load_tier},
            expected_inputs=["A writable run_state row in MySQL."],
            retry_advice="Restore database connectivity so runtime success metadata can update.",
        )

    def _fallback_character_states(self) -> list[dict[str, Any]]:
        return [{"slug": slug, "last_spoke_at": None, "silence_streak": 0} for slug in self._roster]

    def _preview_candidate(
        self,
        *,
        packet,
        directive: dict[str, Any],
        turn,
        stats,
        degraded_mode: bool,
        candidate_index: int,
        speaker_slug: str,
    ) -> EvaluatedTurnCandidate:
        preview_events = (
            self.fail_safe.call(
                "event_extractor.preview_candidate",
                lambda: self.event_extractor.extract(speaker_slug=speaker_slug, turn=turn),
                context={"speaker_slug": speaker_slug, "candidate_index": candidate_index},
                expected_inputs=["A valid CharacterTurn with structured event candidates."],
                retry_advice="Retry candidate preview extraction or skip that candidate.",
                fallback=[],
                fallback_label="empty-candidate-events",
            ).value
            or []
        )
        preview_flags = (
            self.fail_safe.call(
                "continuity_guard.preview_candidate",
                lambda: self.continuity_guard.review_turn(
                    packet=packet,
                    directive=directive,
                    turn=turn,
                ),
                context={"speaker_slug": speaker_slug, "candidate_index": candidate_index},
                expected_inputs=["A valid packet, directive, and candidate turn."],
                retry_advice="Retry candidate preview continuity or skip that candidate.",
                fallback=[],
                fallback_label="no-candidate-flags",
            ).value
            or []
        )
        preview_critic = (
            self.fail_safe.call(
                "critic.preview_candidate",
                lambda: self.critic_service.review(
                    packet=packet,
                    turn=turn,
                    flags=preview_flags,
                ),
                context={"speaker_slug": speaker_slug, "candidate_index": candidate_index},
                expected_inputs=["A valid packet, candidate turn, and preview flags."],
                retry_advice=(
                    "Retry candidate preview critic scoring or fall back to neutral scoring."
                ),
                fallback=TurnCriticReport(),
                fallback_label="neutral-candidate-critic",
            ).value
            or TurnCriticReport()
        )
        return EvaluatedTurnCandidate(
            turn=turn,
            critic_report=preview_critic,
            events=preview_events,
            flags=preview_flags,
            stats=stats,
            degraded_mode=degraded_mode,
            candidate_index=candidate_index,
        )

    def _should_repair_turn(self, *, flags, critic_score: int) -> bool:
        repairable = {"robotic-voice", "chat-register", "reveal-budget", "forbidden-knowledge"}
        if any(flag.flag_type in repairable for flag in flags):
            return True
        return critic_score < self.config.critic.repair_threshold

    def _prefetched_plan_is_fresh(self, plan, prepared_at, now) -> bool:
        if plan is None or prepared_at is None:
            return False
        return (ensure_utc(now) - ensure_utc(prepared_at)).total_seconds() <= 8 * 60

    def _sync_audience_rollout(self, *, audience_control, last_key, now):
        sync_key = (audience_control.fingerprint, audience_control.file_status)
        if sync_key == last_key:
            return sync_key
        self.fail_safe.call(
            "beats.sync_audience_rollout",
            lambda: self.beat_service.sync_audience_rollout(audience_control, now=now),
            context={"fingerprint": audience_control.fingerprint},
            expected_inputs=["A valid audience control report and writable beats table."],
            retry_advice="Retry on the next audience-control change or poll interval.",
        )
        return sync_key

    async def _cancel_background_task(self, task: asyncio.Task | None) -> None:
        if task is None:
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(task, timeout=2)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                logger.debug("signal handlers unavailable for %s", sig)

    def rebuild_runtime_components(
        self,
        changed_files: list[str],
        changed_modules: list[str],
    ) -> None:
        config_module = import_module("lantern_house.config")
        latest_config = config_module.load_config(self.config.loaded_from)
        self.config = latest_config
        self.fail_safe = import_module("lantern_house.runtime.failsafe").FailSafeExecutor(
            latest_config.failsafe
        )

        pacing_module = import_module("lantern_house.quality.pacing")
        governance_module = import_module("lantern_house.quality.governance")
        context_module = import_module("lantern_house.context.assembler")
        audience_module = import_module("lantern_house.services.audience")
        viewer_signals_module = import_module("lantern_house.services.viewer_signals")
        beats_module = import_module("lantern_house.services.beats")
        broadcast_assets_module = import_module("lantern_house.services.broadcast_assets")
        hourly_ledger_module = import_module("lantern_house.services.hourly_ledger")
        programming_grid_module = import_module("lantern_house.services.programming_grid")
        season_planner_module = import_module("lantern_house.services.season_planner")
        canon_module = import_module("lantern_house.services.canon")
        canon_court_module = import_module("lantern_house.services.canon_court")
        chronology_graph_module = import_module("lantern_house.services.chronology_graph")
        house_module = import_module("lantern_house.services.house")
        guest_circulation_module = import_module("lantern_house.services.guest_circulation")
        gravity_module = import_module("lantern_house.services.story_gravity")
        highlights_module = import_module("lantern_house.services.highlights")
        monetization_module = import_module("lantern_house.services.monetization")
        load_module = import_module("lantern_house.services.load_orchestration")
        ops_module = import_module("lantern_house.services.ops_dashboard")
        simulation_module = import_module("lantern_house.services.simulation_lab")
        soak_audit_module = import_module("lantern_house.services.soak_audit")
        god_ai_module = import_module("lantern_house.services.god_ai")
        manager_module = import_module("lantern_house.services.manager")
        character_module = import_module("lantern_house.services.character")
        critic_module = import_module("lantern_house.services.critic")
        turn_selection_module = import_module("lantern_house.services.turn_selection")
        world_tracking_module = import_module("lantern_house.services.world_tracking")
        voice_fingerprints_module = import_module("lantern_house.services.voice_fingerprints")
        recap_module = import_module("lantern_house.services.recaps")
        progression_module = import_module("lantern_house.services.progression")
        scheduler_module = import_module("lantern_house.runtime.scheduler")
        recovery_module = import_module("lantern_house.runtime.recovery")
        extractor_module = import_module("lantern_house.services.event_extractor")
        rendering_module = import_module("lantern_house.rendering.terminal")

        pacing = pacing_module.PacingHealthEvaluator()
        governance = governance_module.StoryGovernanceEvaluator()
        self.assembler = context_module.ContextAssembler(
            self.repository,
            pacing,
            governance,
        )
        self.audience_control_service = audience_module.AudienceControlService(
            latest_config.audience,
            self.repository,
        )
        self.viewer_signal_service = viewer_signals_module.ViewerSignalIngestionService(
            latest_config.viewer_signals,
            self.repository,
        )
        self.beat_service = beats_module.StoryBeatService(self.repository)
        self.hourly_ledger_service = hourly_ledger_module.HourlyBeatLedgerService(
            self.repository,
            latest_config.hourly_beat_ledger,
        )
        self.programming_grid_service = programming_grid_module.ProgrammingGridService(
            self.repository,
            latest_config.programming_grid,
        )
        self.season_planner_service = season_planner_module.SeasonPlannerService(
            self.repository,
            latest_config.season_planner,
        )
        self.canon_service = canon_module.CanonDistillationService(
            self.repository,
            latest_config.canon,
        )
        self.canon_court_service = canon_court_module.CanonCourtService(latest_config.canon_court)
        self.chronology_graph_service = chronology_graph_module.ChronologyGraphService(
            self.repository,
            latest_config.chronology_graph,
        )
        self.house_pressure_service = house_module.HousePressureService(
            self.repository,
            latest_config.house_pressure,
        )
        self.world_tracking_service = world_tracking_module.WorldTrackingService(
            self.repository,
            latest_config.world_tracking,
        )
        self.voice_fingerprint_service = voice_fingerprints_module.VoiceFingerprintService(
            self.repository,
            latest_config.voice_fingerprints,
        )
        self.story_gravity_service = gravity_module.StoryGravityService(
            self.repository,
            latest_config.story_gravity,
        )
        self.guest_circulation_service = guest_circulation_module.GuestCirculationService(
            self.repository,
            latest_config.guest_circulation,
        )
        simulation_lab = simulation_module.SimulationLabService(latest_config.simulation)
        soak_audit_service = soak_audit_module.SoakAuditService(
            self.repository,
            simulation_lab,
            latest_config.soak_audit,
        )
        self.god_ai_service = god_ai_module.GodAIService(
            config=latest_config.god_ai,
            assembler=self.assembler,
            audience_control_service=self.audience_control_service,
            simulation_lab=simulation_lab,
            soak_audit_service=soak_audit_service,
            llm=self.llm_client,
            model_name=latest_config.models.god_ai,
        )
        self.manager_service = manager_module.StoryManagerService(
            self.llm_client,
            latest_config.models.manager,
            latest_config.runtime,
        )
        self.character_service = character_module.CharacterService(
            self.llm_client,
            latest_config.models.character,
            latest_config.models.repair,
        )
        self.turn_selection_service = turn_selection_module.TurnSelectionService(
            latest_config.turn_selection
        )
        self.critic_service = critic_module.TurnCriticService(latest_config.critic)
        self.highlight_service = highlights_module.HighlightPackagingService(
            self.repository,
            latest_config.highlights,
        )
        self.monetization_service = monetization_module.MonetizationPackagingService(
            self.repository,
            latest_config.monetization,
        )
        self.broadcast_asset_service = broadcast_assets_module.BroadcastAssetService(
            self.repository,
            latest_config.broadcast_assets,
        )
        self.recap_service = recap_module.RecapService(
            self.repository,
            self.llm_client,
            latest_config.models.announcer,
        )
        self.progression_service = progression_module.StoryProgressionService()
        self.load_orchestration_service = load_module.LoadOrchestrationService(
            self.repository,
            latest_config.load_orchestration,
        )
        self.ops_dashboard_service = ops_module.OpsDashboardService(
            self.repository,
            latest_config.ops_dashboard,
        )
        self.scheduler = scheduler_module.TurnScheduler(
            runtime_config=latest_config.runtime,
            timing_config=latest_config.timing,
            thought_pulse_config=latest_config.thought_pulses,
        )
        self.recovery_service = recovery_module.RecoveryService(self.repository)
        self.event_extractor = extractor_module.EventExtractor()
        self.continuity_guard = pacing_module.ContinuityGuard()
        self.renderer = rendering_module.TerminalRenderer()
        self.renderer.register_characters(
            self._color_map or self.repository.get_character_color_map()
        )
        self._last_good_audience_control = AudienceControlReport()
        self._last_viewer_signals = []
        self._last_good_manager_packet = None
        self._last_good_character_packet_by_slug.clear()
        self._last_load_profile = LoadProfileSnapshot()
        self._last_ops_snapshot = None

        if self.hot_patch_controller is not None and changed_modules:
            hotpatch_module = import_module("lantern_house.runtime.hotpatch")
            self.hot_patch_controller = hotpatch_module.HotPatchController(
                config=build_hot_patch_config(latest_config),
                project_root=Path(__file__).resolve().parents[3],
                rebuild_runtime=self.rebuild_runtime_components,
                validate_patch=self.hot_patch_validator,
            )
            self.hot_patch_controller.bootstrap()
