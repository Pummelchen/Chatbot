# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.config import ShadowReplayConfig
from lantern_house.context.assembler import ContextAssembler
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import CharacterTurn, ShadowReplayRunSnapshot
from lantern_house.quality.pacing import ContinuityGuard
from lantern_house.services.canon_court import CanonCourtService
from lantern_house.services.critic import TurnCriticService
from lantern_house.services.event_extractor import EventExtractor
from lantern_house.utils.time import ensure_utc, utcnow


class ShadowReplayService:
    def __init__(
        self,
        *,
        repository: StoryRepository,
        assembler: ContextAssembler,
        event_extractor: EventExtractor,
        canon_court_service: CanonCourtService,
        critic_service: TurnCriticService,
        continuity_guard: ContinuityGuard,
        config: ShadowReplayConfig,
    ) -> None:
        self.repository = repository
        self.assembler = assembler
        self.event_extractor = event_extractor
        self.canon_court_service = canon_court_service
        self.critic_service = critic_service
        self.continuity_guard = continuity_guard
        self.config = config

    def run(
        self,
        *,
        changed_files: list[str] | None = None,
        now=None,
    ) -> ShadowReplayRunSnapshot:
        now = ensure_utc(now or utcnow())
        if not self.config.enabled:
            snapshot = ShadowReplayRunSnapshot(
                status="skipped",
                changed_files=changed_files or [],
                checks=["shadow-replay-disabled"],
                metadata={"enabled": False},
                created_at=now,
            )
            return self.repository.record_shadow_replay_run(snapshot=snapshot, now=now)

        recent_rows = self.repository.list_recent_chat_rows(
            limit=max(1, self.config.recent_turn_limit),
            hours=max(1, self.config.compare_window_hours),
            now=now,
        )
        checks: list[str] = []
        regressions: list[str] = []
        if not recent_rows:
            snapshot = ShadowReplayRunSnapshot(
                status="passed",
                changed_files=changed_files or [],
                compared_turns=0,
                checks=["no-recent-turns"],
                metadata={"reason": "No recent turns available for replay."},
                created_at=now,
            )
            return self.repository.record_shadow_replay_run(snapshot=snapshot, now=now)

        directive = self.repository.get_latest_manager_directive() or {
            "objective": "Keep the house coherent under replay validation.",
            "per_character": {},
            "active_character_slugs": [],
            "reveal_budget": 1,
        }
        reviews = {
            row["message_id"]: row
            for row in self.repository.list_recent_public_turn_reviews(
                limit=max(8, len(recent_rows) * 2)
            )
            if row.get("message_id") is not None
        }
        for row in reversed(recent_rows):
            speaker_slug = str(row.get("speaker_slug") or "").strip()
            if not speaker_slug:
                regressions.append("recent replay row is missing speaker_slug")
                continue
            try:
                packet = self.assembler.build_character_packet(speaker_slug, directive)
                turn = CharacterTurn(
                    public_message=str(row.get("content") or ""),
                    tone=str((row.get("hidden_metadata") or {}).get("tone") or "") or None,
                    new_questions=[
                        item
                        for item in ((row.get("hidden_metadata") or {}).get("new_questions") or [])
                        if isinstance(item, str)
                    ][:3],
                    answered_questions=[
                        item
                        for item in (
                            (row.get("hidden_metadata") or {}).get("answered_questions") or []
                        )
                        if isinstance(item, str)
                    ][:3],
                )
                events = self.event_extractor.extract(speaker_slug=speaker_slug, turn=turn)
                continuity_flags = self.continuity_guard.review_turn(
                    packet=packet,
                    directive=directive,
                    turn=turn,
                )
                canon = self.canon_court_service.review(packet=packet, turn=turn, events=events)
                critic = self.critic_service.review(
                    packet=packet,
                    turn=turn,
                    flags=[*continuity_flags, *(canon.additional_flags if canon else [])],
                )
                persisted = reviews.get(row["id"])
                checks.append(f"replayed-{speaker_slug}-tick-{row.get('tick_no')}")
                if canon and canon.requires_repair:
                    regressions.append(
                        f"{speaker_slug} tick {row.get('tick_no')}: replay now requires repair"
                    )
                previous_score = int(persisted.get("critic_score") or 0) if persisted else None
                if previous_score is not None and critic.score + 20 < previous_score:
                    regressions.append(
                        f"{speaker_slug} tick {row.get('tick_no')}: critic score dropped from "
                        f"{previous_score} to {critic.score}"
                    )
            except Exception as exc:  # pragma: no cover - bounded by service-level tests
                regressions.append(
                    f"{speaker_slug or 'unknown'} tick {row.get('tick_no')}: "
                    f"{type(exc).__name__}: {exc}"
                )
            if len(regressions) >= self.config.max_reported_regressions:
                break

        snapshot = ShadowReplayRunSnapshot(
            status="passed" if not regressions else "failed",
            changed_files=changed_files or [],
            compared_turns=min(len(recent_rows), self.config.recent_turn_limit),
            regression_count=len(regressions),
            checks=checks[: self.config.recent_turn_limit + 2],
            regressions=regressions[: self.config.max_reported_regressions],
            metadata={"window_hours": self.config.compare_window_hours},
            created_at=now,
        )
        return self.repository.record_shadow_replay_run(snapshot=snapshot, now=now)
