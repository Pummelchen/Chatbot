# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from lantern_house.config import VoiceFingerprintConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import VoiceFingerprintSnapshot
from lantern_house.utils.time import ensure_utc, utcnow

_GENERIC_TABOO_MARKERS = [
    "the truth is",
    "this changes everything",
    "we both know",
    "you do not understand",
]


class VoiceFingerprintService:
    def __init__(self, repository: StoryRepository, config: VoiceFingerprintConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None, force: bool = False) -> list[VoiceFingerprintSnapshot]:
        now = ensure_utc(now or utcnow())
        existing = self.repository.list_voice_fingerprints(limit=1)
        if (
            not force
            and not self.config.enabled
            and existing
        ):
            return self.repository.list_voice_fingerprints(limit=12)
        if (
            not force
            and existing
            and existing[0].updated_at
            and now - ensure_utc(existing[0].updated_at)
            < timedelta(minutes=max(1, self.config.refresh_interval_minutes))
        ):
            return self.repository.list_voice_fingerprints(limit=12)

        fingerprints: list[VoiceFingerprintSnapshot] = []
        for character in self.repository.list_characters():
            recent_messages = self.repository.list_recent_messages(
                limit=self.config.recent_messages_per_character,
                speaker_slugs=[character["slug"]],
            )
            lexical_markers = _lexical_markers(
                base_texts=[
                    character.get("public_persona", ""),
                    character.get("message_style", ""),
                    character.get("conflict_style", ""),
                    character.get("humor_style", ""),
                    *(item.content for item in recent_messages),
                ],
                limit=self.config.lexical_marker_count,
            )
            fingerprints.append(
                VoiceFingerprintSnapshot(
                    character_slug=character["slug"],
                    signature_line=_signature_line(character, lexical_markers),
                    cadence_profile=_cadence_profile(
                        message_style=character.get("message_style", ""),
                        recent_messages=[item.content for item in recent_messages],
                    ),
                    conflict_tone=_short_phrase(character.get("conflict_style", "")),
                    affection_tone=_short_phrase(character.get("emotional_expression", "")),
                    humor_markers=_marker_list(character.get("humor_style", ""), limit=3),
                    lexical_markers=lexical_markers,
                    taboo_markers=[*_GENERIC_TABOO_MARKERS],
                    metadata={
                        "message_style": character.get("message_style", ""),
                        "humor_style": character.get("humor_style", ""),
                    },
                    updated_at=now,
                )
            )
        return self.repository.save_voice_fingerprints(fingerprints=fingerprints, now=now)


def _signature_line(character: dict[str, str], lexical_markers: list[str]) -> str:
    lead = character["full_name"].split()[0]
    cadence = _cadence_profile(
        message_style=character.get("message_style", ""),
        recent_messages=[],
    )
    lexicon = ", ".join(lexical_markers[:3]) or "concrete pressure"
    return (
        f"{lead} should sound {cadence}, shaped by "
        f"{character.get('conflict_style', 'guarded pressure')}, "
        f"with recurring concrete language like {lexicon}."
    )


def _cadence_profile(*, message_style: str, recent_messages: list[str]) -> str:
    lowered = message_style.lower()
    if "clipped" in lowered or "controlled" in lowered or "composed" in lowered:
        return "clipped"
    if "fast" in lowered or "rapid" in lowered or "reactive" in lowered:
        return "rapid"
    if "quiet" in lowered or "restrained" in lowered or "measured" in lowered:
        return "measured"
    if recent_messages:
        average_words = sum(len(item.split()) for item in recent_messages) / len(recent_messages)
        if average_words <= 10:
            return "clipped"
        if average_words >= 20:
            return "flowing"
    return "balanced"


def _marker_list(text: str, *, limit: int) -> list[str]:
    markers = [part.strip().lower() for part in re.split(r"[,.;/]", text) if part.strip()]
    return markers[:limit]


def _short_phrase(text: str) -> str:
    compact = " ".join(text.split())
    return compact[:120]


def _lexical_markers(*, base_texts: list[str], limit: int) -> list[str]:
    counts: Counter[str] = Counter()
    for text in base_texts:
        for token in re.findall(r"[a-z]{4,}", text.lower()):
            if token in {
                "that",
                "with",
                "have",
                "from",
                "this",
                "will",
                "your",
                "about",
                "into",
                "they",
                "them",
                "want",
                "keep",
            }:
                continue
            counts[token] += 1
    return [token for token, _count in counts.most_common(limit)]
