from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from lantern_house.config import AudienceConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import AudienceControlReport
from lantern_house.utils.time import ensure_utc, isoformat, utcnow

logger = logging.getLogger(__name__)


class AudienceControlService:
    def __init__(self, config: AudienceConfig, repository: StoryRepository) -> None:
        self.config = config
        self.repository = repository
        self.path = Path(config.update_file_path)
        self.interval = timedelta(minutes=max(1, config.check_interval_minutes))

    def refresh_if_due(
        self,
        *,
        now=None,
        force: bool = False,
    ) -> AudienceControlReport:
        now = ensure_utc(now or utcnow())
        previous = self.current_report()
        last_checked = _parse_timestamp(previous.last_checked_at)
        if not force and last_checked and now - last_checked < self.interval:
            return previous

        report = self._load_report(now=now, previous=previous)
        self.repository.merge_runtime_metadata(
            {"audience_control": report.model_dump()},
            now=now,
        )
        return report

    def current_report(self) -> AudienceControlReport:
        try:
            runtime = self.repository.get_run_state()
        except RuntimeError:
            runtime = self.repository.ensure_run_state()
        metadata = runtime.get("metadata") or {}
        raw = metadata.get("audience_control")
        if isinstance(raw, dict):
            try:
                return AudienceControlReport.model_validate(raw)
            except Exception as exc:
                logger.warning("invalid persisted audience control report: %s", exc)
        return AudienceControlReport()

    def _load_report(
        self,
        *,
        now,
        previous: AudienceControlReport,
    ) -> AudienceControlReport:
        if not self.path.exists():
            return AudienceControlReport(
                file_status="missing",
                last_checked_at=isoformat(now),
            )

        raw_text = self.path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return AudienceControlReport(
                file_status="empty",
                last_checked_at=isoformat(now),
            )

        fingerprint = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
        try:
            payload = yaml.safe_load(raw_text) or {}
        except yaml.YAMLError as exc:
            logger.warning("update.txt parse failed: %s", exc)
            return self._recover_or_disable(
                previous=previous,
                now=now,
                fingerprint=fingerprint,
                error=exc,
            )

        if not isinstance(payload, dict):
            return self._recover_or_disable(
                previous=previous,
                now=now,
                fingerprint=fingerprint,
                error=TypeError("update.txt must contain a top-level mapping"),
            )

        enabled = bool(payload.get("enabled", True))
        rollout = payload.get("rollout") if isinstance(payload.get("rollout"), dict) else {}
        full_integration_hours = _clamp(payload=rollout, key="full_integration_hours", default=24)
        activated_at = (
            previous.activated_at if previous.fingerprint == fingerprint else isoformat(now)
        )
        rollout_stage = _rollout_stage(
            activated_at=activated_at,
            full_integration_hours=full_integration_hours,
            now=now,
            active=enabled,
        )
        tone_dials = _normalize_tone_dials(payload.get("core_settings"))
        requests = _collect_requests(payload)
        directives = _collect_directives(
            payload,
            tone_dials=tone_dials,
            rollout_stage=rollout_stage,
        )

        return AudienceControlReport(
            active=enabled and bool(tone_dials or requests or directives),
            file_status="active" if enabled else "disabled",
            change_id=_string(payload.get("change_id")) or f"manual-{fingerprint[:8]}",
            source=_string(payload.get("source")) or "YouTube subscriber vote",
            fingerprint=fingerprint,
            priority=_clamp(payload=payload, key="priority", default=5),
            activated_at=activated_at if enabled else None,
            last_checked_at=isoformat(now),
            full_integration_hours=full_integration_hours,
            rollout_stage=rollout_stage,
            tone_dials=tone_dials,
            requests=requests[:8],
            directives=directives[:12],
        )

    def _recover_or_disable(
        self,
        *,
        previous: AudienceControlReport,
        now,
        fingerprint: str,
        error: Exception,
    ) -> AudienceControlReport:
        message = str(error)
        if previous.active or previous.directives or previous.requests:
            return previous.model_copy(
                update={
                    "file_status": "invalid",
                    "fingerprint": fingerprint,
                    "last_checked_at": isoformat(now),
                    "parse_error": message[:240],
                }
            )
        return AudienceControlReport(
            file_status="invalid",
            fingerprint=fingerprint,
            last_checked_at=isoformat(now),
            parse_error=message[:240],
        )


