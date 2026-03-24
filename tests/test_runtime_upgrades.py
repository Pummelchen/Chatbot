# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import asyncio
from datetime import timedelta

from lantern_house.config import (
    AppConfig,
    CriticConfig,
    FailSafeConfig,
    GodAIConfig,
    HousePressureConfig,
    SimulationConfig,
    StoryGravityConfig,
)
from lantern_house.domain.contracts import (
    AudienceControlReport,
    CharacterContextPacket,
    CharacterTurn,
    EventView,
    HouseStateSnapshot,
    ManagerContextPacket,
    PacingHealthReport,
    SoakAuditSnapshot,
    StoryGovernanceReport,
    StoryGravityStateSnapshot,
    StrategicBriefPlan,
)
from lantern_house.runtime.failsafe import FailSafeExecutor
from lantern_house.runtime.orchestrator import RuntimeOrchestrator
from lantern_house.services.critic import TurnCriticService
from lantern_house.services.god_ai import GodAIService
from lantern_house.services.house import HousePressureService
from lantern_house.services.simulation_lab import SimulationLabService
from lantern_house.services.story_gravity import StoryGravityService
from lantern_house.utils.time import isoformat, utcnow


class HouseRepo:
    def __init__(self) -> None:
        self.saved_state: HouseStateSnapshot | None = None
        self.synced_beats = []
        self.state = HouseStateSnapshot(
            capacity=14,
            occupied_rooms=10,
            vacancy_pressure=5,
            cash_on_hand=1500,
            hourly_burn_rate=50,
            payroll_due_in_hours=18,
            repair_backlog=8,
            inspection_risk=5,
            guest_tension=5,
            weather_pressure=6,
            staff_fatigue=6,
            reputation_risk=5,
            metadata={
                "pressure_catalog": [
                    {
                        "slug": "payroll-cliff",
                        "metric": "payroll_due_in_hours",
                        "threshold": 24,
                        "comparison": "lte",
                        "label": "Payroll cliff",
                        "summary": "Payroll is close.",
                        "recommended_move": "Leak payroll panic into the room.",
                        "beat_objective": "Payroll pressure becomes public.",
                        "keywords": ["payroll", "cash"],
                    }
                ]
            },
            updated_at=utcnow() - timedelta(hours=5),
        )

    def get_house_state_snapshot(self) -> HouseStateSnapshot:
        return self.state

    def seed_exists(self) -> bool:
        return True

    def get_scene_snapshot(self):
        return {"scene_key": "opening-night"}

    def list_recent_events(self, **kwargs):
        now = utcnow()
        return [
            EventView(
                event_type="financial",
                title="Debt call lands badly",
                details="A payment problem spills into public view.",
                significance=8,
                payload={},
                created_at=now - timedelta(minutes=30),
            ),
            EventView(
                event_type="conflict",
                title="Lobby argument",
                details="Tempers spike in front of a guest.",
                significance=7,
                payload={},
                created_at=now - timedelta(minutes=20),
            ),
        ]

    def list_recent_messages(self, **kwargs):
        return []

    def save_house_state(self, snapshot: HouseStateSnapshot, *, now=None):
        self.saved_state = snapshot
        self.state = snapshot
        return snapshot

    def sync_beats(self, *, beat_type, items, source_key, now=None):
        self.synced_beats = items
        return []


class StrategicRepo:
    def __init__(self) -> None:
        self.saved: StrategicBriefPlan | None = None

    def get_latest_strategic_brief(self, *, now=None, active_only=True):
        return None

    def record_strategic_brief(
        self,
        *,
        plan: StrategicBriefPlan,
        source: str,
        model_name: str | None,
        simulation_report=None,
        now=None,
    ):
        self.saved = plan
        return {
            "source": source,
            "model_name": model_name,
            "title": plan.title,
        }


