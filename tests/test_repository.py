from __future__ import annotations

from datetime import timedelta

from sqlalchemy import create_engine

from lantern_house.db import models
from lantern_house.db.base import Base
from lantern_house.db.repository import StoryRepository
from lantern_house.db.session import SessionFactory
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
