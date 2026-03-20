from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utcnow() -> datetime:
    return datetime.now(UTC)


def floor_to_hour(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def hours_ago(value: datetime, hours: int) -> datetime:
    return value - timedelta(hours=hours)


def isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()

