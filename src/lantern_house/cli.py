from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import typer
from alembic.config import Config as AlembicConfig

from alembic import command
from lantern_house.config import AppConfig, load_config
from lantern_house.context.assembler import ContextAssembler
from lantern_house.db.repository import StoryRepository
from lantern_house.db.session import SessionFactory, create_engine_from_config
from lantern_house.llm.ollama import OllamaClient
from lantern_house.logging import configure_logging
from lantern_house.quality.pacing import ContinuityGuard, PacingHealthEvaluator
from lantern_house.rendering.terminal import TerminalRenderer
from lantern_house.runtime.orchestrator import RuntimeOrchestrator
from lantern_house.runtime.recovery import RecoveryService
from lantern_house.runtime.scheduler import TurnScheduler
from lantern_house.services.audience import AudienceControlService
from lantern_house.services.beats import StoryBeatService
from lantern_house.services.character import CharacterService
from lantern_house.services.critic import TurnCriticService
from lantern_house.services.event_extractor import EventExtractor
from lantern_house.services.god_ai import GodAIService
from lantern_house.services.house import HousePressureService
from lantern_house.services.manager import StoryManagerService
from lantern_house.services.progression import StoryProgressionService
from lantern_house.services.recaps import RecapService
from lantern_house.services.seed_loader import StorySeedLoader
from lantern_house.services.simulation_lab import SimulationLabService
from lantern_house.utils.time import floor_to_hour, utcnow

app = typer.Typer(no_args_is_help=True)
ROOT = Path(__file__).resolve().parents[2]
logger = logging.getLogger(__name__)


def _load(config_path: str | None) -> AppConfig:
    return load_config(config_path)


@app.command()
def migrate(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    os.environ["LANTERN_HOUSE_DATABASE_URL"] = cfg.database.url
    alembic_cfg = AlembicConfig(str(ROOT / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")
    typer.echo("Migrations applied.")


@app.command()
def seed(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    engine = create_engine_from_config(cfg.database)
    session_factory = SessionFactory(engine)
    loader = StorySeedLoader(session_factory)
    loader.seed_database()
    typer.echo("Story bible seeded.")


@app.command()
def healthcheck(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    session_factory = SessionFactory(create_engine_from_config(cfg.database))
    session_factory.ping()
    asyncio.run(_ollama_healthcheck(cfg))
    typer.echo("Database and Ollama healthcheck passed.")


async def _ollama_healthcheck(config: AppConfig) -> None:
    client = OllamaClient(config.ollama)
    try:
        await client.healthcheck()
    finally:
        await client.close()


@app.command()
def recap_now(config: str | None = typer.Option(None, "--config")) -> None:
    cfg = _load(config)
    configure_logging(cfg.logging)
    asyncio.run(_recap_now(cfg))


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
    configure_logging(cfg.logging)
    asyncio.run(_run_async(cfg, once=once))


@app.command()
def simulate(
    config: str | None = typer.Option(None, "--config"),
    hours: int = typer.Option(24, "--hours", min=1, max=168),
    turns_per_hour: int = typer.Option(90, "--turns-per-hour", min=1, max=360),
) -> None:
    cfg = _load(config)
    configure_logging(cfg.logging)
    _simulate(cfg, hours=hours, turns_per_hour=turns_per_hour)


def _simulate(config: AppConfig, *, hours: int, turns_per_hour: int) -> None:
    engine = create_engine_from_config(config.database)
    session_factory = SessionFactory(engine)
    repository = StoryRepository(session_factory)
    if not repository.seed_exists():
        raise RuntimeError("No story seed found. Run `lantern-house seed` before `simulate`.")
    audience_service = AudienceControlService(config.audience, repository)
    beat_service = StoryBeatService(repository)
    house_pressure_service = HousePressureService(repository, config.house_pressure)
    house_pressure_service.refresh(force=True)
    audience = audience_service.refresh_if_due(force=True)
    beat_service.sync_audience_rollout(audience, now=utcnow())
    assembler = ContextAssembler(repository, PacingHealthEvaluator())
    packet = assembler.build_manager_packet(audience_control=audience)
    report = SimulationLabService(config.simulation).evaluate(
        packet,
        horizon_hours=hours,
        turns_per_hour=turns_per_hour,
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


async def _run_async(config: AppConfig, *, once: bool) -> None:
    engine = create_engine_from_config(config.database)
    session_factory = SessionFactory(engine)
    repository = StoryRepository(session_factory)
    client = OllamaClient(config.ollama)
    try:
        await client.ensure_models(
            [config.models.character, config.models.manager, config.models.announcer]
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
        beat_service = StoryBeatService(repository)
        simulation_lab = SimulationLabService(config.simulation)
        orchestrator = RuntimeOrchestrator(
            config=config,
            repository=repository,
            assembler=assembler,
            audience_control_service=audience_control_service,
            beat_service=beat_service,
            house_pressure_service=HousePressureService(repository, config.house_pressure),
            god_ai_service=GodAIService(
                config=god_ai_config,
                assembler=assembler,
                audience_control_service=audience_control_service,
                simulation_lab=simulation_lab,
                llm=client,
                model_name=config.models.god_ai,
            ),
            manager_service=StoryManagerService(client, config.models.manager, config.runtime),
            character_service=CharacterService(client, config.models.character),
            critic_service=TurnCriticService(config.critic),
            recap_service=RecapService(repository, client, config.models.announcer),
            progression_service=StoryProgressionService(),
            scheduler=TurnScheduler(
                runtime_config=config.runtime,
                timing_config=config.timing,
                thought_pulse_config=config.thought_pulses,
            ),
            recovery_service=RecoveryService(repository),
            event_extractor=EventExtractor(),
            continuity_guard=ContinuityGuard(),
            renderer=TerminalRenderer(),
        )
        await orchestrator.run(once=once)
    finally:
        await client.close()
