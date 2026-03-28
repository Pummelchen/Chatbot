# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lantern_house.config import ViewerSignalsConfig, YouTubeAdapterConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import YouTubeAdapterStateSnapshot
from lantern_house.runtime.failsafe import AdaptiveServiceError
from lantern_house.utils.time import ensure_utc, utcnow

_STOP_WORDS = {
    "the",
    "and",
    "that",
    "with",
    "this",
    "from",
    "have",
    "they",
    "what",
    "your",
    "just",
    "about",
    "there",
    "would",
    "should",
    "their",
    "because",
    "really",
    "maybe",
    "please",
}


@dataclass(slots=True)
class YouTubeHarvestBundle:
    state: YouTubeAdapterStateSnapshot
    comments: list[dict[str, Any]]
    clips: list[dict[str, Any]]
    retention: list[dict[str, Any]]
    live_chat: list[dict[str, Any]]


class YouTubeSignalAdapterService:
    def __init__(
        self,
        config: YouTubeAdapterConfig,
        viewer_config: ViewerSignalsConfig,
        repository: StoryRepository,
    ) -> None:
        self.config = config
        self.viewer_config = viewer_config
        self.repository = repository
        self.harvest_directory = Path(viewer_config.harvest_directory_path)
        self.file_names = {
            "comments": viewer_config.comments_file_name,
            "clips": viewer_config.clips_file_name,
            "retention": viewer_config.retention_file_name,
            "live_chat": viewer_config.live_chat_file_name,
        }

    def harvest(self, *, now=None, force: bool = False) -> YouTubeHarvestBundle:
        now = ensure_utc(now or utcnow())
        previous = self.repository.get_youtube_adapter_state()
        if not self.config.enabled and not force:
            return YouTubeHarvestBundle(previous, [], [], [], [])
        if not self.harvest_directory.exists():
            return YouTubeHarvestBundle(previous, [], [], [], [])

        source_offsets = dict(previous.source_offsets)
        comments = self._read_delta("comments", source_offsets)
        clips = self._read_delta("clips", source_offsets)
        retention = self._read_delta("retention", source_offsets)
        live_chat = self._read_delta("live_chat", source_offsets)
        state = YouTubeAdapterStateSnapshot(
            state_key="primary",
            last_harvest_at=now,
            source_offsets=source_offsets,
            normalized_counts={
                "comments": len(comments),
                "clips": len(clips),
                "retention": len(retention),
                "live_chat": len(live_chat),
            },
            active_themes=self._themes(comments, live_chat),
            ship_heat=self._ship_heat(comments, live_chat),
            theory_heat=self._theory_heat(comments, live_chat),
            retention_alerts=self._retention_alerts(retention),
            clip_spikes=self._clip_spikes(clips),
            metadata={
                "harvest_directory": str(self.harvest_directory),
                "forced": force,
            },
            updated_at=now,
        )
        persisted = self.repository.save_youtube_adapter_state(snapshot=state, now=now)
        return YouTubeHarvestBundle(persisted, comments, clips, retention, live_chat)

    def _read_delta(self, source_key: str, source_offsets: dict[str, int]) -> list[dict[str, Any]]:
        path = self.harvest_directory / self.file_names[source_key]
        if not path.exists():
            source_offsets[source_key] = 0
            return []
        raw_lines = path.read_text(encoding="utf-8").splitlines()
        previous_offset = int(source_offsets.get(source_key, 0))
        if previous_offset > len(raw_lines):
            previous_offset = 0
        delta_lines = raw_lines[
            previous_offset : previous_offset + self.config.max_records_per_file
        ]
        source_offsets[source_key] = previous_offset + len(delta_lines)
        parsed: list[dict[str, Any]] = []
        for line_number, raw_line in enumerate(delta_lines, start=previous_offset + 1):
            cleaned = raw_line.strip()
            if not cleaned:
                continue
            try:
                payload = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                raise AdaptiveServiceError(
                    f"Malformed JSONL in {path.name}",
                    expected_inputs=["One JSON object per line in the harvested YouTube files."],
                    retry_advice="Fix the malformed line and retry harvesting.",
                    context={"path": str(path), "line_number": line_number},
                ) from exc
            if not isinstance(payload, dict):
                continue
            parsed.append(payload)
        return parsed

    def _themes(self, comments: list[dict[str, Any]], live_chat: list[dict[str, Any]]) -> list[str]:
        texts = [self._text(record) for record in [*comments, *live_chat]]
        counter: Counter[str] = Counter()
        for text in texts:
            for token in re.findall(r"[a-z]{4,}", text.lower()):
                if token in _STOP_WORDS:
                    continue
                counter[token] += 1
        return [token for token, _count in counter.most_common(self.config.max_theme_items)]

    def _ship_heat(
        self,
        comments: list[dict[str, Any]],
        live_chat: list[dict[str, Any]],
    ) -> list[str]:
        patterns = Counter[str]()
        texts = [self._text(record) for record in [*comments, *live_chat]]
        for text in texts:
            lowered = text.lower()
            matches = re.findall(r"([a-z]+)\s*(?:/|x|and|&)\s*([a-z]+)", lowered)
            for left, right in matches:
                if left == right or len(left) < 3 or len(right) < 3:
                    continue
                pair = " / ".join(sorted((left, right)))
                patterns[pair] += 1
        return [f"{pair} ({count})" for pair, count in patterns.most_common(4)]

    def _theory_heat(
        self, comments: list[dict[str, Any]], live_chat: list[dict[str, Any]]
    ) -> list[str]:
        counter: Counter[str] = Counter()
        for record in [*comments, *live_chat]:
            text = self._text(record).lower()
            if not any(
                token in text for token in ("theory", "suspect", "maybe", "what if", "think")
            ):
                continue
            summary = " ".join(text.split())[:90]
            if summary:
                counter[summary] += 1
        return [f"{summary} ({count})" for summary, count in counter.most_common(4)]

    def _retention_alerts(self, retention: list[dict[str, Any]]) -> list[str]:
        alerts: list[str] = []
        for item in retention[-self.config.max_theme_items :]:
            drop = _int_value(item.get("drop_percent"))
            minute = _int_value(item.get("minute"))
            if drop < self.config.retention_drop_threshold:
                continue
            reason = str(item.get("reason") or "unknown cause").strip()
            alerts.append(f"minute {minute}: retention dropped {drop}% ({reason})")
        return alerts[: self.config.max_theme_items]

    def _clip_spikes(self, clips: list[dict[str, Any]]) -> list[str]:
        spikes: list[str] = []
        for item in clips[-self.config.max_theme_items :]:
            score = _int_value(item.get("score") or item.get("views") or item.get("watch_rate"))
            if score < self.config.clip_spike_threshold:
                continue
            title = str(item.get("title") or item.get("hook") or item.get("subject") or "clip")
            spikes.append(f"{title[:70]} ({score})")
        return spikes[: self.config.max_theme_items]

    def _text(self, payload: dict[str, Any]) -> str:
        for key in ("text", "comment", "message", "title", "summary", "hook"):
            value = payload.get(key)
            if value:
                return str(value)
        return ""


def _int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
