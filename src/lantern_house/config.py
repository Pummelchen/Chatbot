# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field


class DatabaseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    url: str = "mysql+pymysql://root:password@127.0.0.1:3306/lantern_house"
    echo: bool = False


class OllamaConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    base_url: str = "http://127.0.0.1:11434"
    request_timeout_seconds: int = 90
    keep_alive: str = "30m"
    auto_pull: bool = False
    warm_on_start: bool = True
    max_retries: int = 3


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    character: str = "gemma3:1b"
    manager: str = "gemma3:4b"
    announcer: str = "gemma3:4b"
    god_ai: str = "gemma3:12b"


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active_character_min: int = 2
    active_character_max: int = 4
    manager_step_interval_messages: int = 4
    manager_prefetch_threshold_messages: int = 2
    checkpoint_interval_seconds: int = 60
    periodic_flush_messages: int = 1
    degraded_mode_on_model_failure: bool = True
    healthcheck_interval_seconds: int = 60


class TimingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    min_delay_seconds: float = 1.0
    max_delay_seconds: float = 3.0
    burst_probability: float = 0.18
    burst_min_delay_seconds: float = 0.6
    burst_max_delay_seconds: float = 1.3
    lull_probability: float = 0.12
    lull_min_delay_seconds: float = 3.1
    lull_max_delay_seconds: float = 5.0


class ThoughtPulseConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    hourly_budget: int = 2
    cooldown_minutes: int = 20
    dramatic_threshold: int = 7


class RecapConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    windows: list[str] = Field(default_factory=lambda: ["1h", "12h", "24h"])


class StoryConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = "Lantern House"
    seed_file: str = "story_bible.yaml"
    default_location_slug: str = "front-desk"


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    level: str = "INFO"
    directory: str = "logs"
    file_name: str = "lantern_house.log"
    error_file_name: str = "error.txt"
    console_enabled: bool = False


class AudienceConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    update_file_path: str = "update.txt"
    check_interval_minutes: int = 10


class HousePressureConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    refresh_interval_minutes: int = 5
    max_active_signals: int = 4
    max_pending_beats: int = 4


class StoryGravityConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    refresh_interval_minutes: int = 10


class CriticConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    repair_threshold: int = 58
    hard_fail_threshold: int = 34


class GodAIConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    refresh_interval_minutes: int = 20
    max_brief_age_minutes: int = 90
    simulation_horizon_hours: int = 24
    simulation_turns_per_hour: int = 90


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default_horizon_hours: int = 24
    default_turns_per_hour: int = 90


class FailSafeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    base_retry_delay_seconds: int = 2
    max_retry_delay_seconds: int = 300
    max_consecutive_failures_before_pause: int = 2
    keep_last_good_value: bool = True
    unexpected_iteration_delay_seconds: int = 3


class HotPatchConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    check_interval_seconds: int = 15
    watch_paths: list[str] = Field(
        default_factory=lambda: [
            "src/lantern_house",
            "config.example.toml",
            "update.txt",
        ]
    )
    watch_extensions: list[str] = Field(
        default_factory=lambda: [".py", ".md", ".toml", ".yaml", ".yml", ".txt"]
    )


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    models: ModelConfig = Field(default_factory=ModelConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    timing: TimingConfig = Field(default_factory=TimingConfig)
    thought_pulses: ThoughtPulseConfig = Field(default_factory=ThoughtPulseConfig)
    recaps: RecapConfig = Field(default_factory=RecapConfig)
    story: StoryConfig = Field(default_factory=StoryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    audience: AudienceConfig = Field(default_factory=AudienceConfig)
    house_pressure: HousePressureConfig = Field(default_factory=HousePressureConfig)
    story_gravity: StoryGravityConfig = Field(default_factory=StoryGravityConfig)
    critic: CriticConfig = Field(default_factory=CriticConfig)
    god_ai: GodAIConfig = Field(default_factory=GodAIConfig)
    simulation: SimulationConfig = Field(default_factory=SimulationConfig)
    failsafe: FailSafeConfig = Field(default_factory=FailSafeConfig)
    hot_patch: HotPatchConfig = Field(default_factory=HotPatchConfig)
    loaded_from: str | None = Field(default=None, exclude=True)
    config_root: str | None = Field(default=None, exclude=True)


def load_config(config_path: str | Path | None = None) -> AppConfig:
    load_dotenv()

    resolved_path = Path(
        config_path or os.getenv("LANTERN_HOUSE_CONFIG_PATH", "config.example.toml")
    ).expanduser()
    if not resolved_path.is_absolute():
        resolved_path = (Path.cwd() / resolved_path).resolve()
    payload: dict[str, Any] = {}
    if resolved_path.exists():
        payload = tomllib.loads(resolved_path.read_text(encoding="utf-8"))

    env_overrides = {
        "database": {"url": os.getenv("LANTERN_HOUSE_DATABASE_URL")},
        "ollama": {"base_url": os.getenv("LANTERN_HOUSE_OLLAMA_BASE_URL")},
        "logging": {"level": os.getenv("LANTERN_HOUSE_LOG_LEVEL")},
    }

    merged = _deep_merge(payload, env_overrides)
    config = AppConfig.model_validate(merged)
    base_dir = resolved_path.parent
    story_seed_file = config.story.seed_file
    if _looks_like_path(story_seed_file):
        story_seed_file = str(_resolve_runtime_path(base_dir, story_seed_file))
    return config.model_copy(
        update={
            "logging": config.logging.model_copy(
                update={
                    "directory": str(
                        _resolve_runtime_path(base_dir, config.logging.directory)
                    )
                }
            ),
            "audience": config.audience.model_copy(
                update={
                    "update_file_path": str(
                        _resolve_runtime_path(base_dir, config.audience.update_file_path)
                    )
                }
            ),
            "story": config.story.model_copy(update={"seed_file": story_seed_file}),
            "loaded_from": str(resolved_path),
            "config_root": str(base_dir),
        }
    )


def build_hot_patch_config(config: AppConfig) -> HotPatchConfig:
    watch_paths = list(config.hot_patch.watch_paths)
    extras = [
        config.loaded_from,
        config.audience.update_file_path,
        str(Path(config.config_root) / ".env") if config.config_root else None,
    ]
    for item in extras:
        if not item:
            continue
        if item not in watch_paths:
            watch_paths.append(item)
    return config.hot_patch.model_copy(update={"watch_paths": watch_paths})


def _deep_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
            continue
        if isinstance(value, dict):
            merged[key] = {k: v for k, v in value.items() if v is not None}
            continue
        merged[key] = value
    return merged


def _resolve_runtime_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _looks_like_path(value: str) -> bool:
    return any(token in value for token in ("/", "\\")) or value.startswith(".")
