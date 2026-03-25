# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path

import typer
from alembic.config import Config as AlembicConfig

from alembic import command
from lantern_house.config import AppConfig, build_hot_patch_config, load_config
from lantern_house.context.assembler import ContextAssembler
from lantern_house.db.repository import StoryRepository
from lantern_house.db.session import SessionFactory, create_engine_from_config
from lantern_house.llm.ollama import OllamaClient
from lantern_house.logging import configure_logging
from lantern_house.quality.pacing import ContinuityGuard, PacingHealthEvaluator
from lantern_house.rendering.terminal import TerminalRenderer
from lantern_house.runtime.failsafe import FailSafeExecutor, log_call_failure
from lantern_house.runtime.hotpatch import HotPatchController
from lantern_house.runtime.orchestrator import RuntimeOrchestrator
from lantern_house.runtime.recovery import RecoveryService
from lantern_house.runtime.scheduler import TurnScheduler
from lantern_house.services.audience import AudienceControlService
from lantern_house.services.beats import StoryBeatService
from lantern_house.services.broadcast_assets import BroadcastAssetService
from lantern_house.services.canon import CanonDistillationService
from lantern_house.services.canon_court import CanonCourtService
from lantern_house.services.character import CharacterService
from lantern_house.services.critic import TurnCriticService
from lantern_house.services.event_extractor import EventExtractor
from lantern_house.services.god_ai import GodAIService
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
from lantern_house.services.seed_loader import StorySeedLoader
from lantern_house.services.simulation_lab import SimulationLabService
from lantern_house.services.soak_audit import SoakAuditService
from lantern_house.services.story_gravity import StoryGravityService
from lantern_house.services.turn_selection import TurnSelectionService
from lantern_house.services.viewer_signals import ViewerSignalIngestionService
from lantern_house.services.world_tracking import WorldTrackingService
from lantern_house.utils.time import floor_to_hour, utcnow

app = typer.Typer(no_args_is_help=True)
ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def _load(config_path: str | None) -> AppConfig:
    return load_config(config_path)


