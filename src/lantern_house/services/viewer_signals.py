# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from lantern_house.config import ViewerSignalsConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import ViewerSignalSnapshot
from lantern_house.runtime.failsafe import AdaptiveServiceError, log_call_failure
from lantern_house.services.youtube_adapter import YouTubeSignalAdapterService
from lantern_house.utils.time import ensure_utc, isoformat, utcnow


class ViewerSignalIngestionService:
    def __init__(
        self,
        config: ViewerSignalsConfig,
        repository: StoryRepository,
        youtube_adapter_service: YouTubeSignalAdapterService | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.youtube_adapter_service = youtube_adapter_service
        self.path = Path(config.source_file_path)
        self.harvest_directory = Path(config.harvest_directory_path)
        self.interval = timedelta(minutes=max(1, config.check_interval_minutes))

    def refresh_if_due(
        self,
        *,
        now=None,
        force: bool = False,
    ) -> list[ViewerSignalSnapshot]:
        now = ensure_utc(now or utcnow())
        run_state = self._safe_run_state()
        last_checked = _parse_timestamp(
            ((run_state.get("metadata") or {}).get("viewer_signals") or {}).get("last_checked_at")
        )
        if not force and last_checked and now - last_checked < self.interval:
            return self.repository.list_active_viewer_signals(limit=self.config.max_active_signals)

        try:
            signals = self._load_signals(now=now, force=force)
        except Exception as exc:
            log_call_failure(
                "viewer_signals.refresh_if_due",
                exc,
                context={
                    "path": str(self.path),
                    "harvest_directory": str(self.harvest_directory),
                },
                expected_inputs=[
                    "A valid YAML mapping with an optional enabled flag and a signals list.",
                    "Optional JSONL files under the configured YouTube-signal harvest directory.",
                ],
                retry_advice=(
                    "Fix viewer_signals.yaml and save it again. The runtime will keep using the "
                    "last active viewer signals until the next poll."
                ),
                fallback_used="last-active-viewer-signals",
            )
            self.repository.merge_runtime_metadata(
                {
                    "viewer_signals": {
                        "last_checked_at": isoformat(now),
                        "last_error": str(exc)[:240],
                        "path": str(self.path),
                        "harvest_directory": str(self.harvest_directory),
                    }
                },
                now=now,
            )
            return self.repository.list_active_viewer_signals(limit=self.config.max_active_signals)

        self.repository.sync_viewer_signals(signals=signals, now=now)
        self.repository.merge_runtime_metadata(
            {
                "viewer_signals": {
                    "last_checked_at": isoformat(now),
                    "signal_count": len(signals),
                    "path": str(self.path),
                    "harvest_directory": str(self.harvest_directory),
                }
            },
            now=now,
        )
        return self.repository.list_active_viewer_signals(limit=self.config.max_active_signals)

    def _load_signals(self, *, now, force: bool = False) -> list[ViewerSignalSnapshot]:
        if not self.config.enabled:
            return []
        payload = self._load_yaml_payload()
        if not bool(payload.get("enabled", True)):
            return []

        configured_signals = payload.get("signals") or []
        if not isinstance(configured_signals, list):
            raise AdaptiveServiceError(
                "viewer_signals.yaml `signals` must be a list",
                expected_inputs=["A list of viewer-signal objects under the `signals` key."],
                retry_advice="Rewrite `signals` as a YAML list and retry.",
                context={"path": str(self.path)},
            )

        normalized: list[ViewerSignalSnapshot] = []
        for index, item in enumerate(configured_signals):
            if not isinstance(item, dict):
                continue
            signal = _build_signal_snapshot(
                item=item,
                index=index,
                default_source="operator",
                now=now,
            )
            if signal is not None:
                normalized.append(signal)
        normalized.extend(self._load_harvested_signals(now=now, force=force))
        return _dedupe_signals(normalized)[: self.config.max_active_signals]

    def _load_yaml_payload(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        raw_text = self.path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return {}
        try:
            payload = yaml.safe_load(raw_text) or {}
        except yaml.YAMLError as exc:
            raise AdaptiveServiceError(
                "viewer_signals.yaml could not be parsed as YAML",
                expected_inputs=["A YAML object with a `signals:` list."],
                retry_advice="Fix the YAML syntax and save the file again.",
                context={"path": str(self.path)},
            ) from exc
        if not isinstance(payload, dict):
            raise AdaptiveServiceError(
                "viewer_signals.yaml must contain a top-level mapping",
                expected_inputs=["A YAML object with configuration keys and a `signals:` list."],
                retry_advice="Rewrite the file as a top-level mapping and retry.",
                context={"path": str(self.path)},
            )
        return payload

    def _load_harvested_signals(self, *, now, force: bool = False) -> list[ViewerSignalSnapshot]:
        if self.youtube_adapter_service is not None:
            bundle = self.youtube_adapter_service.harvest(now=now, force=force)
            comments = bundle.comments
            clips = bundle.clips
            retention = bundle.retention
            live_chat = bundle.live_chat
        else:
            if not self.harvest_directory.exists():
                return []
            comments = _read_jsonl(self.harvest_directory / self.config.comments_file_name)
            clips = _read_jsonl(self.harvest_directory / self.config.clips_file_name)
            retention = _read_jsonl(self.harvest_directory / self.config.retention_file_name)
            live_chat = _read_jsonl(self.harvest_directory / self.config.live_chat_file_name)
        roster = self.repository.list_characters()
        names = {
            item["slug"]: {
                item["slug"],
                item["full_name"].split()[0].lower(),
                item["full_name"].lower(),
            }
            for item in roster
        }
        generated: list[ViewerSignalSnapshot] = []
        generated.extend(
            _ship_signals(
                comments=comments,
                live_chat=live_chat,
                names=names,
                now=now,
            )
        )
        generated.extend(
            _theory_signals(comments=comments, clips=clips, live_chat=live_chat, now=now)
        )
        generated.extend(_faction_signals(comments=comments, names=names, now=now))
        generated.extend(_clip_replay_signals(clips=clips, now=now))
        generated.extend(_retention_signals(retention=retention, now=now))
        return generated[: self.config.max_derived_signals]

    def _safe_run_state(self) -> dict[str, Any]:
        try:
            return self.repository.get_run_state()
        except RuntimeError:
            return self.repository.ensure_run_state()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _slug(value: Any) -> str:
    text = _clean(value).lower().replace("_", "-").replace(" ", "-")
    return "-".join(part for part in text.split("-") if part)


def _listify(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_clean(item) for item in value if _clean(item)]
    cleaned = _clean(value)
    return [cleaned] if cleaned else []


def _parse_timestamp(value: Any):
    text = _clean(value)
    if not text:
        return None
    try:
        from datetime import datetime

        return ensure_utc(datetime.fromisoformat(text))
    except ValueError:
        return None


def _int_or_default(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _build_signal_snapshot(
    *,
    item: dict[str, Any],
    index: int,
    default_source: str,
    now,
) -> ViewerSignalSnapshot | None:
    summary = _clean(item.get("summary")) or _clean(item.get("evidence"))
    signal_type = _slug(item.get("signal_type") or item.get("type") or "viewer")
    subject = _clean(item.get("subject")) or "general"
    if not summary:
        return None
    key_seed = item.get("signal_key") or f"{signal_type}:{subject}:{summary}"
    digest = hashlib.sha1(str(key_seed).encode("utf-8")).hexdigest()[:12]
    expires_at = None
    expires_in_hours = _int_or_default(item.get("expires_in_hours"), 24)
    if expires_in_hours > 0:
        expires_at = now + timedelta(hours=min(24 * 30, expires_in_hours))
    return ViewerSignalSnapshot(
        signal_key=_slug(item.get("signal_key") or f"{signal_type}-{digest}"),
        signal_type=signal_type,
        subject=subject,
        intensity=_clamp(_int_or_default(item.get("intensity"), 5), 1, 10),
        sentiment=_slug(item.get("sentiment") or "mixed"),
        summary=summary,
        source=_clean(item.get("source")) or default_source,
        retention_impact=_clamp(_int_or_default(item.get("retention_impact"), 5), 1, 10),
        metadata={
            "index": index,
            "raw_tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
            "evidence": _listify(item.get("evidence")),
            "weight": _int_or_default(item.get("weight"), 0),
        },
        expires_at=expires_at,
        created_at=now,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _ship_signals(
    *,
    comments: list[dict[str, Any]],
    live_chat: list[dict[str, Any]],
    names: dict[str, set[str]],
    now,
) -> list[ViewerSignalSnapshot]:
    pair_counts: Counter[tuple[str, str]] = Counter()
    texts = [*_messages_from_records(comments), *_messages_from_records(live_chat)]
    for text in texts:
        hits = sorted(
            {
                slug
                for slug, aliases in names.items()
                if any(alias in text for alias in aliases if alias)
            }
        )
        if len(hits) < 2:
            continue
        pair_counts[(hits[0], hits[1])] += 1
    results: list[ViewerSignalSnapshot] = []
    for index, (pair, count) in enumerate(pair_counts.most_common(2)):
        subject = "/".join(pair)
        results.append(
            _derived_signal(
                signal_type="ship-buzz",
                subject=subject,
                summary=f"Audience discussion is clustering around {subject}.",
                source="youtube-comments",
                intensity=min(10, 4 + count),
                retention_impact=min(10, 5 + count),
                evidence=[f"{count} co-mention clusters from comments and live chat."],
                index=index,
                now=now,
            )
        )
    return results


def _theory_signals(
    *,
    comments: list[dict[str, Any]],
    clips: list[dict[str, Any]],
    live_chat: list[dict[str, Any]],
    now,
) -> list[ViewerSignalSnapshot]:
    theory_terms = {
        "ledger": "ledger",
        "codicil": "codicil",
        "evelyn": "evelyn",
        "voice memo": "voice memo",
        "key": "key",
        "record": "records",
    }
    counts: Counter[str] = Counter()
    texts = [
        *_messages_from_records(comments),
        *_messages_from_records(clips),
        *_messages_from_records(live_chat),
    ]
    for text in texts:
        for marker, label in theory_terms.items():
            if marker in text:
                counts[label] += 1
    results: list[ViewerSignalSnapshot] = []
    for index, (subject, count) in enumerate(counts.most_common(2)):
        results.append(
            _derived_signal(
                signal_type="theory-burst",
                subject=subject,
                summary=f"Theory chatter is spiking around {subject}.",
                source="youtube-mixed",
                intensity=min(10, 4 + count),
                retention_impact=min(10, 5 + count),
                evidence=[f"{count} theory mentions across comments, clips, and live chat."],
                index=index,
                now=now,
            )
        )
    return results


def _faction_signals(
    *,
    comments: list[dict[str, Any]],
    names: dict[str, set[str]],
    now,
) -> list[ViewerSignalSnapshot]:
    counts: Counter[str] = Counter()
    for text in _messages_from_records(comments):
        if "team " not in text and "side " not in text:
            continue
        for slug, aliases in names.items():
            if any(alias in text for alias in aliases if alias):
                counts[slug] += 1
    results: list[ViewerSignalSnapshot] = []
    for index, (subject, count) in enumerate(counts.most_common(2)):
        results.append(
            _derived_signal(
                signal_type="faction-split",
                subject=subject,
                summary=f"Side-taking is forming around {subject}.",
                source="youtube-comments",
                intensity=min(10, 4 + count),
                retention_impact=min(10, 4 + count),
                evidence=[f"{count} side-taking comment clusters mention {subject}."],
                index=index,
                now=now,
            )
        )
    return results


def _clip_replay_signals(*, clips: list[dict[str, Any]], now) -> list[ViewerSignalSnapshot]:
    results: list[ViewerSignalSnapshot] = []
    ranked = sorted(
        clips,
        key=lambda item: _int_or_default(item.get("replays"), 0),
        reverse=True,
    )
    for index, item in enumerate(ranked[:2]):
        replays = _int_or_default(item.get("replays"), 0)
        if replays < 3:
            continue
        subject = _clean(item.get("subject") or item.get("title") or f"clip-{index + 1}")
        results.append(
            _derived_signal(
                signal_type="clip-replay",
                subject=subject,
                summary=f"One clip is replaying unusually often: {subject}.",
                source="youtube-clips",
                intensity=min(10, 3 + replays),
                retention_impact=min(10, 4 + replays),
                evidence=[f"Replay count observed: {replays}."],
                index=index,
                now=now,
            )
        )
    return results


def _retention_signals(*, retention: list[dict[str, Any]], now) -> list[ViewerSignalSnapshot]:
    results: list[ViewerSignalSnapshot] = []
    for index, item in enumerate(retention[:2]):
        drop_percent = _int_or_default(item.get("drop_percent"), 0)
        if drop_percent < 12:
            continue
        segment = _clean(item.get("segment") or item.get("label") or "mid-stream")
        signal_type = "recap-dropoff" if "recap" in segment.lower() else "retention-dip"
        results.append(
            _derived_signal(
                signal_type=signal_type,
                subject=segment,
                summary=f"Audience retention drops during {segment}.",
                source="youtube-retention",
                intensity=min(10, 4 + drop_percent // 8),
                retention_impact=min(10, 5 + drop_percent // 10),
                evidence=[f"Drop percentage observed: {drop_percent}%."],
                index=index,
                now=now,
            )
        )
    return results


def _derived_signal(
    *,
    signal_type: str,
    subject: str,
    summary: str,
    source: str,
    intensity: int,
    retention_impact: int,
    evidence: list[str],
    index: int,
    now,
) -> ViewerSignalSnapshot:
    key_seed = f"{signal_type}:{subject}:{summary}"
    digest = hashlib.sha1(key_seed.encode("utf-8")).hexdigest()[:12]
    return ViewerSignalSnapshot(
        signal_key=f"{signal_type}-{digest}",
        signal_type=signal_type,
        subject=subject,
        intensity=_clamp(intensity, 1, 10),
        sentiment="mixed",
        summary=summary,
        source=source,
        retention_impact=_clamp(retention_impact, 1, 10),
        metadata={"index": index, "evidence": evidence},
        expires_at=now + timedelta(hours=24),
        created_at=now,
    )


def _messages_from_records(records: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for item in records:
        text = _clean(item.get("text") or item.get("title") or item.get("summary"))
        if text:
            messages.append(text.lower())
    return messages


def _dedupe_signals(signals: list[ViewerSignalSnapshot]) -> list[ViewerSignalSnapshot]:
    unique: dict[str, ViewerSignalSnapshot] = {}
    for signal in signals:
        unique[signal.signal_key] = signal
    return list(unique.values())
