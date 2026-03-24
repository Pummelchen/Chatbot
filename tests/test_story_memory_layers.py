# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import asyncio
from datetime import timedelta

from lantern_house.config import (
    CanonConfig,
    HighlightsConfig,
    HourlyBeatLedgerConfig,
    SoakAuditConfig,
)
from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    EventCandidate,
    EventView,
    HighlightPackageSnapshot,
    ManagerContextPacket,
    PacingHealthReport,
    SoakAuditSnapshot,
    StrategicBriefSnapshot,
    TurnCriticReport,
)
from lantern_house.domain.enums import EventType
from lantern_house.services.canon import CanonDistillationService
from lantern_house.services.character import CharacterService
from lantern_house.services.highlights import HighlightPackagingService
from lantern_house.services.hourly_ledger import HourlyBeatLedgerService
from lantern_house.services.soak_audit import SoakAuditService
from lantern_house.utils.time import utcnow


class LedgerRepo:
    def __init__(self, now) -> None:
        self.saved = None
        self.events = [
            EventView(
                event_type="clue",
                title="Copied ledger page surfaces",
                details="A copied ledger page appears under the desk.",
                significance=8,
                payload={},
                created_at=now - timedelta(minutes=12),
            ),
            EventView(
                event_type="financial",
                title="Payroll panic leaks out",
                details="The payroll gap becomes public.",
                significance=7,
                payload={},
                created_at=now - timedelta(minutes=9),
            ),
        ]

    def list_recent_events(self, **kwargs):
        return self.events

    def save_hourly_progress_ledger(self, *, snapshot, now=None):
        self.saved = snapshot
        return snapshot


class CanonRepo:
    def __init__(self) -> None:
        self.saved: list = []

    def get_world_state_snapshot(self):
        return {
            "title": "Lantern House",
            "unresolved_questions": ["Who copied the registry page?"],
            "metadata": {},
        }

    def get_scene_snapshot(self):
        return {"objective": "Hold the lobby together."}

    def get_house_state_snapshot(self):
        return type(
            "HouseState",
            (),
            {
                "active_pressures": [
                    type(
                        "Pressure",
                        (),
                        {
                            "label": "Payroll cliff",
                            "recommended_move": "Make payroll fear public.",
                            "summary": "Payroll is close.",
                        },
                    )()
                ]
            },
        )()

    def get_latest_strategic_brief(self, **kwargs):
        return StrategicBriefSnapshot(
            reveals_forbidden_for_now=["Do not solve Evelyn's disappearance outright."]
        )

    def get_story_gravity_state_snapshot(self):
        return type(
            "Gravity", (), {"manager_guardrails": ["The house itself must always matter."]}
        )()

    def get_relationship_map(self):
        return ["amelia<->rafael: trust 8, desire 8, suspicion 4."]

    def list_open_arcs(self, **kwargs):
        return [
            type(
                "Arc",
                (),
                {
                    "title": "What Happened to Evelyn Vale?",
                    "summary": "The central mystery is still active.",
                },
            )()
        ]

    def list_recent_events(self, **kwargs):
        now = utcnow()
        return [
            EventView(
                event_type="clue",
                title="The ledger copy matters",
                details="A copied ledger page now points at a second key.",
                significance=7,
                payload={},
                created_at=now - timedelta(minutes=10),
            )
        ]

    def list_recent_summaries(self, **kwargs):
        return [
            type(
                "Summary",
                (),
                {"content": "Payroll fear and the copied ledger both escalated."},
            )()
        ]

    def save_canon_capsule(self, *, snapshot, now=None):
        self.saved.append(snapshot)
        return snapshot


class HighlightRepo:
    def __init__(self) -> None:
        self.saved: HighlightPackageSnapshot | None = None

    def record_highlight_package(self, *, package, now=None):
        self.saved = package
        return package


class SoakRepo:
    def __init__(self) -> None:
        self.saved: SoakAuditSnapshot | None = None

    def get_latest_soak_audit(self):
        return None

    def list_recent_clip_value_scores(self, *, limit=6):
        return [{"clip_value": 4}, {"clip_value": 5}]

    def record_soak_audit_run(self, *, snapshot, now=None):
        self.saved = snapshot
        return snapshot


class RepairLLM:
    async def generate_json(self, **kwargs):
        return (
            {
                "public_message": "Watch the desk drawer before you accuse the wrong person.",
                "thought_pulse": None,
                "event_candidates": [
                    {
                        "event_type": "clue",
                        "title": "Desk drawer warning",
                        "details": "A specific object turns the accusation sharper.",
                        "significance": 7,
                    }
                ],
                "relationship_updates": [],
                "new_questions": ["Who moved the copied page before dawn?"],
                "answered_questions": [],
                "tone": "sharp",
                "silence": False,
            },
            None,
        )


