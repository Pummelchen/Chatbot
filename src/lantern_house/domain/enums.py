# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from enum import StrEnum


class MessageKind(StrEnum):
    CHAT = "chat"
    ANNOUNCE = "announce"
    RECAP = "recap"


class SummaryWindow(StrEnum):
    ONE_HOUR = "1h"
    TWELVE_HOURS = "12h"
    TWENTY_FOUR_HOURS = "24h"


class ArcStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    DORMANT = "dormant"
    RESOLVED = "resolved"


class FlagSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EventType(StrEnum):
    CLUE = "clue"
    RELATIONSHIP = "relationship"
    REVEAL = "reveal"
    QUESTION = "question"
    HUMOR = "humor"
    FINANCIAL = "financial"
    THREAT = "threat"
    ROMANCE = "romance"
    ROUTINE = "routine"
    CONFLICT = "conflict"
    ALLIANCE = "alliance"
