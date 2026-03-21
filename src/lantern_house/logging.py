# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from lantern_house.config import LoggingConfig


class JsonErrorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in (
            "operation",
            "recoverable",
            "expected_inputs",
            "retry_advice",
            "context",
            "failure_streak",
            "next_retry_at",
            "fallback_used",
            "exception_type",
            "traceback_excerpt",
        ):
            value = getattr(record, key, None)
            if value not in (None, [], {}, ""):
                payload[key] = value
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(config: LoggingConfig) -> None:
    log_dir = Path(config.directory)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / config.file_name
    error_path = log_dir / config.error_file_name

    root = logging.getLogger()
    root.setLevel(config.level.upper())
    root.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    error_handler = RotatingFileHandler(
        error_path,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(JsonErrorFormatter())
    root.addHandler(error_handler)

    if config.console_enabled:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
