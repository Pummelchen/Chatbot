from __future__ import annotations

from pathlib import Path

from lantern_house.config import AudienceConfig
from lantern_house.services.audience import AudienceControlService


class FakeRepository:
    def __init__(self) -> None:
        self.metadata: dict = {}

    def get_run_state(self):
        return {"metadata": dict(self.metadata)}

    def merge_runtime_metadata(self, payload: dict, *, now=None):
        self.metadata.update(payload)
        return dict(self.metadata)


def test_audience_control_parses_update_file(tmp_path: Path) -> None:
    update_file = tmp_path / "update.txt"
    update_file.write_text(
        """
enabled: true
change_id: "vote-1"
source: "YouTube vote"
priority: 9
rollout:
  full_integration_hours: 24
core_settings:
  romance: 9
  twists: 7
relationship_moves:
  - pair: ["Amelia Vale", "Rafael Costa"]
    direction: "eventual_baby_arc"
    intensity_target: 9
    pace: "very slow"
    start_with: "repair trust first"
    avoid: "instant pregnancy"
story_requests:
  must_happen:
    - "Build a believable path toward Amelia and Rafael choosing a baby together."
""".strip(),
        encoding="utf-8",
    )
    service = AudienceControlService(
        AudienceConfig(update_file_path=str(update_file), check_interval_minutes=10),
        FakeRepository(),
    )
    report = service.refresh_if_due(force=True)
    assert report.active is True
    assert report.change_id == "vote-1"
    assert report.tone_dials["romance"] == 9
    assert report.full_integration_hours == 24
    assert any("eventual_baby_arc" in item for item in report.requests + report.directives)


def test_audience_control_keeps_last_good_state_on_parse_error(tmp_path: Path) -> None:
    update_file = tmp_path / "update.txt"
    repository = FakeRepository()
    service = AudienceControlService(
        AudienceConfig(update_file_path=str(update_file), check_interval_minutes=10),
        repository,
    )
    update_file.write_text(
        'enabled: true\nstory_requests:\n  must_happen:\n    - "Keep Hana dangerous."\n',
        encoding="utf-8",
    )
    first = service.refresh_if_due(force=True)
    assert first.active is True

    update_file.write_text("enabled: true\nstory_requests: [\n", encoding="utf-8")
    second = service.refresh_if_due(force=True)
    assert second.file_status == "invalid"
    assert any("Keep Hana dangerous" in item for item in second.requests)
