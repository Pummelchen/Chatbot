# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from pathlib import Path

from lantern_house.services.seed_loader import StorySeedLoader


def test_story_seed_meets_requirements() -> None:
    loader = StorySeedLoader.__new__(StorySeedLoader)
    loader.seed_file = "story_bible.yaml"
    payload = loader.load_seed_payload()
    assert len(payload["characters"]) == 6
    assert len(payload["secrets"]) >= 12
    assert len(payload["future_plot_hooks"]) >= 20
    assert len(payload["recap_examples"]) == 3


def test_story_seed_loader_can_read_custom_local_seed(tmp_path: Path) -> None:
    seed_path = tmp_path / "custom_story.yaml"
    seed_path.write_text("title: Custom House\ncharacters: []\n", encoding="utf-8")

    loader = StorySeedLoader.__new__(StorySeedLoader)
    loader.seed_file = str(seed_path)

    payload = loader.load_seed_payload()

    assert payload["title"] == "Custom House"
