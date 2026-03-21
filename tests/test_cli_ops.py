# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from lantern_house.cli import app


def test_healthcheck_exits_cleanly_without_traceback_on_ping_failure(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(
        """
[logging]
directory = "logs"
file_name = "runtime.log"
error_file_name = "error.txt"
""".strip(),
        encoding="utf-8",
    )

    def fail_ping(self) -> None:
        raise RuntimeError("database unreachable in test")

    monkeypatch.setattr("lantern_house.cli.SessionFactory.ping", fail_ping)

    result = CliRunner().invoke(app, ["healthcheck", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "healthcheck failed: database unreachable in test" in result.output
    assert "Expected:" in result.output
    assert "Retry:" in result.output
    assert "Traceback" not in result.output

    error_path = tmp_path / "logs" / "error.txt"
    payload = json.loads(error_path.read_text(encoding="utf-8").splitlines()[-1])
    assert payload["operation"] == "cli.healthcheck"