class GravityRepo:
    def __init__(self) -> None:
        self.saved: StoryGravityStateSnapshot | None = None
        self.synced_threads = []

    def get_story_gravity_state_snapshot(self) -> StoryGravityStateSnapshot:
        return StoryGravityStateSnapshot(updated_at=utcnow() - timedelta(hours=2))

    def get_world_state_snapshot(self):
        return {
            "title": "Lantern House",
            "unresolved_questions": ["Who hid the ledger?", "Why did Hana really return?"],
            "archived_threads": [
                "Amelia and Rafael were trapped in the records closet during the blackout.",
                "Lucía once saw a second registry copy.",
            ],
            "metadata": {
                "story_engine": {
                    "central_force": (
                        "Keep the house tied to debt, records, and unstable attraction."
                    ),
                    "core_promises": ["The house itself must always matter."],
                    "voice_guardrails": ["Keep dialogue concrete."],
                    "core_tensions": [
                        {"key": "house-survival", "keywords": ["debt", "repair", "rent"]},
                        {"key": "hidden-records", "keywords": ["ledger", "registry", "key"]},
                    ],
                }
            },
        }

    def list_recent_messages(self, **kwargs):
        now = utcnow()
        return [
            type(
                "Message",
                (),
                {
                    "content": "The ledger is still in the desk, unless someone moved it.",
                    "created_at": now,
                },
            )()
        ]

    def list_recent_events(self, **kwargs):
        now = utcnow()
        return [
            EventView(
                event_type="clue",
                title="Ledger mention",
                details="A guest overheard a ledger argument at the desk.",
                significance=7,
                payload={},
                created_at=now - timedelta(minutes=10),
            ),
            EventView(
                event_type="financial",
                title="Rent pressure",
                details="Cash pressure keeps leaking into public talk.",
                significance=8,
                payload={},
                created_at=now - timedelta(minutes=15),
            ),
        ]

    def get_house_state_snapshot(self):
        return HouseStateSnapshot(
            repair_backlog=7,
            inspection_risk=6,
            active_pressures=[],
        )

    def list_recent_recap_quality_scores(self, **kwargs):
        now = utcnow()
        return [
            {
                "summary_window": "1h",
                "bucket_end_at": now,
                "usefulness": 4,
                "clarity": 4,
                "theory_value": 5,
                "emotional_readability": 5,
                "next_hook_strength": 4,
                "issues": ["Recap language is getting generic."],
            }
        ]

    def sync_dormant_threads(self, *, threads, now=None):
        self.synced_threads = threads
        return threads

    def save_story_gravity_state(self, snapshot: StoryGravityStateSnapshot, *, now=None):
        self.saved = snapshot
        return snapshot


class AssemblerStub:
    def __init__(self, packet: ManagerContextPacket, repository) -> None:
        self.packet = packet
        self.repository = repository

    def build_manager_packet(self, *, audience_control=None, include_strategic=True):
        return self.packet.model_copy(update={"audience_control": audience_control})


class AudienceStub:
    def __init__(self, report: AudienceControlReport) -> None:
        self.report = report

    def current_report(self) -> AudienceControlReport:
        return self.report


class SoakAuditStub:
    def refresh_if_due(self, context, *, now=None, force=False):
        return SoakAuditSnapshot(
            horizons_hours=[24, 72, 168],
            progression_miss_risk=40,
            drift_risk=35,
            strategy_lock_risk=45,
            recap_decay_risk=30,
            clip_drought_risk=28,
            ship_stagnation_risk=32,
            unresolved_overload_risk=24,
            recommended_direction="house-pressure-first",
            audit_notes=["The hourly contract still needs a hard shift."],
            candidate_pressure=["Force a money or evidence turn."],
        )


class FailingLLM:
    async def generate_json(self, **kwargs):
        raise RuntimeError("offline in test")


class HangingLLM:
    async def generate_json(self, **kwargs):
        await asyncio.sleep(60)
        raise AssertionError("unreachable")


def test_refresh_house_pressure_uses_lazy_repository_fallback() -> None:
    calls = {"refresh": 0}

    class Repo:
        def get_house_state_snapshot(self):
            raise AssertionError("fallback should stay lazy")

    class HouseService:
        def refresh(self, *, now=None, force=False):
            calls["refresh"] += 1
            return HouseStateSnapshot()

    orchestrator = RuntimeOrchestrator.__new__(RuntimeOrchestrator)
    orchestrator.config = AppConfig()
    orchestrator.fail_safe = FailSafeExecutor(FailSafeConfig())
    orchestrator.repository = Repo()
    orchestrator.house_pressure_service = HouseService()

    RuntimeOrchestrator._refresh_house_pressure(orchestrator, now=utcnow(), force=True)

    assert calls["refresh"] == 1


def _manager_packet() -> ManagerContextPacket:
    return ManagerContextPacket(
        title="Lantern House",
        scene_objective="Hold the room together.",
        scene_location="Front Desk",
        emotional_temperature=6,
        cast_guidance=["amelia / Amelia Vale: central anchor."],
        current_arc_summaries=["Debt pressure (stage 1): public money risk."],
        unresolved_questions=["Who is lying about the ledger?"],
        pending_beats=["audience-rollout / ready: Seed domestic tension for Amelia and Rafael."],
        house_state=HouseStateSnapshot(
            cash_on_hand=1200,
            hourly_burn_rate=50,
            repair_backlog=8,
            inspection_risk=7,
            staff_fatigue=6,
        ),
        pacing_health=PacingHealthReport(score=58, mystery_stalled=True),
        story_governance=StoryGovernanceReport(
            viewer_value_score=60,
            hourly_progression_met=False,
        ),
        audience_control=AudienceControlReport(
            active=True,
            file_status="active",
            requests=["Build a believable baby path for Amelia and Rafael."],
            tone_dials={"romance": 9},
        ),
    )


