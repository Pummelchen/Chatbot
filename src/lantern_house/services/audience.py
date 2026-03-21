# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from lantern_house.config import AudienceConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import AudienceControlReport, BeatPlanItem
from lantern_house.runtime.failsafe import log_call_failure
from lantern_house.utils.time import ensure_utc, isoformat, utcnow


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
        sync_rollout = getattr(self.repository, "sync_rollout_requests", None)
        if callable(sync_rollout):
            sync_rollout(
                change_id=report.change_id,
                fingerprint=report.fingerprint,
                priority=report.priority,
                requests=report.requests,
                directives=report.directives,
                active=report.active,
                activated_at=report.activated_at,
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
                log_call_failure(
                    "audience.current_report",
                    exc,
                    context={"source": "run_state.metadata.audience_control"},
                    expected_inputs=[
                        "A persisted audience_control block matching AudienceControlReport."
                    ],
                    retry_advice=(
                        "Allow the next valid update.txt parse to rebuild the audience-control "
                        "state."
                    ),
                    fallback_used="empty-audience-control",
                )
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
            log_call_failure(
                "audience.load_update_file",
                exc,
                context={
                    "path": str(self.path),
                    "fingerprint": fingerprint,
                },
                expected_inputs=["A valid YAML mapping in update.txt."],
                retry_advice=(
                    "Fix the YAML syntax and save update.txt again. The runtime will keep the "
                    "last good audience-control state until the next poll."
                ),
                fallback_used="last-good-audience-control",
            )
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
        beat_hints = _build_beat_hints(
            payload,
            now=now,
            activated_at=activated_at,
            full_integration_hours=full_integration_hours,
        )

        return AudienceControlReport(
            active=enabled and bool(tone_dials or requests or directives or beat_hints),
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
            beat_hints=beat_hints[:12],
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
        if previous.active or previous.directives or previous.requests or previous.beat_hints:
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
        payload.get("story_requests") if isinstance(payload.get("story_requests"), dict) else {}
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
        payload.get("story_requests") if isinstance(payload.get("story_requests"), dict) else {}
    )
    directives.extend(_flatten_section(story_requests.get("avoid_for_now"), "Avoid for now"))
    directives.extend(_flatten_section(story_requests.get("new_conflicts"), "New conflict"))
    directives.extend(
        _flatten_section(story_requests.get("external_pressures"), "External pressure")
    )
    directives.extend(_flatten_section(story_requests.get("mysteries_to_push"), "Mystery push"))
    manager_notes = (
        payload.get("manager_notes") if isinstance(payload.get("manager_notes"), dict) else {}
    )
    directives.extend(_manager_note_lines(manager_notes))
    return directives


def _build_beat_hints(
    payload: dict[str, Any],
    *,
    now,
    activated_at: str | None,
    full_integration_hours: int,
) -> list[BeatPlanItem]:
    anchor = _parse_timestamp(activated_at) or now
    hints: list[BeatPlanItem] = []
    hints.extend(
        _relationship_beat_hints(
            payload.get("relationship_moves"),
            anchor=anchor,
            full_integration_hours=full_integration_hours,
        )
    )
    hints.extend(
        _entity_beat_hints(
            payload.get("character_changes"),
            entity_label="character",
            anchor=anchor,
            full_integration_hours=full_integration_hours,
        )
    )
    hints.extend(
        _entity_beat_hints(
            payload.get("location_changes"),
            entity_label="location",
            anchor=anchor,
            full_integration_hours=full_integration_hours,
        )
    )
    story_requests = (
        payload.get("story_requests") if isinstance(payload.get("story_requests"), dict) else {}
    )
    hints.extend(
        _freeform_beat_hints(
            story_requests.get("must_happen"),
            label="must-happen",
            anchor=anchor,
            full_integration_hours=full_integration_hours,
        )
    )
    hints.extend(
        _freeform_beat_hints(
            story_requests.get("freeform_votes"),
            label="freeform-vote",
            anchor=anchor,
            full_integration_hours=full_integration_hours,
        )
    )
    deduped: list[BeatPlanItem] = []
    seen: set[str] = set()
    for hint in hints:
        if hint.beat_key in seen:
            continue
        seen.add(hint.beat_key)
        deduped.append(hint)
    return deduped


def _relationship_beat_hints(
    value: Any,
    *,
    anchor: datetime,
    full_integration_hours: int,
) -> list[BeatPlanItem]:
    if not isinstance(value, list):
        return []
    hints: list[BeatPlanItem] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        pair = item.get("pair")
        pair_parts = [str(part).strip() for part in pair[:2]] if isinstance(pair, list) else []
        if len(pair_parts) < 2:
            continue
        direction = _compact(str(item.get("direction", "relationship-shift")), limit=40)
        request_text = f"{pair_parts[0]} and {pair_parts[1]} -> {direction}"
        start_with = _compact(str(item.get("start_with", "seed the path first")), limit=100)
        avoid = _compact(str(item.get("avoid", "no instant payoff")), limit=100)
        objectives = _relationship_objectives(
            pair_parts=pair_parts,
            direction=direction,
            start_with=start_with,
            avoid=avoid,
        )
        for index, objective in enumerate(objectives):
            hints.append(
                BeatPlanItem(
                    beat_key=_beat_key("relationship", request_text, index),
                    beat_type="audience-rollout",
                    objective=objective,
                    significance=min(9, 6 + index),
                    ready_at=_schedule(anchor, full_integration_hours, index, len(objectives)),
                    keywords=_keywords_from_texts([*pair_parts, direction, objective]),
                    metadata={
                        "source": "audience-control",
                        "pair": pair_parts,
                        "direction": direction,
                        "phase": _phase_for_index(index, len(objectives)),
                        "request_text": request_text,
                        "request_summary": request_text,
                    },
                )
            )
    return hints


def _entity_beat_hints(
    value: Any,
    *,
    entity_label: str,
    anchor: datetime,
    full_integration_hours: int,
) -> list[BeatPlanItem]:
    if not isinstance(value, dict):
        return []
    hints: list[BeatPlanItem] = []
    add_items = _flatten_named_items(value.get("add"))
    remove_items = _flatten_named_items(value.get("remove"))
    for name in add_items[:2]:
        objectives = [
            f"Seed rumors and practical preparation for a new {entity_label}: {name}.",
            (
                f"Force the house to debate what welcoming {name} "
                "would cost financially and emotionally."
            ),
            f"Let {name} arrive or become usable through a concrete on-screen disruption.",
        ]
        hints.extend(
            _objectives_to_hints(
                label=f"add-{entity_label}",
                request_text=name,
                objectives=objectives,
                anchor=anchor,
                full_integration_hours=full_integration_hours,
                metadata={
                    "source": "audience-control",
                    "entity_label": entity_label,
                    "change": "add",
                },
            )
        )
    for name in remove_items[:2]:
        objectives = [
            f"Seed credible absence pressure around {name} instead of sudden disappearance.",
            (f"Make the cost of losing {name} visible through work, loyalty, or romance strain."),
            f"Move {name} toward a believable exit beat or sustained offscreen status.",
        ]
        hints.extend(
            _objectives_to_hints(
                label=f"remove-{entity_label}",
                request_text=name,
                objectives=objectives,
                anchor=anchor,
                full_integration_hours=full_integration_hours,
                metadata={
                    "source": "audience-control",
                    "entity_label": entity_label,
                    "change": "remove",
                },
            )
        )
    return hints


def _freeform_beat_hints(
    value: Any,
    *,
    label: str,
    anchor: datetime,
    full_integration_hours: int,
) -> list[BeatPlanItem]:
    requests = _flatten_section(value, "Request")
    hints: list[BeatPlanItem] = []
    for request in requests[:2]:
        text = request.split(":", 1)[-1].strip()
        objectives = [
            f"Seed the emotional or practical prerequisite for: {text}",
            f"Create resistance, jealousy, money pressure, or secrecy around: {text}",
            f"Move {text} one irreversible step closer without treating it as already solved.",
        ]
        hints.extend(
            _objectives_to_hints(
                label=label,
                request_text=text,
                objectives=objectives,
                anchor=anchor,
                full_integration_hours=full_integration_hours,
                metadata={"source": "audience-control", "request_kind": label},
            )
        )
    return hints


def _objectives_to_hints(
    *,
    label: str,
    request_text: str,
    objectives: list[str],
    anchor: datetime,
    full_integration_hours: int,
    metadata: dict[str, Any],
) -> list[BeatPlanItem]:
    hints: list[BeatPlanItem] = []
    for index, objective in enumerate(objectives):
        hints.append(
            BeatPlanItem(
                beat_key=_beat_key(label, request_text, index),
                beat_type="audience-rollout",
                objective=objective,
                significance=min(9, 6 + index),
                ready_at=_schedule(anchor, full_integration_hours, index, len(objectives)),
                keywords=_keywords_from_texts([request_text, objective]),
                metadata={
                    **metadata,
                    "phase": _phase_for_index(index, len(objectives)),
                    "request_summary": request_text,
                },
            )
        )
    return hints


def _relationship_objectives(
    *,
    pair_parts: list[str],
    direction: str,
    start_with: str,
    avoid: str,
) -> list[str]:
    pair_text = " and ".join(pair_parts)
    lowered = direction.lower()
    if "baby" in lowered:
        return [
            (
                f"{pair_text} keep getting shoved into domestic teamwork "
                f"that feels intimate enough to scare them. Start with {start_with}."
            ),
            (
                f"{pair_text} reach explicit future-talk, then flinch because "
                f"duty, shame, or old lies make a baby path feel dangerous. Avoid {avoid}."
            ),
            (
                f"Jealousy, family pressure, or house survival costs interrupt {pair_text} "
                "just when the bond starts looking stable."
            ),
            (
                f"{pair_text} choose each other in one practical crisis so an "
                "eventual baby storyline feels earned instead of voted into existence."
            ),
        ]
    if any(token in lowered for token in ("love", "marry", "romance", "together")):
        return [
            (
                f"{pair_text} edge closer through useful favors and subtext "
                "before anyone names what that means."
            ),
            (
                f"{pair_text} are forced into near-confession territory by a "
                "house problem or a jealous interruption."
            ),
            (
                f"{pair_text} make one emotionally costly choice that turns "
                "attraction into a serious plot force."
            ),
        ]
    if any(token in lowered for token in ("hate", "enemy", "feud", "estrange")):
        return [
            (
                f"{pair_text} start landing sharper public wounds without "
                "breaking the world logic of why they still have to share space."
            ),
            f"{pair_text} turn private resentment into a concrete loyalty fracture with witnesses.",
            (
                f"{pair_text} become an open fault line that other characters "
                "can exploit or try to mend."
            ),
        ]
    if any(token in lowered for token in ("alliance", "trust", "friend")):
        return [
            f"{pair_text} start with one cautious favor that could still be denied later.",
            (
                f"{pair_text} protect each other from one house threat, then "
                "worry about the cost of that trust."
            ),
            (f"{pair_text} become a real alliance with consequences for the rest of the room."),
        ]
    return [
        (
            f"{pair_text} shift first through subtext and believable shared tasks "
            "instead of sudden declarations."
        ),
        (
            f"{pair_text} hit resistance from secrecy, jealousy, or money "
            "pressure before the shift becomes public."
        ),
        (
            f"{pair_text} complete one visible step toward {direction} without "
            "making the change feel finished."
        ),
    ]


def _phase_for_index(index: int, total: int) -> str:
    if index == 0:
        return "seed"
    if index >= total - 1:
        return "payoff-ready"
    return "build"


def _schedule(anchor: datetime, full_integration_hours: int, index: int, total: int) -> str:
    if total <= 1:
        return isoformat(anchor)
    ratio = index / max(1, total - 1)
    offset_hours = round(full_integration_hours * ratio)
    return isoformat(anchor + timedelta(hours=offset_hours))


def _beat_key(label: str, request_text: str, index: int) -> str:
    fingerprint = hashlib.sha1(request_text.encode("utf-8")).hexdigest()[:10]
    return f"{label}-{fingerprint}-{index}"


def _keywords_from_texts(values: list[str]) -> list[str]:
    keywords: list[str] = []
    for value in values:
        for token in str(value).replace("/", " ").replace("-", " ").split():
            cleaned = token.strip(" ,.!?\"'()[]").lower()
            if len(cleaned) < 4:
                continue
            if cleaned in keywords:
                continue
            keywords.append(cleaned)
    return keywords[:8]


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
