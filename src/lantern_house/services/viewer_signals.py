# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import hashlib
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from lantern_house.config import ViewerSignalsConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import ViewerSignalSnapshot
from lantern_house.runtime.failsafe import AdaptiveServiceError, log_call_failure
from lantern_house.utils.time import ensure_utc, isoformat, utcnow


class ViewerSignalIngestionService:
    def __init__(self, config: ViewerSignalsConfig, repository: StoryRepository) -> None:
        self.config = config
        self.repository = repository
        self.path = Path(config.source_file_path)
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
            signals = self._load_signals(now=now)
        except Exception as exc:
            log_call_failure(
                "viewer_signals.refresh_if_due",
                exc,
                context={"path": str(self.path)},
                expected_inputs=[
                    "A valid YAML mapping with an optional enabled flag and a signals list."
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
                }
            },
            now=now,
        )
        return self.repository.list_active_viewer_signals(limit=self.config.max_active_signals)

    def _load_signals(self, *, now) -> list[ViewerSignalSnapshot]:
        if not self.config.enabled:
            return []
        if not self.path.exists():
            return []

        raw_text = self.path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return []
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
        if not bool(payload.get("enabled", True)):
            return []
        signals = payload.get("signals")
        if signals is None:
            return []
        if not isinstance(signals, list):
            raise AdaptiveServiceError(
                "viewer_signals.yaml `signals` must be a list",
                expected_inputs=["A list of viewer-signal objects under the `signals` key."],
                retry_advice="Rewrite `signals` as a YAML list and retry.",
                context={"path": str(self.path)},
            )
        normalized: list[ViewerSignalSnapshot] = []
        for index, item in enumerate(signals):
            if not isinstance(item, dict):
                continue
            summary = _clean(item.get("summary")) or _clean(item.get("evidence"))
            signal_type = _slug(item.get("signal_type") or item.get("type") or "viewer")
            subject = _clean(item.get("subject")) or "general"
            if not summary:
                continue
            key_seed = item.get("signal_key") or f"{signal_type}:{subject}:{summary}"
            digest = hashlib.sha1(str(key_seed).encode("utf-8")).hexdigest()[:12]
            expires_at = None
            expires_in_hours = _int_or_default(item.get("expires_in_hours"), 24)
            if expires_in_hours > 0:
                expires_at = now + timedelta(hours=min(24 * 30, expires_in_hours))
            normalized.append(
                ViewerSignalSnapshot(
                    signal_key=_slug(item.get("signal_key") or f"{signal_type}-{digest}"),
                    signal_type=signal_type,
                    subject=subject,
                    intensity=_clamp(_int_or_default(item.get("intensity"), 5), 1, 10),
                    sentiment=_slug(item.get("sentiment") or "mixed"),
                    summary=summary,
                    source=_clean(item.get("source")) or "operator",
                    retention_impact=_clamp(
                        _int_or_default(item.get("retention_impact"), 5), 1, 10
                    ),
                    metadata={
                        "index": index,
                        "raw_tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                        "evidence": _listify(item.get("evidence")),
                        "weight": _int_or_default(item.get("weight"), 0),
                    },
                    expires_at=expires_at,
                    created_at=now,
                )
            )
        return normalized[: self.config.max_active_signals]

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