def test_house_pressure_service_refreshes_state_and_beats() -> None:
    repository = HouseRepo()
    service = HousePressureService(repository, HousePressureConfig())
    refreshed = service.refresh(force=True)
    assert refreshed.cash_on_hand < 1500
    assert refreshed.payroll_due_in_hours <= 18
    assert refreshed.active_pressures
    assert repository.synced_beats
    assert repository.synced_beats[0].beat_type == "house-pressure"


def test_story_gravity_service_persists_state_and_dormant_threads() -> None:
    repository = GravityRepo()
    service = StoryGravityService(repository, StoryGravityConfig(refresh_interval_minutes=10))
    snapshot = service.refresh(force=True)
    assert "house-survival" in snapshot.active_axes
    assert snapshot.dormant_threads
    assert repository.synced_threads
    assert repository.saved is not None


def test_turn_critic_flags_low_value_generic_turn() -> None:
    critic = TurnCriticService(CriticConfig(repair_threshold=60, hard_fail_threshold=30))
    packet = CharacterContextPacket(
        character_slug="amelia",
        full_name="Amelia Vale",
        cultural_background="Anglo",
        public_persona="manager",
        hidden_wound="wound",
        long_term_desire="desire",
        private_fear="fear",
        family_expectations="legacy",
        conflict_style="controlled",
        privacy_boundaries="private",
        value_instincts="duty",
        emotional_expression="restrained",
        message_style="clipped",
        ensemble_role="House Manager",
        current_location="Front Desk",
        relevant_facts=["The desk drawer is full of invoices."],
        recent_messages=["Amelia: Fine."],
        live_pressures=["Card reader instability: payment tension is rising."],
        manager_directive="Keep pressure up.",
    )
    report = critic.review(
        packet=packet,
        turn=CharacterTurn(public_message="The truth is this changes everything."),
        flags=[],
    )
    assert report.should_repair is True
    assert report.score < 60


def test_simulation_lab_prefers_house_pressure_when_house_is_hot() -> None:
    report = SimulationLabService(SimulationConfig()).evaluate(_manager_packet())
    assert report.candidates[0].strategy_key == "house-pressure-first"
    assert report.systemic_risks


def test_god_ai_falls_back_to_deterministic_brief() -> None:
    repository = StrategicRepo()
    packet = _manager_packet()
    report = packet.audience_control
    service = GodAIService(
        config=GodAIConfig(enabled=True, refresh_interval_minutes=20),
        assembler=AssemblerStub(packet, repository),
        audience_control_service=AudienceStub(report),
        simulation_lab=SimulationLabService(SimulationConfig()),
        soak_audit_service=SoakAuditStub(),
        llm=FailingLLM(),
        model_name="gemma3:12b",
    )
    saved = asyncio.run(service.refresh_if_due(force=True))
    assert repository.saved is not None
    assert "maximize retention" in repository.saved.viewer_value_thesis.lower()
    assert repository.saved.current_north_star_objective
    assert repository.saved.next_twenty_four_hour_intention
    assert saved["source"] == "god-ai"


def test_god_ai_persists_provisional_brief_before_model_returns() -> None:
    repository = StrategicRepo()
    packet = _manager_packet()
    service = GodAIService(
        config=GodAIConfig(enabled=True, refresh_interval_minutes=20),
        assembler=AssemblerStub(packet, repository),
        audience_control_service=AudienceStub(packet.audience_control),
        simulation_lab=SimulationLabService(SimulationConfig()),
        soak_audit_service=SoakAuditStub(),
        llm=HangingLLM(),
        model_name="gemma3:12b",
    )

    async def run_test() -> None:
        task = asyncio.create_task(service.refresh_if_due(force=True))
        await asyncio.sleep(0)
        assert repository.saved is not None
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run_test())


def test_audience_report_can_store_rollout_beat_hints() -> None:
    report = AudienceControlReport(
        active=True,
        file_status="active",
        activated_at=isoformat(utcnow()),
        beat_hints=[
            {
                "beat_key": "baby-0",
                "beat_type": "audience-rollout",
                "objective": "Seed domestic teamwork first.",
                "ready_at": isoformat(utcnow()),
            }
        ],
    )
    assert report.beat_hints[0].beat_key == "baby-0"
