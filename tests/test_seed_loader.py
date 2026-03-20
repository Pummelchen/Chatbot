from __future__ import annotations

from lantern_house.services.seed_loader import StorySeedLoader


def test_story_seed_meets_requirements() -> None:
    loader = StorySeedLoader.__new__(StorySeedLoader)
    payload = loader.load_seed_payload()
    assert len(payload["characters"]) == 6
    assert len(payload["secrets"]) >= 12
    assert len(payload["future_plot_hooks"]) >= 20
    assert len(payload["recap_examples"]) == 3