class FixedSimulationLab:
    def evaluate(self, context, *, horizon_hours=None, turns_per_hour=None):
        from lantern_house.domain.contracts import SimulationCandidateScore, SimulationLabReport

        horizon = horizon_hours or 24
        winner = "mystery-evidence-first" if horizon >= 72 else "house-pressure-first"
        return SimulationLabReport(
            horizon_hours=horizon,
            turns_per_hour=turns_per_hour or 90,
            candidates=[
                SimulationCandidateScore(
                    strategy_key=winner,
                    score=80,
                    value_profile={},
                    rationale=["test"],
                    next_hour_focus="Push the ledger copy.",
                    six_hour_path="Escalate the evidence trail.",
                )
            ],
            systemic_risks=["The last hour under-delivered on progression."],
            recommended_focus=["Push the ledger copy."],
            ranked_strategy_keys=[winner],
        )


def test_hourly_beat_ledger_tracks_hard_contract() -> None:
    now = utcnow().replace(minute=30, second=0, microsecond=0)
    service = HourlyBeatLedgerService(LedgerRepo(now), HourlyBeatLedgerConfig())
    snapshot = service.refresh(now=now)
    assert snapshot.contract_met is True
    assert snapshot.evidence_shift_count == 1
    assert snapshot.debt_shift_count == 1


def test_canon_distillation_builds_multi_window_capsules() -> None:
    repo = CanonRepo()
    service = CanonDistillationService(
        repo,
        CanonConfig(windows=["1h", "24h"], max_items_per_section=3),
    )
    capsules = service.refresh(now=utcnow())
    assert len(capsules) == 2
    assert capsules[0].headline
    assert capsules[0].protected_truths


def test_highlight_packaging_records_clip_ready_turn() -> None:
    repo = HighlightRepo()
    service = HighlightPackagingService(repo, HighlightsConfig(clip_threshold=7, quote_threshold=7))
    package = service.maybe_record(
        message_id=42,
        speaker_slug="amelia",
        turn=CharacterTurn(
            public_message="Tell me who touched the drawer before payroll does.",
            event_candidates=[
                EventCandidate(
                    event_type=EventType.FINANCIAL,
                    title="Payroll threat lands",
                    details="Money pressure becomes personal.",
                    significance=8,
                )
            ],
        ),
        report=TurnCriticReport(
            score=82,
            clip_value=8,
            quote_worthiness=8,
            fandom_discussion_value=7,
            novelty=7,
        ),
        strategic_brief=StrategicBriefSnapshot(title="Protect the house through pressure"),
        now=utcnow(),
    )
    assert package is not None
    assert repo.saved is not None
    assert "Amelia" in package.title


def test_soak_audit_scores_long_run_risks() -> None:
    repo = SoakRepo()
    packet = ManagerContextPacket(
        title="Lantern House",
        scene_objective="Hold the lobby together.",
        scene_location="Front Desk",
        emotional_temperature=6,
        pacing_health=PacingHealthReport(score=55, repetitive=True, romance_stalled=True),
    )
    service = SoakAuditService(
        repo,
        FixedSimulationLab(),
        SoakAuditConfig(horizons_hours=[24, 72], turns_per_hour=90, refresh_interval_minutes=30),
    )
    snapshot = service.refresh_if_due(packet, now=utcnow(), force=True)
    assert snapshot is not None
    assert snapshot.progression_miss_risk >= 40
    assert snapshot.strategy_lock_risk >= 20


def test_character_repair_model_salvages_turn() -> None:
    service = CharacterService(RepairLLM(), "gemma3:1b", "gemma3:1b")
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
        recent_messages=["Rafael: Stop circling."],
        live_pressures=["Payroll cliff: payment tension is rising."],
        story_memory_capsule=["24h: Payroll fear and the copied ledger both escalated."],
        manager_directive="Keep pressure up.",
    )
    turn, _stats, degraded = asyncio.run(
        service.repair_with_model(
            packet=packet,
            original_turn=CharacterTurn(public_message="The truth is this changes everything."),
            critic_report=TurnCriticReport(
                score=32,
                reasons=["The turn is generic.", "The turn is not grounded."],
            ),
            thought_pulse_allowed=False,
        )
    )
    assert degraded is False
    assert "desk drawer" in turn.public_message.lower()
    assert turn.new_questions == ["Who moved the copied page before dawn?"]
