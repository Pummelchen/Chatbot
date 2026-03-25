# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine

from lantern_house.db import models
from lantern_house.db.base import Base
from lantern_house.db.repository import StoryRepository
from lantern_house.db.session import SessionFactory
from lantern_house.domain.contracts import (
    CanonCapsuleSnapshot,
    CanonCourtFindingSnapshot,
    HighlightPackageSnapshot,
    HourlyProgressLedgerSnapshot,
    MonetizationPackageSnapshot,
    OpsTelemetrySnapshot,
    ProgrammingGridSlotSnapshot,
    SoakAuditSnapshot,
)
from lantern_house.utils.time import utcnow


def test_build_relationship_initializes_score_fields() -> None:
    relationship = StoryRepository._build_relationship(
        pair_key=(1, 2),
        summary="Amelia pushed Rafael to be honest.",
        now=utcnow(),
    )
    assert relationship.character_a_id == 1
    assert relationship.character_b_id == 2
    assert relationship.trust_score == 0
    assert relationship.desire_score == 0
    assert relationship.suspicion_score == 0
    assert relationship.obligation_score == 0


def test_list_pending_beats_prioritizes_ready_beats_over_future_payoffs() -> None:
    repository = _repository_with_scene()
    now = utcnow()
    with repository.session_factory.session_scope() as session:
        session.add_all(
            [
                models.Beat(
                    scene_id=1,
                    beat_type="audience-rollout",
                    objective="Seed the romance path first.",
                    status="planned",
                    significance=6,
                    due_by=now,
                    metadata_json={"beat_key": "seed"},
                ),
                models.Beat(
                    scene_id=1,
                    beat_type="audience-rollout",
                    objective="Land the major payoff much later.",
                    status="planned",
                    significance=9,
                    due_by=now + timedelta(hours=12),
                    metadata_json={"beat_key": "payoff"},
                ),
            ]
        )

    beats = repository.list_pending_beats(limit=2, now=now)

    assert beats[0].beat_key == "seed"
    assert beats[0].status == "ready"
    assert beats[1].beat_key == "payoff"
    assert beats[1].status == "planned"


def test_complete_matching_beats_does_not_complete_future_planned_beats() -> None:
    repository = _repository_with_scene()
    now = utcnow()
    with repository.session_factory.session_scope() as session:
        session.add(
            models.Beat(
                scene_id=1,
                beat_type="audience-rollout",
                objective="Future payoff.",
                status="planned",
                significance=9,
                due_by=now + timedelta(hours=8),
                metadata_json={"beat_key": "future", "keywords": ["amelia", "rafael"]},
            )
        )

    completed = repository.complete_matching_beats(
        texts=["Amelia and Rafael almost kiss."],
        now=now,
    )

    assert completed == []
    beats = repository.list_pending_beats(limit=1, now=now)
    assert beats[0].beat_key == "future"
    assert beats[0].status == "planned"


