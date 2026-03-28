# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from datetime import timedelta

from lantern_house.config import (
    DailyLifeConfig,
    InferenceGovernorConfig,
    PayoffDebtConfig,
    ShadowReplayConfig,
    ViewerSignalsConfig,
    YouTubeAdapterConfig,
)
from lantern_house.domain.contracts import (
    CharacterContextPacket,
    LoadProfileSnapshot,
    TurnCriticReport,
    YouTubeAdapterStateSnapshot,
)
from lantern_house.quality.pacing import ContinuityGuard
from lantern_house.services.daily_life import DailyLifeSchedulerService
from lantern_house.services.inference_governor import InferenceGovernorService
from lantern_house.services.payoff_debt import PayoffDebtLedgerService
from lantern_house.services.shadow_replay import ShadowReplayService
from lantern_house.services.youtube_adapter import YouTubeSignalAdapterService
from lantern_house.utils.time import utcnow


def test_inference_governor_disables_expensive_roles_under_critical_load() -> None:
    service = InferenceGovernorService(InferenceGovernorConfig())
    load = LoadProfileSnapshot(load_tier="critical", average_latency_ms=22000)

    god_ai = service.policy_for(role="god_ai", load_profile=load, now=utcnow())
    repair = service.policy_for(role="repair", load_profile=load, now=utcnow())
    character = service.policy_for(role="character", load_profile=load, now=utcnow())

    assert god_ai.allow_model_call is False
    assert repair.allow_model_call is False
    assert character.allow_model_call is True
    assert character.timeout_seconds <= repair.timeout_seconds * 2


class DailyLifeRepo:
    def __init__(self) -> None:
        self.synced_slots = []
        self.synced_beats = []

    def list_daily_life_schedule_slots(self, **kwargs):
        return []

    def get_world_state_snapshot(self):
        return {"current_story_day": 3}

    def get_house_state_snapshot(self):
        return type(
            "House",
            (),
            {
                "payroll_due_in_hours": 18,
                "reputation_risk": 6,
                "repair_backlog": 7,
                "weather_pressure": 7,
                "inspection_risk": 5,
            },
        )()

    def list_characters(self):
        return [
            {
                "slug": "amelia",
                "full_name": "Amelia Vale",
                "ensemble_role": "House Manager",
                "message_style": "controlled",
            },
            {
                "slug": "rafael",
                "full_name": "Rafael Costa",
                "ensemble_role": "Night Fixer",
                "message_style": "dry",
            },
        ]

    def list_active_guest_profiles(self, **kwargs):
        return []

    def list_locations(self):
        return [
            {"slug": "front-desk", "name": "Front Desk"},
            {"slug": "lantern-wing", "name": "Lantern Wing"},
            {"slug": "roof-access", "name": "Roof Access"},
        ]

    def sync_daily_life_schedule_slots(self, *, slots, now=None):
        self.synced_slots = slots
        return slots

    def sync_beats(self, *, beat_type, items, source_key, now=None):
        self.synced_beats = items
        return []


def test_daily_life_scheduler_generates_slots_and_beats() -> None:
    repo = DailyLifeRepo()
    service = DailyLifeSchedulerService(
        repo,
        DailyLifeConfig(max_active_slots=6, max_pending_beats=3),
    )

    slots = service.refresh(now=utcnow(), force=True)

    assert slots
    assert any(slot.participant_slug == "amelia" for slot in slots)
    assert repo.synced_beats
    assert repo.synced_beats[0].beat_type == "daily-life"


def test_daily_life_scheduler_stays_inert_when_disabled_without_existing_state() -> None:
    repo = DailyLifeRepo()
    service = DailyLifeSchedulerService(repo, DailyLifeConfig(enabled=False))

    slots = service.refresh(now=utcnow())

    assert slots == []
    assert repo.synced_slots == []
    assert repo.synced_beats == []


