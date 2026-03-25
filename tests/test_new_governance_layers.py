# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from pathlib import Path

from lantern_house.config import (
    BroadcastAssetsConfig,
    SeasonPlannerConfig,
    TurnSelectionConfig,
    ViewerSignalsConfig,
    WorldTrackingConfig,
)
from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    HighlightPackageSnapshot,
    HourlyProgressLedgerSnapshot,
    ManagerContextPacket,
    MonetizationPackageSnapshot,
    PacingHealthReport,
    StoryGovernanceReport,
    StrategicBriefSnapshot,
    TurnCriticReport,
)
from lantern_house.domain.enums import EventType
from lantern_house.services.broadcast_assets import BroadcastAssetService
from lantern_house.services.season_planner import SeasonPlannerService
from lantern_house.services.turn_selection import EvaluatedTurnCandidate, TurnSelectionService
from lantern_house.services.viewer_signals import ViewerSignalIngestionService
from lantern_house.services.world_tracking import (
    WorldTrackingService,
    build_room_occupancy_digest,
)
from lantern_house.utils.time import utcnow


class ViewerSignalRepo:
    def __init__(self) -> None:
        self.runtime = {"metadata": {}}
        self.signals = []

    def get_run_state(self):
        return self.runtime

    def ensure_run_state(self):
        return self.runtime

    def merge_runtime_metadata(self, payload, *, now=None):
        self.runtime["metadata"].update(payload)
        return self.runtime["metadata"]

    def sync_viewer_signals(self, *, signals, now=None):
        self.signals = list(signals)
        return self.signals

    def list_active_viewer_signals(self, *, limit=8):
        return self.signals[:limit]


class SeasonRepo:
    def __init__(self) -> None:
        self.saved = []

    def list_programming_grid_slots(self, *, horizon=None, limit=10):
        rows = self.saved
        if horizon is not None:
            rows = [item for item in rows if item.horizon == horizon]
        return rows[:limit]

    def list_recent_events(self, *, hours=24, limit=20, minimum_significance=1):
        now = utcnow()
        return [
            type(
                "Event",
                (),
                {
                    "event_type": "clue" if hours <= 24 * 30 else "conflict",
                    "title": "Copied codicil resurfaces",
                    "significance": 8,
                    "created_at": now,
                },
            )()
        ]

    def list_open_arcs(self, *, limit=8):
        return [
            type("Arc", (), {"title": "Who Owns Lantern House?"})(),
            type("Arc", (), {"title": "What Happened to Evelyn Vale?"})(),
        ]

    def get_world_state_snapshot(self):
        return {
            "metadata": {
                "future_recurring_character": {
                    "full_name": "Ren Akiyama",
                }
            }
        }

    def sync_programming_grid_slots(self, *, slots, now=None):
        self.saved = list(slots)
        return self.saved


class BroadcastRepo:
    def __init__(self) -> None:
        self.saved = None

    def record_broadcast_asset(self, *, package, now=None):
        self.saved = package
        return package


class WorldTrackingRepo:
    def __init__(self) -> None:
        self.timeline = []
        self.possessions = []

    def list_character_positions(self):
        return [
            {
                "slug": "amelia",
                "full_name": "Amelia Vale",
                "location_slug": "front-desk",
                "location_name": "Front Desk",
            },
            {
                "slug": "rafael",
                "full_name": "Rafael Costa",
                "location_slug": "boiler-room",
                "location_name": "Boiler Room",
            },
        ]

    def list_story_objects(self):
        return [
            {
                "slug": "lantern-wing-key",
                "name": "Lantern Wing Key",
                "location_slug": "front-desk",
                "location_name": "Front Desk",
                "holder_character_slug": None,
                "possession_status": "room",
            }
        ]

    def get_house_state_snapshot(self):
        return type(
            "HouseState",
            (),
            {
                "payroll_due_in_hours": 24,
                "hourly_burn_rate": 40,
                "cash_on_hand": 600,
                "repair_backlog": 6,
                "weather_pressure": 7,
                "active_pressures": [],
            },
        )()

    def record_timeline_facts(self, *, facts, now=None):
        self.timeline.extend(facts)
        return facts

    def sync_object_possessions(self, *, snapshots, now=None):
        self.possessions = list(snapshots)
        return self.possessions

    def list_locations(self):
        return [
            {"slug": "front-desk", "name": "Front Desk"},
            {"slug": "roof-walk", "name": "Roof Walk"},
        ]


def test_viewer_signal_ingestion_parses_local_yaml(tmp_path: Path) -> None:
    signal_file = tmp_path / "viewer_signals.yaml"
    signal_file.write_text(
        """
enabled: true
signals:
  - signal_type: theory_burst
    subject: lucia-ledger
    intensity: 8
    retention_impact: 9
    summary: Ledger theory is spiking.
""".strip(),
        encoding="utf-8",
    )
    repo = ViewerSignalRepo()
    service = ViewerSignalIngestionService(
        ViewerSignalsConfig(source_file_path=str(signal_file)),
        repo,
    )

    signals = service.refresh_if_due(force=True)

    assert len(signals) == 1
    assert signals[0].signal_type == "theory-burst"
    assert repo.runtime["metadata"]["viewer_signals"]["signal_count"] == 1


def test_season_planner_creates_near_and_long_horizon_slots() -> None:
    repo = SeasonRepo()
    service = SeasonPlannerService(repo, SeasonPlannerConfig())

    slots = service.refresh(now=utcnow(), force=True)

    assert any(slot.horizon == "season-30d" for slot in slots)
    assert any(slot.horizon == "season-90d" for slot in slots)
    assert any("Ren Akiyama" in slot.objective for slot in slots)


