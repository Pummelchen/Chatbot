# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.domain.contracts import EventCandidate, StoryArcSnapshot
from lantern_house.domain.enums import EventType
from lantern_house.services.progression import StoryProgressionService


def test_story_progression_matches_finance_arc_and_surfaces_question() -> None:
    service = StoryProgressionService()
    plan = service.plan(
        arcs=[
            StoryArcSnapshot(
                slug="forced-sale",
                title="The Forced Sale",
                arc_type="finance",
                summary="Debt pressure keeps turning fractures into bad bargains.",
                stage_index=0,
                reveal_ladder=["A due notice lands in public view."],
                unresolved_questions=["How much of the debt is real?"],
                payoff_window="weeks to months",
                pressure_score=8,
            )
        ],
        events=[
            EventCandidate(
                event_type=EventType.FINANCIAL,
                title="Blackwake demand becomes public",
                details="A debt notice is slapped onto the front desk ledger.",
                significance=8,
            )
        ],
    )
    assert len(plan.arc_updates) == 1
    update = plan.arc_updates[0]
    assert update.slug == "forced-sale"
    assert update.pressure_score > 8
    assert "How much of the debt is real?" in update.surfaced_questions
    assert plan.archived_threads == []


def test_story_progression_advances_stage_after_enough_points() -> None:
    service = StoryProgressionService()
    plan = service.plan(
        arcs=[
            StoryArcSnapshot(
                slug="lantern-archive",
                title="The Lantern Archive",
                arc_type="mystery",
                summary="The missing archive could explain the debt and the disappearance.",
                stage_index=0,
                reveal_ladder=[
                    "The lantern-wing key matters.",
                    "A registry alias matches someone still alive.",
                ],
                unresolved_questions=["Where is Evelyn's archive now?"],
                payoff_window="continuous",
                pressure_score=9,
                metadata={"progress_points": 7},
            )
        ],
        events=[
            EventCandidate(
                event_type=EventType.CLUE,
                title="The lantern wing key reappears",
                details="A brass key and registry alias surface together.",
                significance=9,
            )
        ],
    )
    assert plan.arc_updates[0].stage_index == 1
    assert (
        plan.arc_updates[0].metadata["active_beat"]
        == "A registry alias matches someone still alive."
    )
    assert plan.archived_threads == [
        "The Lantern Archive: A registry alias matches someone still alive."
    ]