class PayoffRepo:
    def __init__(self) -> None:
        self.synced_items = []
        self.synced_beats = []

    def list_payoff_debts(self, **kwargs):
        return []

    def get_world_state_snapshot(self):
        return {"unresolved_questions": ["Who hid the ledger?", "Why did Hana return?"]}

    def list_dormant_threads(self, **kwargs):
        now = utcnow() - timedelta(hours=60)
        return [
            type(
                "Thread",
                (),
                {
                    "thread_key": "ledger-envelope",
                    "summary": "The missing envelope still has not paid off.",
                    "source": "world-memory",
                    "heat": 7,
                    "last_seen_at": now,
                },
            )()
        ]

    def list_active_rollout_requests(self, **kwargs):
        return [
            {
                "summary": "Amelia and Rafael should move closer to a confession.",
                "request_type": "romance",
                "priority": 8,
                "directives": ["slow burn"],
                "activated_at": utcnow(),
            }
        ]

    def list_characters(self):
        return [{"slug": "amelia"}, {"slug": "rafael"}]

    def list_relationship_snapshots(self, slug):
        if slug != "amelia":
            return []
        return [
            type(
                "Rel",
                (),
                {
                    "counterpart_slug": "rafael",
                    "trust_score": 5,
                    "desire_score": 8,
                    "suspicion_score": 6,
                    "summary": "Too much history, not enough honesty.",
                },
            )()
        ]

    def list_pending_beats(self, **kwargs):
        return []

    def sync_payoff_debts(self, *, items, now=None):
        self.synced_items = items
        return items

    def sync_beats(self, *, beat_type, items, source_key, now=None):
        self.synced_beats = items
        return []


def test_payoff_debt_ledger_creates_mystery_relationship_and_rollout_debts() -> None:
    repo = PayoffRepo()
    service = PayoffDebtLedgerService(repo, PayoffDebtConfig(max_active_debts=8))

    items = service.refresh(now=utcnow(), force=True)

    keys = {item.debt_type for item in items}
    assert "mystery-question" in keys
    assert "relationship-faultline" in keys
    assert "audience-rollout" in keys
    assert repo.synced_beats


def test_payoff_debt_ledger_stays_inert_when_disabled_without_existing_state() -> None:
    repo = PayoffRepo()
    service = PayoffDebtLedgerService(repo, PayoffDebtConfig(enabled=False))

    items = service.refresh(now=utcnow())

    assert items == []
    assert repo.synced_items == []
    assert repo.synced_beats == []


class AdapterRepo:
    def __init__(self) -> None:
        self.saved: YouTubeAdapterStateSnapshot | None = None

    def get_youtube_adapter_state(self) -> YouTubeAdapterStateSnapshot:
        return self.saved or YouTubeAdapterStateSnapshot()

    def save_youtube_adapter_state(self, *, snapshot, now=None):
        self.saved = snapshot
        return snapshot


def test_youtube_adapter_tracks_offsets_and_derives_state(tmp_path) -> None:
    harvest_dir = tmp_path / "signals"
    harvest_dir.mkdir()
    (harvest_dir / "comments.jsonl").write_text(
        '{"text":"Amelia and Rafael are everything"}\n'
        '{"text":"I think Hana knows about the ledger"}\n',
        encoding="utf-8",
    )
    (harvest_dir / "clips.jsonl").write_text(
        '{"title":"Ledger fight clip","score":88}\n',
        encoding="utf-8",
    )
    (harvest_dir / "retention.jsonl").write_text(
        '{"minute":12,"drop_percent":18,"reason":"slow scene"}\n',
        encoding="utf-8",
    )
    (harvest_dir / "live_chat.jsonl").write_text(
        '{"message":"amelia x rafael endgame"}\n',
        encoding="utf-8",
    )
    viewer_cfg = ViewerSignalsConfig(harvest_directory_path=str(harvest_dir))
    repo = AdapterRepo()
    service = YouTubeSignalAdapterService(YouTubeAdapterConfig(), viewer_cfg, repo)

    bundle = service.harvest(now=utcnow(), force=True)

    assert bundle.comments
    assert bundle.state.active_themes
    assert bundle.state.ship_heat
    assert bundle.state.retention_alerts
    assert bundle.state.clip_spikes
    assert repo.saved is not None