def test_world_tracking_captures_presence_and_possession_claims() -> None:
    repo = WorldTrackingRepo()
    service = WorldTrackingService(repo, WorldTrackingConfig())

    service.capture_turn(
        packet=CharacterContextPacket(
            character_slug="amelia",
            full_name="Amelia Vale",
            cultural_background="Anglo",
            public_persona="manager",
            hidden_wound="loss",
            long_term_desire="save the house",
            private_fear="collapse",
            family_expectations="protect the family",
            conflict_style="controlled",
            privacy_boundaries="tight",
            value_instincts="duty first",
            emotional_expression="restrained",
            message_style="clipped",
            ensemble_role="House Manager",
            current_location="Front Desk",
            manager_directive="Keep the room unstable.",
        ),
        turn=CharacterTurn(
            public_message="I have the lantern wing key, and I was on the Roof Walk before this.",
            event_candidates=[],
        ),
        events=[],
        now=utcnow(),
    )

    assert any(fact.fact_type == "presence" for fact in repo.timeline)
    assert any(fact.fact_type == "alibi" for fact in repo.timeline)
    assert repo.possessions[0].holder_character_slug == "amelia"


def test_broadcast_asset_service_builds_export_package() -> None:
    repo = BroadcastRepo()
    service = BroadcastAssetService(repo, BroadcastAssetsConfig(min_asset_score=60))

    package = service.maybe_record(
        message_id=12,
        speaker_slug="lucia",
        turn=CharacterTurn(
            public_message="If the codicil is fake, someone wanted the house buried."
        ),
        report=TurnCriticReport(
            score=84,
            clip_value=8,
            quote_worthiness=8,
            fandom_discussion_value=8,
            novelty=7,
        ),
        highlight_package=HighlightPackageSnapshot(
            message_id=12,
            speaker_slug="lucia",
            title="Lucía just handed viewers a new theory",
            hook_line="If the codicil is fake, someone wanted the house buried.",
            quote_line="If the codicil is fake, someone wanted the house buried.",
            summary_blurb="The codicil may have been staged.",
            theory_angle="Who forged the codicil?",
            score=82,
        ),
        monetization_package=MonetizationPackageSnapshot(
            message_id=12,
            speaker_slug="lucia",
            primary_title="Lucía just changed the ownership war",
            hook_line="If the codicil is fake, someone wanted the house buried.",
            quote_line="If the codicil is fake, someone wanted the house buried.",
            summary_blurb="The codicil may have been staged.",
            recap_blurb="Ownership pressure just turned into accusation.",
            chapter_label="Ownership turn",
            comment_prompt="Who forged the codicil?",
            theory_angle="Who forged the codicil?",
            faction_labels=["theory"],
            tags=["lantern-house", "fan-theory"],
            score=90,
        ),
        strategic_brief=StrategicBriefSnapshot(
            title="Push theory value",
            viewer_value_thesis="Theory value is high when paperwork turns personal.",
            next_one_hour_intention="Escalate the paperwork war.",
        ),
        viewer_signals=[],
        now=utcnow(),
    )

    assert package is not None
    assert repo.saved is not None
    assert package.clip_manifest
    assert package.long_description


def test_turn_selection_prefers_candidate_that_fits_hourly_need() -> None:
    service = TurnSelectionService(TurnSelectionConfig())
    packet = ManagerContextPacket(
        title="Lantern House",
        scene_objective="Push the next hour forward.",
        scene_location="Front Desk",
        emotional_temperature=7,
        pacing_health=PacingHealthReport(score=52),
        story_governance=StoryGovernanceReport(
            viewer_value_score=50,
            cliffhanger_pressure_low=True,
        ),
        hourly_ledger=HourlyProgressLedgerSnapshot(contract_met=False, evidence_shift_count=0),
    )
    weak = EvaluatedTurnCandidate(
        turn=CharacterTurn(public_message="Fine.", event_candidates=[]),
        critic_report=TurnCriticReport(
            score=62,
            clip_value=4,
            quote_worthiness=4,
            fandom_discussion_value=4,
            novelty=4,
        ),
        events=[],
        flags=[],
        stats=None,
        degraded_mode=False,
        candidate_index=0,
    )
    strong = EvaluatedTurnCandidate(
        turn=CharacterTurn(
            public_message="If the codicil is fake, who wanted the house buried?",
            new_questions=["If the codicil is fake, who wanted the house buried?"],
        ),
        critic_report=TurnCriticReport(
            score=78,
            clip_value=8,
            quote_worthiness=8,
            fandom_discussion_value=8,
            novelty=7,
        ),
        events=[
            type("Event", (), {"event_type": EventType.CLUE})(),
        ],
        flags=[],
        stats=None,
        degraded_mode=False,
        candidate_index=1,
    )

    chosen = service.choose_best(manager_packet=packet, candidates=[weak, strong])

    assert chosen.turn.public_message.startswith("If the codicil is fake")


def test_turn_selection_requires_candidate_input() -> None:
    service = TurnSelectionService(TurnSelectionConfig())
    packet = ManagerContextPacket(
        title="Lantern House",
        scene_objective="Keep moving.",
        scene_location="Front Desk",
        emotional_temperature=5,
        pacing_health=PacingHealthReport(score=60),
    )

    try:
        service.choose_best(manager_packet=packet, candidates=[])
    except ValueError as exc:
        assert "at least one" in str(exc)
    else:
        raise AssertionError("choose_best should reject empty candidate lists")


def test_room_occupancy_digest_skips_unknown_locations() -> None:
    digest = build_room_occupancy_digest(
        [
            {"slug": "amelia", "location_name": "Front Desk"},
            {"slug": "rafael", "location_name": "Unknown"},
            {"slug": "ayu", "location_name": ""},
        ]
    )

    assert digest == ["Front Desk: amelia"]