def test_repository_can_persist_story_memory_layers() -> None:
    repository = _repository_with_scene()
    now = utcnow()

    repository.save_hourly_progress_ledger(
        snapshot=HourlyProgressLedgerSnapshot(
            bucket_start_at=now.replace(minute=0, second=0, microsecond=0),
            bucket_end_at=now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1),
            meaningful_progressions=2,
            evidence_shift_count=1,
            debt_shift_count=1,
            contract_met=True,
            dominant_axis="evidence",
            recommended_push=["Push a sharper question next."],
        ),
        now=now,
    )
    ledger = repository.get_latest_hourly_progress_ledger()
    assert ledger is not None
    assert ledger.contract_met is True
    assert ledger.dominant_axis == "evidence"

    repository.sync_programming_grid_slots(
        slots=[
            ProgrammingGridSlotSnapshot(
                horizon="daily",
                slot_key="clue-turn",
                label="Clue turn",
                objective="Land one clue today.",
                target_axis="evidence",
                status="at-risk",
                priority=9,
                notes=["No clue turn has landed yet."],
                window_start_at=now.replace(hour=0, minute=0, second=0, microsecond=0),
                window_end_at=now.replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=1),
            )
        ],
        now=now,
    )
    grid_slots = repository.list_programming_grid_slots(limit=1)
    assert grid_slots[0].slot_key == "clue-turn"
    assert grid_slots[0].status == "at-risk"

    repository.save_canon_capsule(
        snapshot=CanonCapsuleSnapshot(
            window_key="24h",
            headline="24h canon: Debt and desire both moved.",
            state_of_play=["The house is still under cash pressure."],
            key_clues=["CLUE: The copied ledger page exists."],
            relationship_fault_lines=["amelia<->rafael: trust 8, desire 8."],
            active_pressures=["Payroll cliff: someone has to blink."],
            unresolved_questions=["Who copied the registry page?"],
            protected_truths=["Do not solve Evelyn's disappearance outright."],
            recap_hooks=["Lucía challenged the paperwork."],
        ),
        now=now,
    )
    capsules = repository.list_canon_capsules(window_keys=["24h"])
    assert capsules[0].headline.startswith("24h canon")

    repository.record_highlight_package(
        package=HighlightPackageSnapshot(
            message_id=1,
            speaker_slug="amelia",
            title="Amelia just changed the balance of power",
            hook_line="Tell me the truth before payroll tells it for you.",
            quote_line="Tell me the truth before payroll tells it for you.",
            summary_blurb="A money threat became personal.",
            conflict_axis="financial",
            score=82,
        ),
        now=now,
    )
    highlights = repository.list_recent_highlight_packages(limit=1)
    assert highlights[0].speaker_slug == "amelia"
    assert highlights[0].score == 82

    repository.record_monetization_package(
        package=MonetizationPackageSnapshot(
            message_id=1,
            highlight_message_id=1,
            speaker_slug="amelia",
            primary_title="Amelia just gave viewers a new side to pick",
            hook_line="Tell me the truth before payroll tells it for you.",
            quote_line="Tell me the truth before payroll tells it for you.",
            summary_blurb="A money threat became personal.",
            recap_blurb="The house crisis became public and personal.",
            chapter_label="Daily recap hook",
            comment_prompt="Whose side are you on right now?",
            tags=["lantern-house", "ship-war"],
            score=88,
        ),
        now=now,
    )
    monetization = repository.list_recent_monetization_packages(limit=1)
    assert monetization[0].score == 88
    assert monetization[0].speaker_slug == "amelia"

    repository.record_soak_audit_run(
        snapshot=SoakAuditSnapshot(
            horizons_hours=[24, 72, 168],
            progression_miss_risk=40,
            drift_risk=35,
            strategy_lock_risk=55,
            recap_decay_risk=30,
            clip_drought_risk=25,
            ship_stagnation_risk=45,
            unresolved_overload_risk=20,
            recommended_direction="mystery-evidence-first",
            audit_notes=["The next day needs a sharper clue path."],
            candidate_pressure=["Push copied-ledger evidence."],
        ),
        now=now,
    )
    audit = repository.get_latest_soak_audit()
    assert audit is not None
    assert audit.recommended_direction == "mystery-evidence-first"

    repository.record_canon_court_findings(
        findings=[
            CanonCourtFindingSnapshot(
                issue_type="premature-finality",
                severity="critical",
                action="repair",
                summary="The turn spoke with too much finality.",
                evidence=["case closed"],
            )
        ],
        message_id=1,
        now=now,
    )
    findings = repository.list_recent_canon_court_findings(limit=1)
    assert findings[0].issue_type == "premature-finality"

    repository.record_ops_telemetry(
        snapshot=OpsTelemetrySnapshot(
            runtime_status="running",
            phase="loop-ready",
            degraded_mode=False,
            load_tier="medium",
            average_latency_ms=2100,
            checkpoint_age_seconds=30,
            recap_age_minutes=10,
            strategy_age_minutes=20,
            drift_risk=35,
            progression_contract_open=False,
            restart_count=1,
            active_strategy="mystery-evidence-first",
            auto_remediations=["force-hourly-progression"],
        ),
        now=now,
    )
    telemetry = repository.get_latest_ops_telemetry()
    assert telemetry is not None
    assert telemetry.active_strategy == "mystery-evidence-first"


def _repository_with_scene() -> StoryRepository:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    repository = StoryRepository(SessionFactory(engine))
    with repository.session_factory.session_scope() as session:
        session.add(
            models.SceneState(
                id=1,
                scene_key="test-scene",
                status="active",
                objective="Hold the room together.",
                emotional_temperature=5,
                mystery_pressure=5,
                romance_pressure=5,
                comedic_pressure=4,
                active_character_slugs=[],
            )
        )
    return repository
