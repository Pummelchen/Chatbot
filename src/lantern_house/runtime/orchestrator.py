from __future__ import annotations

import asyncio
import logging
import signal

from lantern_house.config import AppConfig
from lantern_house.context.assembler import ContextAssembler
from lantern_house.db.repository import StoryRepository
from lantern_house.quality.pacing import ContinuityGuard
from lantern_house.rendering.terminal import TerminalRenderer
from lantern_house.runtime.recovery import RecoveryService
from lantern_house.runtime.scheduler import TurnScheduler
from lantern_house.services.character import CharacterService
from lantern_house.services.event_extractor import EventExtractor
from lantern_house.services.manager import StoryManagerService
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
        manager_service: StoryManagerService,
        character_service: CharacterService,
        recap_service: RecapService,
        scheduler: TurnScheduler,
        recovery_service: RecoveryService,
        event_extractor: EventExtractor,
        continuity_guard: ContinuityGuard,
        renderer: TerminalRenderer,
    ) -> None:
        self.config = config
        self.repository = repository
        self.assembler = assembler
        self.manager_service = manager_service
        self.character_service = character_service
        self.recap_service = recap_service
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

        self.repository.set_runtime_status("starting", degraded_mode=False)
        self.renderer.register_characters(self.repository.get_character_color_map())
        self._install_signal_handlers()

        try:
            recovery = self.recovery_service.recover()
            for bucket in recovery["missed_recap_hours"]:
                await self._emit_recap(bucket)

            while not self._stop_event.is_set():
                now = utcnow()
                if self.config.recaps.enabled:
                    for bucket in self.repository.list_missing_recap_hours(now=now):
                        await self._emit_recap(bucket)

                manager_packet = self.assembler.build_manager_packet()
                run_state = self.repository.get_run_state()
                directive = self.repository.get_latest_manager_directive()
                if self.scheduler.should_refresh_manager(
                    run_state=run_state,
                    directive=directive,
                    health=manager_packet.pacing_health,
                ):
                    directive_plan = await self.manager_service.plan(manager_packet, roster)
                    directive = self.repository.record_manager_directive(
                        directive_plan,
                        tick_no=run_state["last_tick_no"] + 1,
                        now=now,
                    )

                character_states = self.repository.list_character_states()
                speaker_slug = self.scheduler.select_speaker(directive=directive, character_states=character_states)
                packet = self.assembler.build_character_packet(speaker_slug, directive)
                thought_pulse_allowed = self.scheduler.allow_thought_pulse(
                    directive=directive,
                    speaker_slug=speaker_slug,
                    run_state=run_state,
                    recent_pulse_count=self.repository.count_recent_thought_pulses(hours=1),
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

                if once:
                    break

                await asyncio.sleep(self.scheduler.compute_delay_seconds(health=manager_packet.pacing_health))
        finally:
            self.repository.set_runtime_status("idle")

    async def _emit_recap(self, bucket_end_at) -> None:
        bundle = await self.recap_service.generate_bundle(bucket_end_at=bucket_end_at)
        self.repository.save_recap_bundle(bucket_end_at=bucket_end_at, bundle=bundle)
        self.renderer.render_recap(when=bucket_end_at, bundle=bundle)

    def stop(self) -> None:
        self._stop_event.set()

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                logger.debug("signal handlers unavailable for %s", sig)
