from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from lantern_house.config import (
    FailSafeConfig,
    LoggingConfig,
    build_hot_patch_config,
    load_config,
)
from lantern_house.logging import configure_logging
from lantern_house.runtime.failsafe import FailSafeExecutor


def test_failsafe_uses_last_good_value_and_logs_error_context(tmp_path: Path) -> None:
    configure_logging(
        LoggingConfig(
            directory=str(tmp_path),
            file_name="runtime.log",
            error_file_name="error.txt",
        )
    )
    executor = FailSafeExecutor(FailSafeConfig())

    ok = executor.call("demo.operation", lambda: {"status": "ok"})
    assert ok.ok is True
    assert ok.value == {"status": "ok"}

    def explode():
        raise RuntimeError("boom")

    failed = executor.call(
        "demo.operation",
        explode,
        context={"phase": "unit-test"},
        expected_inputs=["A callable that returns a status mapping."],
        retry_advice="Try the operation again after fixing the failing dependency.",
    )

    assert failed.ok is False
    assert failed.value == {"status": "ok"}
    assert failed.used_fallback is True
    assert failed.failure is not None
    assert "Expected:" in failed.failure.caller_message()

    payload = json.loads((tmp_path / "error.txt").read_text(encoding="utf-8").splitlines()[-1])
    assert payload["operation"] == "demo.operation"
    assert payload["context"]["phase"] == "unit-test"
    assert payload["fallback_used"] == "last-good-value"


def test_failsafe_pauses_repeated_failures_before_retry() -> None:
    executor = FailSafeExecutor(
        FailSafeConfig(
            base_retry_delay_seconds=5,
            max_retry_delay_seconds=5,
            max_consecutive_failures_before_pause=1,
        )
    )
    calls = {"count": 0}

    def explode():
        calls["count"] += 1
        raise RuntimeError("boom")

    first = executor.call("demo.cooldown", explode, fallback="safe")
    second = executor.call("demo.cooldown", explode, fallback="safe")

    assert first.ok is False
    assert second.ok is False
    assert calls["count"] == 1
    assert second.failure is not None
    assert second.failure.next_retry_at is not None


def test_hotpatch_controller_reloads_changed_modules(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    package_root = project_root / "src" / "lantern_house" / "services"
    target = package_root / "__codex_hotpatch_probe.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    script = f"""
import importlib
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, {str(project_root / "src")!r})

from lantern_house.config import HotPatchConfig
from lantern_house.runtime.hotpatch import HotPatchController
from lantern_house.utils.time import utcnow

callback_calls = []
importlib.invalidate_caches()
importlib.import_module("lantern_house.services.__codex_hotpatch_probe")
controller = HotPatchController(
    config=HotPatchConfig(
        check_interval_seconds=1,
        watch_paths=["src/lantern_house"],
        watch_extensions=[".py"],
    ),
    project_root=Path({str(project_root)!r}),
    rebuild_runtime=lambda files, modules: callback_calls.append((files, modules)),
)
controller.bootstrap()
controller._last_checked_at = utcnow() - timedelta(seconds=2)
time.sleep(0.05)
Path({str(target)!r}).write_text("VALUE = 2\\n", encoding="utf-8")
os.utime(Path({str(target)!r}), None)
report = controller.refresh_if_due(now=utcnow())
print(json.dumps({{
    "changed_files": report.changed_files if report else [],
    "reloaded_modules": report.reloaded_modules if report else [],
    "rebuilt_runtime": report.rebuilt_runtime if report else False,
    "callback_calls": callback_calls,
}}))
"""
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(completed.stdout.strip())

        assert payload["rebuilt_runtime"] is True
        assert any(path.endswith("__codex_hotpatch_probe.py") for path in payload["changed_files"])
        assert "lantern_house.services.__codex_hotpatch_probe" in payload["reloaded_modules"]
        assert payload["callback_calls"]
    finally:
        target.unlink(missing_ok=True)


def test_runtime_hotpatch_config_tracks_loaded_config_and_update_file(
    tmp_path: Path,
) -> None:
    update_file = tmp_path / "ops" / "votes.txt"
    config_path = tmp_path / "runtime.toml"
    config_path.write_text(
        """
[audience]
update_file_path = "ops/votes.txt"

[hot_patch]
watch_paths = ["src/lantern_house"]
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)
    hot_patch = build_hot_patch_config(config)

    assert config.loaded_from == str(config_path.resolve())
    assert config.audience.update_file_path == str(update_file.resolve())
    assert config.viewer_signals.harvest_directory_path == str(
        (tmp_path / "youtube_signals").resolve()
    )
    assert str(config_path.resolve()) in hot_patch.watch_paths
    assert str(update_file.resolve()) in hot_patch.watch_paths
    assert str((tmp_path / "youtube_signals").resolve()) in hot_patch.watch_paths


def test_hotpatch_controller_reports_shadow_validation_checks(tmp_path: Path) -> None:
    root = tmp_path / "project"
    watched = root / "watched"
    watched.mkdir(parents=True)
    target = watched / "probe.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    rebuild_calls: list[tuple[list[str], list[str]]] = []

    from lantern_house.config import HotPatchConfig
    from lantern_house.runtime.hotpatch import HotPatchController
    from lantern_house.utils.time import utcnow

    controller = HotPatchController(
        config=HotPatchConfig(
            check_interval_seconds=1,
            shadow_validate=True,
            watch_paths=[str(watched.relative_to(root))],
            watch_extensions=[".py"],
        ),
        project_root=root,
        rebuild_runtime=lambda files, modules: rebuild_calls.append((files, modules)),
        validate_patch=lambda files: ["shadow-ok", *[Path(item).name for item in files]],
    )
    controller.bootstrap()
    controller._last_checked_at = utcnow() - timedelta(seconds=2)
    target.write_text("VALUE = 2\n", encoding="utf-8")

    report = controller.refresh_if_due(now=utcnow())

    assert report is not None
    assert report.shadow_validated is True
    assert "shadow-ok" in report.validation_checks
    assert rebuild_calls
