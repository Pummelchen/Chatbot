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


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active_character_min: int = 2
    active_character_max: int = 4
    manager_step_interval_messages: int = 4
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


def load_config(config_path: str | Path | None = None) -> AppConfig:
    load_dotenv()

    resolved_path = Path(
        config_path or os.getenv("LANTERN_HOUSE_CONFIG_PATH", "config.example.toml")
    )
    payload: dict[str, Any] = {}
    if resolved_path.exists():
        payload = tomllib.loads(resolved_path.read_text(encoding="utf-8"))

    env_overrides = {
        "database": {"url": os.getenv("LANTERN_HOUSE_DATABASE_URL")},
        "ollama": {"base_url": os.getenv("LANTERN_HOUSE_OLLAMA_BASE_URL")},
        "logging": {"level": os.getenv("LANTERN_HOUSE_LOG_LEVEL")},
    }

    merged = _deep_merge(payload, env_overrides)
    return AppConfig.model_validate(merged)


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
