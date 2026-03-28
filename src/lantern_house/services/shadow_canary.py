# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.context.assembler import ContextAssembler
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import AudienceControlReport, HotPatchCanaryRunSnapshot
from lantern_house.services.chronology_graph import ChronologyGraphService
from lantern_house.services.daily_life import DailyLifeSchedulerService
from lantern_house.services.guest_circulation import GuestCirculationService
from lantern_house.services.payoff_debt import PayoffDebtLedgerService
from lantern_house.services.season_planner import SeasonPlannerService
from lantern_house.services.viewer_signals import ViewerSignalIngestionService
from lantern_house.services.voice_fingerprints import VoiceFingerprintService
from lantern_house.services.world_tracking import WorldTrackingService
from lantern_house.utils.time import ensure_utc, utcnow


class ShadowCanaryService:
    def __init__(
        self,
        *,
        repository: StoryRepository,
        assembler: ContextAssembler,
        viewer_signal_service: ViewerSignalIngestionService,
        season_planner_service: SeasonPlannerService,
        world_tracking_service: WorldTrackingService,
        chronology_graph_service: ChronologyGraphService,
        voice_fingerprint_service: VoiceFingerprintService,
        guest_circulation_service: GuestCirculationService,
        daily_life_service: DailyLifeSchedulerService,
        payoff_debt_service: PayoffDebtLedgerService,
    ) -> None:
        self.repository = repository
        self.assembler = assembler
        self.viewer_signal_service = viewer_signal_service
        self.season_planner_service = season_planner_service
        self.world_tracking_service = world_tracking_service
        self.chronology_graph_service = chronology_graph_service
        self.voice_fingerprint_service = voice_fingerprint_service
        self.guest_circulation_service = guest_circulation_service
        self.daily_life_service = daily_life_service
        self.payoff_debt_service = payoff_debt_service

    def run(
        self,
        *,
        changed_files: list[str] | None = None,
        now=None,
    ) -> HotPatchCanaryRunSnapshot:
        now = ensure_utc(now or utcnow())
        checks: list[str] = []
        try:
            roster = self.repository.list_characters()
            if not roster:
                raise RuntimeError("Shadow canary requires a seeded character roster.")
            checks.append("seeded-roster-ok")

            self.viewer_signal_service.refresh_if_due(now=now, force=True)
            checks.append("viewer-signals-ok")

            self.season_planner_service.refresh(now=now, force=True)
            checks.append("season-planner-ok")

            self.world_tracking_service.refresh(now=now, force=True)
            checks.append("world-tracking-ok")

            self.chronology_graph_service.refresh(now=now, force=True)
            checks.append("chronology-graph-ok")

            self.voice_fingerprint_service.refresh(now=now, force=True)
            checks.append("voice-fingerprints-ok")

            self.guest_circulation_service.refresh(now=now, force=True)
            checks.append("guest-circulation-ok")

            self.daily_life_service.refresh(now=now, force=True)
            checks.append("daily-life-ok")

            self.payoff_debt_service.refresh(now=now, force=True)
            checks.append("payoff-debt-ok")

            manager_packet = self.assembler.build_manager_packet(
                audience_control=AudienceControlReport()
            )
            checks.append("manager-packet-ok")

            directive = {
                "objective": manager_packet.scene_objective,
                "per_character": {},
                "reveal_budget": 1,
                "active_character_slugs": [roster[0]["slug"]],
            }
            self.assembler.build_character_packet(roster[0]["slug"], directive)
            checks.append("character-packet-ok")

            snapshot = HotPatchCanaryRunSnapshot(
                status="passed",
                changed_files=changed_files or [],
                checks=checks,
                metadata={"scene_objective": manager_packet.scene_objective},
                created_at=now,
            )
            return self.repository.record_hot_patch_canary_run(snapshot=snapshot, now=now)
        except Exception as exc:
            snapshot = HotPatchCanaryRunSnapshot(
                status="failed",
                changed_files=changed_files or [],
                checks=checks,
                error_summary=str(exc),
                metadata={"failure_type": type(exc).__name__},
                created_at=now,
            )
            self.repository.record_hot_patch_canary_run(snapshot=snapshot, now=now)
            raise
