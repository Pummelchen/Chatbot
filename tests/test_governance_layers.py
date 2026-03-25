# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import (
    CanonCourtConfig,
    LoadOrchestrationConfig,
    MonetizationConfig,
    OpsDashboardConfig,
    ProgrammingGridConfig,
)
from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    EventCandidate,
    HighlightPackageSnapshot,
    LoadProfileSnapshot,
    StrategicBriefSnapshot,
    TurnCriticReport,
)
from lantern_house.domain.enums import EventType
from lantern_house.services.canon_court import CanonCourtService
from lantern_house.services.load_orchestration import LoadOrchestrationService
from lantern_house.services.monetization import MonetizationPackagingService
from lantern_house.services.ops_dashboard import OpsDashboardService
from lantern_house.services.programming_grid import ProgrammingGridService
from lantern_house.utils.time import utcnow


class ProgrammingGridRepo:
    def __init__(self) -> None:
        self.saved = []

    def list_recent_events(self, *, hours=24, limit=20, minimum_significance=1):
        now = utcnow()
        if hours <= 24:
            return [
                type(
                    "Event",
                    (),
                    {
                        "event_type": "financial",
                        "title": "Payroll cliff hits the lobby",
                        "significance": 8,
                        "created_at": now - timedelta(hours=2),
                    },
                )()
            ]
        return []

    def get_house_state_snapshot(self):
        return type(
            "HouseState",
            (),
            {
                "active_pressures": [
                    type(
                        "Pressure",
                        (),
                        {"label": "Inspection risk", "intensity": 8},
                    )()
                ]
            },
        )()

    def list_open_arcs(self, *, limit=5):
        return [
            type("Arc", (), {"title": "Who Owns Lantern House?"})(),
        ]

    def get_latest_hourly_progress_ledger(self):
        return type("Ledger", (), {"contract_met": False, "dominant_axis": "debt"})()

    def sync_programming_grid_slots(self, *, slots, now=None):
        self.saved = slots
        return slots

    def list_programming_grid_slots(self, *, limit=10):
        return self.saved[:limit]


class MonetizationRepo:
    def __init__(self) -> None:
        self.saved = None

    def record_monetization_package(self, *, package, now=None):
        self.saved = package
        return package


class LoadRepo:
    def get_run_state(self):
        return {
            "status": "running",
            "degraded_mode": True,
            "metadata": {"recent_failure_count": 3},
        }

    def list_recent_message_metrics(self, *, limit=10):
        now = utcnow()
        return [
            {"latency_ms": 18000, "created_at": now},
            {"latency_ms": 12000, "created_at": now - timedelta(seconds=5)},
            {"latency_ms": 9000, "created_at": now - timedelta(seconds=10)},
        ]


class OpsRepo:
    def __init__(self) -> None:
        self.saved = None

    def get_run_state(self):
        now = utcnow()
        return {
            "status": "running",
            "last_tick_no": 12,
            "last_checkpoint_at": now - timedelta(minutes=5),
            "last_recap_hour": now - timedelta(hours=2),
            "last_public_message_at": now - timedelta(seconds=15),
            "degraded_mode": True,
            "metadata": {"runtime_phase": "loop-ready", "restart_count": 4},
        }

    def get_latest_strategic_brief(self, *, now=None, active_only=False):
        return StrategicBriefSnapshot(
            title="Protect the day plan",
            created_at=utcnow() - timedelta(hours=3),
        )

    def get_latest_hourly_progress_ledger(self):
        return type("Ledger", (), {"contract_met": False})()

    def get_story_gravity_state_snapshot(self):
        return type("Gravity", (), {"drift_score": 61})()

    def record_ops_telemetry(self, *, snapshot, now=None):
        self.saved = snapshot
        return snapshot

    def get_latest_ops_telemetry(self):
        return self.saved


