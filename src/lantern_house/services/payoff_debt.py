# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import PayoffDebtConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import BeatPlanItem, PayoffDebtSnapshot
from lantern_house.utils.time import ensure_utc, isoformat, utcnow


class PayoffDebtLedgerService:
    def __init__(self, repository: StoryRepository, config: PayoffDebtConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None, force: bool = False) -> list[PayoffDebtSnapshot]:
        now = ensure_utc(now or utcnow())
        existing = self.repository.list_payoff_debts(
            statuses=["open", "at-risk", "due", "overdue"],
            limit=self.config.max_active_debts,
        )
        if not force and not self.config.enabled:
            return existing
        if (
            not force
            and existing
            and existing[0].updated_at
            and now - ensure_utc(existing[0].updated_at)
            < timedelta(minutes=max(1, self.config.refresh_interval_minutes))
        ):
            return existing

        world = self.repository.get_world_state_snapshot()
        dormant_threads = self.repository.list_dormant_threads(limit=8)
        rollout_requests = self.repository.list_active_rollout_requests(limit=6)
        roster = self.repository.list_characters()
        pending_beats = self.repository.list_pending_beats(limit=8)
        items = self._build_items(
            world=world,
            dormant_threads=dormant_threads,
            rollout_requests=rollout_requests,
            roster=roster,
            pending_beats=pending_beats,
            now=now,
        )
        persisted = self.repository.sync_payoff_debts(items=items, now=now)
        self._sync_payoff_beats(items=persisted, now=now)
        return persisted

    def _build_items(
        self,
        *,
        world: dict,
        dormant_threads,
        rollout_requests: list[dict[str, object]],
        roster: list[dict[str, object]],
        pending_beats,
        now,
    ) -> list[PayoffDebtSnapshot]:
        items: list[PayoffDebtSnapshot] = []
        unresolved = list(world.get("unresolved_questions") or [])
        for index, question in enumerate(unresolved[:4]):
            heat = max(6, 9 - index)
            due_window = "overdue" if index == 0 else "soon"
            items.append(
                PayoffDebtSnapshot(
                    debt_key=f"question-{_slug(question)[:80]}",
                    debt_type="mystery-question",
                    subject="house mystery",
                    summary=question,
                    payoff_class="clue",
                    status="overdue" if due_window == "overdue" else "open",
                    due_window=due_window,
                    heat=heat,
                    urgency=heat,
                    freshness_hours=72 + index * 12,
                    metadata={"source": "world.unresolved_questions"},
                    last_touched_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )

        for thread in dormant_threads[:4]:
            last_seen = ensure_utc(thread.last_seen_at or now)
            freshness = int(max(1, (now - last_seen).total_seconds() // 3600))
            due_window = "overdue" if freshness >= self.config.overdue_after_hours else "soon"
            items.append(
                PayoffDebtSnapshot(
                    debt_key=f"dormant-{thread.thread_key}",
                    debt_type="dormant-thread",
                    subject=thread.thread_key,
                    summary=thread.summary,
                    payoff_class="revival",
                    status="overdue" if due_window == "overdue" else "at-risk",
                    due_window=due_window,
                    heat=max(5, min(10, thread.heat + (1 if freshness >= 24 else 0))),
                    urgency=max(5, min(10, thread.heat + (2 if freshness >= 24 else 0))),
                    freshness_hours=freshness,
                    metadata={"source": thread.source},
                    last_touched_at=last_seen,
                    created_at=thread.last_seen_at,
                    updated_at=now,
                )
            )

        relationship_keys: set[str] = set()
        for character in roster:
            slug = str(character.get("slug") or "")
            for rel in self.repository.list_relationship_snapshots(slug)[:3]:
                pair_key = "-".join(sorted((slug, rel.counterpart_slug)))
                if pair_key in relationship_keys:
                    continue
                relationship_keys.add(pair_key)
                if rel.desire_score < 6 and rel.suspicion_score < 6 and rel.trust_score < 7:
                    continue
                urgency = max(rel.desire_score, rel.suspicion_score, rel.trust_score // 2)
                items.append(
                    PayoffDebtSnapshot(
                        debt_key=f"relationship-{pair_key}",
                        debt_type="relationship-faultline",
                        subject=pair_key,
                        summary=(
                            f"{slug} and {rel.counterpart_slug} are carrying unresolved heat: "
                            f"{rel.summary}"
                        ),
                        payoff_class="emotion",
                        status="open",
                        linked_character_slug=slug,
                        due_window="soon" if urgency >= 7 else "later",
                        heat=max(5, min(10, urgency)),
                        urgency=max(5, min(10, urgency)),
                        freshness_hours=12,
                        metadata={
                            "trust": rel.trust_score,
                            "desire": rel.desire_score,
                            "suspicion": rel.suspicion_score,
                        },
                        last_touched_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )

        for request in rollout_requests[:3]:
            summary = str(request.get("summary") or "").strip()
            if not summary:
                continue
            priority = int(request.get("priority") or 5)
            items.append(
                PayoffDebtSnapshot(
                    debt_key=f"rollout-{_slug(summary)[:80]}",
                    debt_type="audience-rollout",
                    subject=summary,
                    summary=summary,
                    payoff_class="rollout",
                    status="open",
                    due_window="slow-burn",
                    heat=max(5, min(10, priority + 1)),
                    urgency=max(5, min(10, priority)),
                    freshness_hours=6,
                    metadata={
                        "request_type": request.get("request_type"),
                        "directives": request.get("directives", []),
                    },
                    last_touched_at=ensure_utc(request.get("activated_at") or now),
                    created_at=ensure_utc(request.get("activated_at") or now),
                    updated_at=now,
                )
            )

        for beat in pending_beats[:3]:
            if beat.beat_type not in {"audience-rollout", "guest-circulation"}:
                continue
            items.append(
                PayoffDebtSnapshot(
                    debt_key=f"beat-{beat.beat_type}-{_slug(beat.objective)[:72]}",
                    debt_type="prepared-beat",
                    subject=beat.beat_type,
                    summary=beat.objective,
                    payoff_class="staged-beat",
                    status="due" if beat.status in {"ready", "active"} else "open",
                    due_window="now" if beat.status in {"ready", "active"} else "soon",
                    heat=max(5, min(10, beat.significance)),
                    urgency=max(5, min(10, beat.significance + int(beat.status == "ready"))),
                    freshness_hours=4,
                    metadata={"beat_key": beat.beat_key, "beat_status": beat.status},
                    last_touched_at=beat.due_by or now,
                    created_at=beat.due_by or now,
                    updated_at=now,
                )
            )

        items.sort(key=lambda item: (-item.urgency, -item.heat, item.subject))
        return items[: self.config.max_active_debts]

    def _sync_payoff_beats(self, *, items: list[PayoffDebtSnapshot], now) -> None:
        beat_items = [
            BeatPlanItem(
                beat_key=f"payoff-{item.debt_key}",
                beat_type="payoff-debt",
                objective=item.summary,
                significance=max(5, min(9, item.urgency)),
                ready_at=isoformat(now),
                keywords=[item.subject, item.debt_type.replace("-", " ")],
                metadata={
                    "debt_key": item.debt_key,
                    "payoff_class": item.payoff_class,
                    "linked_character_slug": item.linked_character_slug,
                },
            )
            for item in items[: self.config.max_pending_beats]
        ]
        self.repository.sync_beats(
            beat_type="payoff-debt",
            items=beat_items,
            source_key="payoff-debt-ledger",
            now=now,
        )


def _slug(value: str) -> str:
    return "-".join(part for part in "".join(
        character.lower() if character.isalnum() else "-"
        for character in value
    ).split("-") if part)