def _normalize_tone_dials(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, raw in value.items():
        slug = str(key).strip().lower().replace(" ", "_")
        try:
            parsed = int(raw)
        except (TypeError, ValueError):
            continue
        normalized[slug] = max(1, min(10, parsed))
    return normalized


def _collect_requests(payload: dict[str, Any]) -> list[str]:
    story_requests = (
        payload.get("story_requests")
        if isinstance(payload.get("story_requests"), dict)
        else {}
    )
    requests: list[str] = []
    requests.extend(_flatten_section(story_requests.get("must_happen"), "Must happen"))
    requests.extend(_relationship_requests(payload.get("relationship_moves")))
    requests.extend(_entity_requests(payload.get("character_changes"), "character"))
    requests.extend(_entity_requests(payload.get("location_changes"), "location"))
    requests.extend(_flatten_section(story_requests.get("freeform_votes"), "Vote"))
    return requests


def _collect_directives(
    payload: dict[str, Any],
    *,
    tone_dials: dict[str, int],
    rollout_stage: str,
) -> list[str]:
    directives = [
        (
            "Rollout: phase changes in gradually across the configured window, "
            "seed prerequisites first, and avoid instant retcons."
        ),
        f"Rollout stage: {rollout_stage}.",
    ]
    if tone_dials:
        dial_summary = ", ".join(f"{key}={value}" for key, value in sorted(tone_dials.items()))
        directives.append(f"Tone dials: {dial_summary}.")
    directives.extend(_entity_requests(payload.get("character_changes"), "character"))
    directives.extend(_entity_requests(payload.get("location_changes"), "location"))
    directives.extend(_relationship_requests(payload.get("relationship_moves")))
    story_requests = (
        payload.get("story_requests")
        if isinstance(payload.get("story_requests"), dict)
        else {}
    )
    directives.extend(_flatten_section(story_requests.get("avoid_for_now"), "Avoid for now"))
    directives.extend(_flatten_section(story_requests.get("new_conflicts"), "New conflict"))
    directives.extend(
        _flatten_section(story_requests.get("external_pressures"), "External pressure")
    )
    directives.extend(_flatten_section(story_requests.get("mysteries_to_push"), "Mystery push"))
    manager_notes = (
        payload.get("manager_notes")
        if isinstance(payload.get("manager_notes"), dict)
        else {}
    )
    directives.extend(_manager_note_lines(manager_notes))
    return directives


def _entity_requests(section: Any, label: str) -> list[str]:
    if not isinstance(section, dict):
        return []
    directives: list[str] = []
    for item in _flatten_named_items(section.get("add")):
        directives.append(f"Add {label}: {item}.")
    for item in _flatten_named_items(section.get("remove")):
        directives.append(f"Remove {label}: {item}.")
    for item in _flatten_named_items(section.get("spotlight_up")):
        directives.append(f"Increase {label} spotlight: {item}.")
    for item in _flatten_named_items(section.get("spotlight_down")):
        directives.append(f"Reduce {label} spotlight: {item}.")
    for item in _flatten_named_items(section.get("protect_from_exit")):
        directives.append(f"Protect from exit: {item}.")
    for item in _flatten_named_items(section.get("allow_exit")):
        directives.append(f"Allow exit path: {item}.")
    for item in _flatten_named_items(section.get("keep_offscreen_for_hours")):
        directives.append(f"Temporary offscreen request: {item}.")
    return directives


def _relationship_requests(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    directives: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            directives.append(f"Relationship vote: {_compact(str(item), limit=160)}.")
            continue
        pair = item.get("pair")
        if isinstance(pair, list):
            pair_text = " <-> ".join(_compact(str(part), limit=40) for part in pair[:2])
        else:
            pair_text = _compact(str(pair or "unspecified pair"), limit=80)
        direction = _compact(str(item.get("direction", "shift")), limit=40)
        pace = _compact(str(item.get("pace", "gradual")), limit=40)
        start_with = _compact(str(item.get("start_with", "seed the path first")), limit=90)
        avoid = _compact(str(item.get("avoid", "no instant payoff")), limit=90)
        intensity = _clamp(payload=item, key="intensity_target", default=5)
        directives.append(
            f"Relationship vote: {pair_text} -> {direction} "
            f"(target {intensity}/10, pace {pace}). Start with: {start_with}. Avoid: {avoid}."
        )
    return directives


def _flatten_section(value: Any, prefix: str) -> list[str]:
    if value is None:
        return []
    lines: list[str] = []
    if isinstance(value, list):
        for item in value:
            lines.extend(_flatten_section(item, prefix))
        return lines
    if isinstance(value, dict):
        if "request" in value:
            text = _compact(str(value.get("request", "")), limit=160)
            if text:
                lines.append(_ensure_sentence(f"{prefix}: {text}"))
            rollout_note = _compact(str(value.get("rollout_note", "")), limit=120)
            if rollout_note:
                lines.append(_ensure_sentence(f"{prefix} rollout: {rollout_note}"))
            return lines
        text = ", ".join(
            f"{_compact(str(key), limit=30)}={_compact(str(item), limit=60)}"
            for key, item in value.items()
            if str(item).strip()
        )
        if text:
            lines.append(_ensure_sentence(f"{prefix}: {text}"))
        return lines
    text = _compact(str(value), limit=160)
    if text:
        lines.append(_ensure_sentence(f"{prefix}: {text}"))
    return lines


def _flatten_named_items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items: list[str] = []
        for entry in value:
            items.extend(_flatten_named_items(entry))
        return items
    if isinstance(value, dict):
        if not _has_meaningful_content(value):
            return []
        primary = (
            _string(value.get("name"))
            or _string(value.get("character"))
            or _string(value.get("slug"))
        )
        detail_bits = []
        for key in ("role", "function", "background", "note", "rollout_note", "hours"):
            raw = _string(value.get(key))
            if raw:
                detail_bits.append(f"{key}={_compact(raw, limit=40)}")
        if primary:
            suffix = f" ({', '.join(detail_bits)})" if detail_bits else ""
            return [f"{_compact(primary, limit=60)}{suffix}"]
        return [_compact(str(value), limit=120)]
    text = _compact(str(value), limit=120)
    return [text] if text else []


def _has_meaningful_content(value: dict[str, Any]) -> bool:
    for raw in value.values():
        if isinstance(raw, list):
            if any(_string(item) for item in raw):
                return True
            continue
        text = _string(raw)
        if text and text != "0":
            return True
    return False


def _manager_note_lines(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    lines: list[str] = []
    for key, raw in value.items():
        if raw in ("", None):
            continue
        key_text = _compact(str(key).replace("_", " "), limit=40)
        value_text = _compact(str(raw), limit=120)
        lines.append(f"Manager note: {key_text} = {value_text}.")
    return lines


def _rollout_stage(
    *,
    activated_at: str | None,
    full_integration_hours: int,
    now,
    active: bool,
) -> str:
    if not active:
        return "inactive"
    activated = _parse_timestamp(activated_at)
    if activated is None:
        return "seed"
    elapsed_hours = max(0.0, (now - activated).total_seconds() / 3600)
    if elapsed_hours < max(2.0, full_integration_hours * 0.2):
        return "seed"
    if elapsed_hours < full_integration_hours * 0.6:
        return "build"
    if elapsed_hours < full_integration_hours:
        return "payoff-ready"
    return "settled"


def _clamp(*, payload: dict[str, Any], key: str, default: int) -> int:
    try:
        value = int(payload.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(1, min(168 if "hours" in key else 10, value))


def _string(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _compact(value: str, *, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _ensure_sentence(text: str) -> str:
    cleaned = text.rstrip()
    if cleaned.endswith(("!", "?", ".")):
        return cleaned
    return f"{cleaned}."


def _parse_timestamp(value: str | None):
    if not value:
        return None
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError:
        return None