def test_youtube_adapter_advances_offsets_without_skipping_backlog(tmp_path) -> None:
    harvest_dir = tmp_path / "signals"
    harvest_dir.mkdir()
    (harvest_dir / "comments.jsonl").write_text(
        "\n".join(
            f'{{"text":"comment {index} about amelia and rafael"}}' for index in range(5)
        )
        + "\n",
        encoding="utf-8",
    )
    for file_name in ("clips.jsonl", "retention.jsonl", "live_chat.jsonl"):
        (harvest_dir / file_name).write_text("", encoding="utf-8")
    viewer_cfg = ViewerSignalsConfig(harvest_directory_path=str(harvest_dir))
    repo = AdapterRepo()
    service = YouTubeSignalAdapterService(
        YouTubeAdapterConfig(max_records_per_file=2),
        viewer_cfg,
        repo,
    )

    first = service.harvest(now=utcnow(), force=True)
    second = service.harvest(now=utcnow(), force=True)
    third = service.harvest(now=utcnow(), force=True)

    assert len(first.comments) == 2
    assert len(second.comments) == 2
    assert len(third.comments) == 1
    assert repo.saved is not None
    assert repo.saved.source_offsets["comments"] == 5


class ShadowReplayRepo:
    def __init__(self) -> None:
        self.snapshot = None

    def list_recent_chat_rows(self, **kwargs):
        return [
            {
                "id": 1,
                "tick_no": 7,
                "speaker_slug": "amelia",
                "speaker_label": "Amelia",
                "content": "The ledger was never in the drawer.",
                "created_at": utcnow(),
                "hidden_metadata": {
                    "tone": "guarded",
                    "new_questions": [],
                    "answered_questions": [],
                },
            }
        ]

    def get_latest_manager_directive(self):
        return {
            "objective": "Test replay",
            "per_character": {},
            "active_character_slugs": ["amelia"],
        }

    def list_recent_public_turn_reviews(self, **kwargs):
        return [{"message_id": 1, "critic_score": 92}]

    def record_shadow_replay_run(self, *, snapshot, now=None):
        self.snapshot = snapshot
        return snapshot


class ShadowAssembler:
    def build_character_packet(self, speaker_slug, directive):
        return CharacterContextPacket(
            character_slug=speaker_slug,
            full_name="Amelia Vale",
            cultural_background="Anglo",
            public_persona="steady",
            hidden_wound="loss",
            long_term_desire="save the house",
            private_fear="collapse",
            family_expectations="hold the line",
            conflict_style="controlled",
            privacy_boundaries="tight",
            value_instincts="duty first",
            emotional_expression="guarded",
            message_style="measured",
            ensemble_role="House Manager",
            current_location="Front Desk",
            manager_directive="Test replay",
        )


class ShadowExtractor:
    def extract(self, *, speaker_slug, turn):
        return []


class ShadowCanon:
    def review(self, *, packet, turn, events):
        return type("Report", (), {"additional_flags": [], "requires_repair": False})()


class WeakCritic:
    def review(self, *, packet, turn, flags):
        return TurnCriticReport(score=48, reasons=["too weak"])


def test_shadow_replay_detects_regression() -> None:
    repo = ShadowReplayRepo()
    service = ShadowReplayService(
        repository=repo,
        assembler=ShadowAssembler(),
        event_extractor=ShadowExtractor(),
        canon_court_service=ShadowCanon(),
        critic_service=WeakCritic(),
        continuity_guard=ContinuityGuard(),
        config=ShadowReplayConfig(recent_turn_limit=2, max_reported_regressions=2),
    )

    snapshot = service.run(now=utcnow(), changed_files=["src/lantern_house/services/manager.py"])

    assert snapshot.status == "failed"
    assert snapshot.regression_count >= 1
    assert repo.snapshot is not None
