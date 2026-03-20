from __future__ import annotations

import asyncio
import contextlib
import logging
import signal

from lantern_house.config import AppConfig
from lantern_house.context.assembler import ContextAssembler
from lantern_house.db.repository import StoryRepository
from lantern_house.quality.pacing import ContinuityGuard
from lantern_house.rendering.terminal import TerminalRenderer
from lantern_house.runtime.recovery import RecoveryService
from lantern_house.runtime.scheduler import TurnScheduler
from lantern_house.services.audience import AudienceControlService
from lantern_house.services.character import CharacterService
from lantern_house.services.event_extractor import EventExtractor
from lantern_house.services.manager import StoryManagerService
from lantern_house.services.progression import StoryProgressionService
from lantern_house.services.recaps import RecapService
from lantern_house.utils.time import utcnow

logger = logging.getLogger(__name__)


class RuntimeOrchestrator:
    def __init__(
        self,
        *,
        config: AppConfig,
        repository: StoryRepository,
        assembler: ContextAssembler,
        audience_control_service: AudienceControlService,
        manager_service: StoryManagerService,
        character_service: CharacterService,
        recap_service: RecapService,
        progression_service: StoryProgressionService,
        scheduler: TurnScheduler,
        recovery_service: RecoveryService,
        event_extractor: EventExtractor,
        continuity_guard: ContinuityGuard,
        renderer: TerminalRenderer,
    ) -> None:
        self.config = config
        self.repository = repository
        self.assembler = assembler
        self.audience_control_service = audience_control_service
        self.manager_service = manager_service
        self.character_service = character_service
        self.recap_service = recap_service
        self.progression_service = progression_service
        self.scheduler = scheduler
        self.recovery_service = recovery_service
        self.event_extractor = event_extractor
        self.continuity_guard = continuity_guard
        self.renderer = renderer
        self._stop_event = asyncio.Event()

    async def run(self, *, once: bool = False) -> None:
        roster = [item["slug"] for item in self.repository.list_characters()]
        if not roster:
            raise RuntimeError("No story seed found. Run `lantern-house seed` first.")

        self.renderer.register_characters(self.repository.get_character_color_map())
        self._install_signal_handlers()
        checkpoint_task: asyncio.Task[None] | None = None
        pending_manager_task: asyncio.Task | None = None

        try:
            recovery = self.recovery_service.recover()
            if recovery["unclean_shutdown"]:
                logger.warning("Recovered from unclean shutdown using persisted checkpoint state.")
            self.repository.write_checkpoint(reason="startup", phase="recovery")
            for bucket in recovery["missed_recap_hours"]:
                await self._emit_recap(bucket)

            self.audience_control_service.refresh_if_due(now=utcnow(), force=True)
            self.repository.set_runtime_status("running", degraded_mode=False, phase="loop-ready")
            checkpoint_task = asyncio.create_task(self._checkpoint_loop())

            while not self._stop_event.is_set():
                now = utcnow()
                if self.config.recaps.enabled:
                    for bucket in self.repository.list_missing_recap_hours(now=now):
                        await self._emit_recap(bucket)

                audience_control = self.audience_control_service.refresh_if_due(now=now)
                directive = self.repository.get_latest_manager_directive()
                if pending_manager_task is not None and pending_manager_task.done():
                    try:
                        directive_plan = pending_manager_task.result()
                    except Exception as exc:
                        logger.warning("background manager refresh failed: %s", exc)
                    else:
                        run_state = self.repository.get_run_state()
                        directive = self.repository.record_manager_directive(
                            directive_plan,
                            tick_no=run_state["last_tick_no"] + 1,
                            now=now,
                        )
                    pending_manager_task = None

                manager_packet = self.assembler.build_manager_packet(
                    audience_control=audience_control
                )
                run_state = self.repository.get_run_state()
                if self.scheduler.should_refresh_manager(
                    run_state=run_state,
                    directive=directive,
                    health=manager_packet.pacing_health,
                    governance=manager_packet.story_governance,
                ):
                    if directive is None:
                        self.repository.set_runtime_status(
                            "running",
                            phase="manager-request",
                            extra_metadata={"manager_requested_at": now.isoformat()},
                            now=now,
                        )
                        directive_plan = await self.manager_service.plan(manager_packet, roster)
                        directive = self.repository.record_manager_directive(
                            directive_plan,
                            tick_no=run_state["last_tick_no"] + 1,
                            now=now,
                        )
                    elif pending_manager_task is None:
                        self.repository.set_runtime_status(
                            "running",
                            phase="manager-request",
                            extra_metadata={"manager_requested_at": now.isoformat()},
                            now=now,
                        )
                        pending_manager_task = asyncio.create_task(
                            self.manager_service.plan(manager_packet, roster)
                        )

                if directive is None:
                    raise RuntimeError("Manager directive unavailable after refresh attempt.")

                character_states = self.repository.list_character_states()
                speaker_slug = self.scheduler.select_speaker(
                    directive=directive, character_states=character_states
                )
                packet = self.assembler.build_character_packet(speaker_slug, directive)
                thought_pulse_allowed = self.scheduler.allow_thought_pulse(
                    directive=directive,
                    speaker_slug=speaker_slug,
                    run_state=run_state,
                    recent_pulse_count=self.repository.count_recent_thought_pulses(hours=1),
                )

                self.repository.set_runtime_status(
                    "running",
                    phase="character-request",
                    extra_metadata={"candidate_speaker": speaker_slug},
                    now=now,
                )
                turn, stats, degraded_mode = await self.character_service.generate(
                    packet=packet,
                    thought_pulse_allowed=thought_pulse_allowed,
                )
                events = self.event_extractor.extract(speaker_slug=speaker_slug, turn=turn)
                flags = self.continuity_guard.review_turn(
                    packet=packet,
                    directive=directive,
                    turn=turn,
                )
                if self._should_repair_turn(flags):
                    degraded_mode = True
                    turn = self.character_service.repair(
                        packet=packet,
                        thought_pulse_allowed=thought_pulse_allowed,
                    )
                    events = self.event_extractor.extract(speaker_slug=speaker_slug, turn=turn)
                    flags = self.continuity_guard.review_turn(
                        packet=packet,
                        directive=directive,
                        turn=turn,
                    )

                persisted = self.repository.record_turn(
                    speaker_slug=speaker_slug,
                    speaker_label=packet.full_name.split()[0],
                    turn=turn,
                    events=events,
                    flags=flags,
                    directive_id=directive.get("id"),
                    degraded_mode=degraded_mode,
                    latency_ms=stats.latency_ms if stats else None,
                    now=now,
                )
                progression = self.progression_service.plan(
                    arcs=self.repository.list_open_arcs(limit=12),
                    events=events,
                    now=now,
                )
                self.repository.apply_story_progression(progression, now=now)

                self.renderer.render_message(
                    when=persisted["created_at"],
                    speaker_slug=speaker_slug,
                    speaker_label=packet.full_name.split()[0],
                    content=turn.public_message,
                )
                if persisted["thought_pulse"]:
                    self.renderer.render_thought_pulse(
                        when=persisted["created_at"],
                        speaker_label=packet.full_name.split()[0],
                        content=persisted["thought_pulse"],
                    )

                flush_every = max(1, self.config.runtime.periodic_flush_messages)
                if persisted["tick_no"] % flush_every == 0:
                    self.repository.write_checkpoint(reason="turn-flush")

                if once:
                    break

                delay = self.scheduler.compute_delay_seconds(health=manager_packet.pacing_health)
                self.repository.set_runtime_status(
                    "running",
                    phase="sleeping",
                    extra_metadata={"next_delay_seconds": round(delay, 3)},
                )
                await asyncio.sleep(delay)
        finally:
            if pending_manager_task is not None:
                pending_manager_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await pending_manager_task
            if checkpoint_task is not None:
                checkpoint_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await checkpoint_task
            self.repository.write_checkpoint(reason="shutdown", phase="shutdown")
            self.repository.set_runtime_status("idle", degraded_mode=False, phase="idle")

    async def _emit_recap(self, bucket_end_at) -> None:
        self.repository.set_runtime_status(
            "running",
            phase="recap-generation",
            extra_metadata={"recap_bucket_end_at": bucket_end_at.isoformat()},
        )
        bundle = await self.recap_service.generate_bundle(bucket_end_at=bucket_end_at)
        self.repository.save_recap_bundle(bucket_end_at=bucket_end_at, bundle=bundle)
        self.repository.write_checkpoint(reason="recap")
        self.renderer.render_recap(when=bucket_end_at, bundle=bundle)

    async def _checkpoint_loop(self) -> None:
        interval = max(1, self.config.runtime.checkpoint_interval_seconds)
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
            except TimeoutError:
                self.repository.write_checkpoint(reason="heartbeat")

    def stop(self) -> None:
        self._stop_event.set()

    def _should_repair_turn(self, flags) -> bool:
        repairable = {"robotic-voice", "chat-register", "reveal-budget", "forbidden-knowledge"}
        return any(flag.flag_type in repairable for flag in flags)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                logger.debug("signal handlers unavailable for %s", sig)