@app.command()
def migrate(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    _run_cli_command(
        "migrate",
        cfg,
        lambda: _migrate(cfg),
        expected_inputs=[
            "A reachable MySQL database URL in config or .env.",
            "A readable alembic.ini and migration directory.",
        ],
        retry_advice="Fix the database or migration configuration and rerun migrate.",
    )


@app.command()
def seed(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    _run_cli_command(
        "seed",
        cfg,
        lambda: _seed(cfg),
        expected_inputs=[
            "A migrated MySQL database.",
            "A valid packaged or local story seed YAML file.",
        ],
        retry_advice="Run migrate first or repair story.seed_file and rerun seed.",
    )


@app.command()
def healthcheck(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    _run_cli_command(
        "healthcheck",
        cfg,
        lambda: _healthcheck(cfg),
        expected_inputs=[
            "A reachable MySQL database URL in config or .env.",
            "A reachable Ollama endpoint with the configured base URL.",
        ],
        retry_advice="Repair the database or Ollama connection details and try again.",
    )


async def _ollama_healthcheck(config: AppConfig) -> None:
    client = OllamaClient(config.ollama)
    try:
        await client.healthcheck()
    finally:
        await client.close()


@app.command()
def recap_now(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    _run_cli_command(
        "recap-now",
        cfg,
        lambda: asyncio.run(_recap_now(cfg)),
        expected_inputs=[
            "A seeded database with stored events.",
            "A reachable announcer model in Ollama.",
        ],
        retry_advice="Seed the project and restore Ollama availability before retrying.",
        configure_logs_first=True,
    )


async def _recap_now(config: AppConfig) -> None:
    engine = create_engine_from_config(config.database)
    session_factory = SessionFactory(engine)
    repository = StoryRepository(session_factory)
    client = OllamaClient(config.ollama)
    try:
        recap_service = RecapService(repository, client, config.models.announcer)
        bucket = floor_to_hour(utcnow())
        bundle = await recap_service.generate_bundle(bucket_end_at=bucket)
        repository.save_recap_bundle(bucket_end_at=bucket, bundle=bundle)
        TerminalRenderer().render_recap(when=bucket, bundle=bundle)
    finally:
        await client.close()


@app.command()
def run(
    config: str | None = typer.Option(None, "--config"),
    once: bool = typer.Option(False, "--once", help="Generate a single turn and exit."),
) -> None:
    cfg = _load(config)
    _run_cli_command(
        "run",
        cfg,
        lambda: asyncio.run(_run_async(cfg, once=once)),
        expected_inputs=[
            "A migrated and seeded database.",
            "Reachable configured Ollama models.",
            "Readable runtime files such as the config and update.txt.",
        ],
        retry_advice="Repair the failing dependency and rerun the live runtime.",
        configure_logs_first=True,
    )


@app.command()
def simulate(
    config: str | None = typer.Option(None, "--config"),
    hours: int = typer.Option(24, "--hours", min=1, max=168),
    turns_per_hour: int = typer.Option(90, "--turns-per-hour", min=1, max=360),
) -> None:
    cfg = _load(config)
    _run_cli_command(
        "simulate",
        cfg,
        lambda: _simulate(cfg, hours=hours, turns_per_hour=turns_per_hour),
        expected_inputs=[
            "A migrated and seeded database.",
            "A readable strategy-ready story state.",
        ],
        retry_advice="Seed the database and restore strategy inputs before simulating.",
        configure_logs_first=True,
    )


@app.command()
def soak_audit(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    _run_cli_command(
        "soak-audit",
        cfg,
        lambda: _soak_audit(cfg),
        expected_inputs=[
            "A migrated and seeded database.",
            "Readable strategy state for the manager packet and simulation lab.",
        ],
        retry_advice="Seed the database and restore strategy inputs before running soak audit.",
        configure_logs_first=True,
    )


@app.command()
def dashboard(
    config: str | None = typer.Option(None, "--config"),
    watch: bool = typer.Option(False, "--watch", help="Refresh dashboard output every 5 seconds."),
) -> None:
    cfg = _load(config)
    _run_cli_command(
        "dashboard",
        cfg,
        lambda: _dashboard(cfg, watch=watch),
        expected_inputs=[
            "A migrated database with run_state and telemetry tables.",
        ],
        retry_advice="Run migrate and let the runtime produce telemetry before using dashboard.",
        configure_logs_first=True,
    )


@app.command("broadcast-assets")
def broadcast_assets(
    config: str | None = typer.Option(None, "--config"),
    limit: int = typer.Option(5, "--limit", min=1, max=20),
) -> None:
    cfg = _load(config)
    _run_cli_command(
        "broadcast-assets",
        cfg,
        lambda: _broadcast_assets(cfg, limit=limit),
        expected_inputs=[
            "A migrated database with broadcast_asset_packages "
            "or a live runtime that has generated them.",
        ],
        retry_advice="Run migrations and let the runtime produce asset packages before retrying.",
        configure_logs_first=True,
    )


def _migrate(config: AppConfig) -> None:
    os.environ["LANTERN_HOUSE_DATABASE_URL"] = config.database.url
    alembic_cfg = AlembicConfig(str(ROOT / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    typer.echo("Migrations applied.")


def _seed(config: AppConfig) -> None:
    engine = create_engine_from_config(config.database)
    session_factory = SessionFactory(engine)
    loader = StorySeedLoader(session_factory, seed_file=config.story.seed_file)
    loader.seed_database()
    typer.echo("Story bible seeded.")


def _healthcheck(config: AppConfig) -> None:
    session_factory = SessionFactory(create_engine_from_config(config.database))
    session_factory.ping()
    asyncio.run(_ollama_healthcheck(config))
    typer.echo("Database and Ollama healthcheck passed.")


def _simulate(config: AppConfig, *, hours: int, turns_per_hour: int) -> None:
    engine = create_engine_from_config(config.database)
    session_factory = SessionFactory(engine)
    repository = StoryRepository(session_factory)
    if not repository.seed_exists():
        raise RuntimeError("No story seed found. Run `lantern-house seed` before `simulate`.")
    audience_service = AudienceControlService(config.audience, repository)
    viewer_signal_service = ViewerSignalIngestionService(config.viewer_signals, repository)
    beat_service = StoryBeatService(repository)
    house_pressure_service = HousePressureService(repository, config.house_pressure)
    house_pressure_service.refresh(force=True)
    StoryGravityService(repository, config.story_gravity).refresh(force=True)
    ProgrammingGridService(repository, config.programming_grid).refresh(force=True)
    SeasonPlannerService(repository, config.season_planner).refresh(force=True)
    viewer_signal_service.refresh_if_due(force=True)
    audience = audience_service.refresh_if_due(force=True)
    beat_service.sync_audience_rollout(audience, now=utcnow())
    WorldTrackingService(repository, config.world_tracking).refresh(force=True)
    assembler = ContextAssembler(repository, PacingHealthEvaluator())
    packet = assembler.build_manager_packet(audience_control=audience)
    report = SimulationLabService(config.simulation).evaluate(
        packet,
        horizon_hours=hours,
        turns_per_hour=turns_per_hour,
    )
    report = repository.record_simulation_lab_run(
        report=report,
        source="cli-simulate",
        now=utcnow(),
    )
    typer.echo(f"Simulation horizon: {report.horizon_hours}h @ {report.turns_per_hour} turns/hour")
    for candidate in report.candidates:
        typer.echo(f"- {candidate.strategy_key}: {candidate.score}")
        typer.echo(f"  next hour: {candidate.next_hour_focus}")
        typer.echo(f"  six hours: {candidate.six_hour_path}")
    if report.systemic_risks:
        typer.echo("Risks:")
        for risk in report.systemic_risks:
            typer.echo(f"- {risk}")


def _soak_audit(config: AppConfig) -> None:
    engine = create_engine_from_config(config.database)
    session_factory = SessionFactory(engine)
    repository = StoryRepository(session_factory)
    if not repository.seed_exists():
        raise RuntimeError("No story seed found. Run `lantern-house seed` before `soak-audit`.")
    audience_service = AudienceControlService(config.audience, repository)
    viewer_signal_service = ViewerSignalIngestionService(config.viewer_signals, repository)
    beat_service = StoryBeatService(repository)
    beat_service.sync_audience_rollout(audience_service.refresh_if_due(force=True), now=utcnow())
    viewer_signal_service.refresh_if_due(force=True)
    house_pressure_service = HousePressureService(repository, config.house_pressure)
    house_pressure_service.refresh(force=True)
    StoryGravityService(repository, config.story_gravity).refresh(force=True)
    HourlyBeatLedgerService(repository, config.hourly_beat_ledger).refresh(now=utcnow())
    ProgrammingGridService(repository, config.programming_grid).refresh(force=True)
    SeasonPlannerService(repository, config.season_planner).refresh(force=True)
    CanonDistillationService(repository, config.canon).refresh(now=utcnow())
    WorldTrackingService(repository, config.world_tracking).refresh(force=True)
    assembler = ContextAssembler(repository, PacingHealthEvaluator())
    packet = assembler.build_manager_packet(audience_control=audience_service.current_report())
    simulation_lab = SimulationLabService(config.simulation)
    snapshot = SoakAuditService(repository, simulation_lab, config.soak_audit).refresh_if_due(
        packet,
        now=utcnow(),
        force=True,
    )
    if snapshot is None:
        raise RuntimeError("Soak audit did not produce a result.")
    typer.echo(f"Soak audit direction: {snapshot.recommended_direction}")
    typer.echo(
        "Risks: "
        f"progression={snapshot.progression_miss_risk}, "
        f"drift={snapshot.drift_risk}, "
        f"strategy_lock={snapshot.strategy_lock_risk}, "
        f"recap_decay={snapshot.recap_decay_risk}, "
        f"clip_drought={snapshot.clip_drought_risk}, "
        f"ship_stagnation={snapshot.ship_stagnation_risk}, "
        f"unresolved_overload={snapshot.unresolved_overload_risk}"
    )
    for note in snapshot.audit_notes:
        typer.echo(f"- {note}")


def _dashboard(config: AppConfig, *, watch: bool) -> None:
    engine = create_engine_from_config(config.database)
    session_factory = SessionFactory(engine)
    repository = StoryRepository(session_factory)
    service = OpsDashboardService(repository, config.ops_dashboard)

    def emit() -> None:
        typer.echo(service.render_text())

    if not watch:
        emit()
        return
    try:
        while True:
            emit()
            typer.echo("")
            time.sleep(5)
    except KeyboardInterrupt:
        raise typer.Exit(code=0) from None


def _broadcast_assets(config: AppConfig, *, limit: int) -> None:
    engine = create_engine_from_config(config.database)
    repository = StoryRepository(SessionFactory(engine))
    packages = repository.list_recent_broadcast_assets(limit=limit)
    if not packages:
        typer.echo("No broadcast assets recorded yet.")
        return
    for item in packages:
        typer.echo(f"{item.asset_title} [{item.asset_score}]")
        typer.echo(f"  hook: {item.hook_line}")
        typer.echo(f"  why: {item.why_it_matters}")
        if item.clip_manifest:
            clip = item.clip_manifest[0]
            typer.echo(
                f"  clip: {clip.get('start_seconds', 0)}-{clip.get('end_seconds', 0)}s | "
                f"{clip.get('angle', 'reentry')}"
            )


async def _run_async(config: AppConfig, *, once: bool) -> None:
    engine = create_engine_from_config(config.database)
    session_factory = SessionFactory(engine)
    repository = StoryRepository(session_factory)
    client = OllamaClient(config.ollama)
    try:
        await client.ensure_models(
            [
                config.models.character,
                config.models.repair,
                config.models.manager,
                config.models.announcer,
            ]
        )
        god_ai_config = config.god_ai
        if god_ai_config.enabled:
            try:
                await client.ensure_models([config.models.god_ai])
            except Exception as exc:
                logger.warning("god-ai model unavailable, disabling background planner: %s", exc)
                god_ai_config = config.god_ai.model_copy(update={"enabled": False})
        pacing = PacingHealthEvaluator()
        assembler = ContextAssembler(repository, pacing)
        audience_control_service = AudienceControlService(config.audience, repository)
        viewer_signal_service = ViewerSignalIngestionService(config.viewer_signals, repository)
        beat_service = StoryBeatService(repository)
        hourly_ledger_service = HourlyBeatLedgerService(repository, config.hourly_beat_ledger)
        programming_grid_service = ProgrammingGridService(repository, config.programming_grid)
        season_planner_service = SeasonPlannerService(repository, config.season_planner)
        canon_service = CanonDistillationService(repository, config.canon)
        simulation_lab = SimulationLabService(config.simulation)
        soak_audit_service = SoakAuditService(repository, simulation_lab, config.soak_audit)
        orchestrator = RuntimeOrchestrator(
            config=config,
            repository=repository,
            assembler=assembler,
            audience_control_service=audience_control_service,
            viewer_signal_service=viewer_signal_service,
            beat_service=beat_service,
            hourly_ledger_service=hourly_ledger_service,
            programming_grid_service=programming_grid_service,
            season_planner_service=season_planner_service,
            canon_service=canon_service,
            canon_court_service=CanonCourtService(config.canon_court),
            house_pressure_service=HousePressureService(repository, config.house_pressure),
            world_tracking_service=WorldTrackingService(repository, config.world_tracking),
            story_gravity_service=StoryGravityService(repository, config.story_gravity),
            god_ai_service=GodAIService(
                config=god_ai_config,
                assembler=assembler,
                audience_control_service=audience_control_service,
                simulation_lab=simulation_lab,
                soak_audit_service=soak_audit_service,
                llm=client,
                model_name=config.models.god_ai,
            ),
            manager_service=StoryManagerService(client, config.models.manager, config.runtime),
            character_service=CharacterService(
                client,
                config.models.character,
                config.models.repair,
            ),
            turn_selection_service=TurnSelectionService(config.turn_selection),
            critic_service=TurnCriticService(config.critic),
            highlight_service=HighlightPackagingService(repository, config.highlights),
            monetization_service=MonetizationPackagingService(repository, config.monetization),
            broadcast_asset_service=BroadcastAssetService(
                repository,
                config.broadcast_assets,
            ),
            recap_service=RecapService(repository, client, config.models.announcer),
            progression_service=StoryProgressionService(),
            load_orchestration_service=LoadOrchestrationService(
                repository,
                config.load_orchestration,
            ),
            ops_dashboard_service=OpsDashboardService(repository, config.ops_dashboard),
            scheduler=TurnScheduler(
                runtime_config=config.runtime,
                timing_config=config.timing,
                thought_pulse_config=config.thought_pulses,
            ),
            recovery_service=RecoveryService(repository),
            event_extractor=EventExtractor(),
            continuity_guard=ContinuityGuard(),
            renderer=TerminalRenderer(),
            llm_client=client,
            fail_safe_executor=FailSafeExecutor(config.failsafe),
        )
        orchestrator.attach_hot_patch_controller(
            HotPatchController(
                config=build_hot_patch_config(config),
                project_root=ROOT,
                rebuild_runtime=orchestrator.rebuild_runtime_components,
            )
        )
        await orchestrator.run(once=once)
    finally:
        await client.close()


def _run_cli_command(
    command_name: str,
    config: AppConfig,
    operation: Callable[[], None],
    *,
    expected_inputs: list[str],
    retry_advice: str,
    configure_logs_first: bool = False,
) -> None:
    if configure_logs_first:
        configure_logging(config.logging)
    try:
        operation()
    except Exception as exc:
        configure_logging(config.logging)
        log_call_failure(
            f"cli.{command_name}",
            exc,
            context={"config_path": config.loaded_from},
            expected_inputs=expected_inputs,
            retry_advice=retry_advice,
        )
        typer.secho(
            _format_cli_error(
                command_name=command_name,
                error=exc,
                expected_inputs=expected_inputs,
                retry_advice=retry_advice,
            ),
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1) from exc


def _format_cli_error(
    *,
    command_name: str,
    error: Exception,
    expected_inputs: list[str],
    retry_advice: str,
) -> str:
    parts = [f"{command_name} failed: {error}"]
    if expected_inputs:
        parts.append("Expected: " + "; ".join(expected_inputs))
    if retry_advice:
        parts.append("Retry: " + retry_advice)
    return "\n".join(parts)