def test_programming_grid_marks_missing_daily_slots_at_risk() -> None:
    service = ProgrammingGridService(
        ProgrammingGridRepo(),
        ProgrammingGridConfig(at_risk_after_hours=1, weekly_at_risk_after_days=1),
    )
    slots = service.refresh(now=utcnow().replace(hour=18, minute=0, second=0, microsecond=0))
    assert any(slot.slot_key == "house-crisis" and slot.status == "done" for slot in slots)
    assert any(slot.slot_key == "romance-escalation" and slot.status == "at-risk" for slot in slots)


def test_canon_court_softens_protected_truth_bleed() -> None:
    service = CanonCourtService(CanonCourtConfig())
    packet = CharacterContextPacket(
        character_slug="amelia",
        full_name="Amelia Vale",
        cultural_background="Anglo",
        public_persona="practical manager",
        hidden_wound="loss",
        long_term_desire="save the house",
        private_fear="public collapse",
        family_expectations="protect the family name",
        conflict_style="controlled",
        privacy_boundaries="tight",
        value_instincts="duty first",
        emotional_expression="restrained",
        message_style="clipped",
        ensemble_role="House Manager",
        current_location="Front Desk",
        manager_directive="Keep the room volatile.",
        forbidden_boundaries=["Do not reveal Evelyn copied the ledger and staged the fire route."],
    )
    turn = CharacterTurn(
        public_message="Evelyn copied the ledger and staged the fire route, so case closed.",
        event_candidates=[
            EventCandidate(
                event_type=EventType.REVEAL,
                title="Everything is solved",
                details="The secret is fully explained.",
                significance=9,
            )
        ],
    )
    report = service.review(packet=packet, turn=turn, events=turn.event_candidates)
    assert report.findings
    assert report.requires_repair is True


def test_monetization_pipeline_builds_packaging() -> None:
    repo = MonetizationRepo()
    service = MonetizationPackagingService(repo, MonetizationConfig(min_package_score=60))
    package = service.maybe_record(
        message_id=9,
        speaker_slug="lucia",
        turn=CharacterTurn(
            public_message="If the ledger is fake, then one of you wanted the house to drown.",
            event_candidates=[
                EventCandidate(
                    event_type=EventType.CLUE,
                    title="Ledger doubt lands",
                    details="The paperwork may have been staged.",
                    significance=8,
                )
            ],
            new_questions=["Who forged the ledger page?"],
        ),
        report=TurnCriticReport(
            score=84,
            clip_value=8,
            quote_worthiness=8,
            fandom_discussion_value=8,
            novelty=7,
        ),
        strategic_brief=StrategicBriefSnapshot(title="Push theory value"),
        highlight_package=HighlightPackageSnapshot(
            message_id=9,
            speaker_slug="lucia",
            title="Lucía just handed viewers a new theory",
            hook_line="If the ledger is fake, then one of you wanted the house to drown.",
            quote_line="If the ledger is fake, then one of you wanted the house to drown.",
            summary_blurb="The paperwork may have been staged.",
            theory_angle="Who forged the ledger page?",
            score=82,
        ),
        programming_grid_digest=["daily Clue turn [at-risk]: No fresh clue has landed yet."],
        now=utcnow(),
    )
    assert package is not None
    assert repo.saved is not None
    assert package.comment_prompt
    assert "fan-theory" in package.tags


def test_load_orchestration_enters_critical_tier() -> None:
    service = LoadOrchestrationService(LoadRepo(), LoadOrchestrationConfig())
    profile = service.build_profile(
        pending_manager_prefetch=True,
        pending_background_jobs=2,
        now=utcnow(),
    )
    assert profile.load_tier == "critical"
    assert "defer-god-ai-refresh" in profile.recommended_actions


def test_ops_dashboard_generates_auto_remediation_snapshot() -> None:
    repo = OpsRepo()
    service = OpsDashboardService(repo, OpsDashboardConfig(stale_checkpoint_seconds=60))
    snapshot = service.capture(
        load_profile=LoadProfileSnapshot(
            load_tier="high",
            average_latency_ms=8000,
            recommended_actions=["limit-background-work"],
        ),
        now=utcnow(),
    )
    assert snapshot is not None
    assert "force-checkpoint" in snapshot.auto_remediations
    assert "backfill-hourly-recaps" in snapshot.auto_remediations
