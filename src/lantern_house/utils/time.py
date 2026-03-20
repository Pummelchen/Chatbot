# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def floor_to_hour(value: datetime) -> datetime:
    return ensure_utc(value).replace(minute=0, second=0, microsecond=0)


def hours_ago(value: datetime, hours: int) -> datetime:
    return ensure_utc(value) - timedelta(hours=hours)


def isoformat(value: datetime) -> str:
    return ensure_utc(value).isoformat()
