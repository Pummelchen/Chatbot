# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from lantern_house.config import HotPatchConfig
from lantern_house.runtime.failsafe import log_call_failure
from lantern_house.utils.time import ensure_utc, utcnow

_MODULE_PRIORITY = {
    "lantern_house.utils": 0,
    "lantern_house.domain": 1,
    "lantern_house.db": 2,
    "lantern_house.quality": 3,
    "lantern_house.context": 4,
    "lantern_house.llm": 5,
    "lantern_house.services": 6,
    "lantern_house.rendering": 7,
    "lantern_house.runtime": 8,
}
_UNSAFE_RELOAD_MODULES = {
    "lantern_house.db.base",
    "lantern_house.db.models",
}


@dataclass(slots=True)
class HotPatchReport:
    changed_files: list[str] = field(default_factory=list)
    reloaded_modules: list[str] = field(default_factory=list)
    rebuilt_runtime: bool = False
    shadow_validated: bool = False
    validation_checks: list[str] = field(default_factory=list)


class HotPatchController:
    def __init__(
        self,
        *,
        config: HotPatchConfig,
        project_root: Path,
        rebuild_runtime: Callable[[list[str], list[str]], None],
        validate_patch: Callable[[list[str]], list[str] | None] | None = None,
    ) -> None:
        self.config = config
        self.project_root = project_root
        self.rebuild_runtime = rebuild_runtime
        self.validate_patch = validate_patch
        resolved_roots = []
        for item in config.watch_paths:
            candidate = (project_root / item).resolve()
            if candidate.exists():
                resolved_roots.append(candidate)
        self._watch_roots = [candidate for candidate in resolved_roots]
        self._known_mtimes: dict[Path, int] = {}
        self._last_checked_at = None

    def bootstrap(self) -> None:
        self._known_mtimes = self._scan()
        self._last_checked_at = utcnow()

    def refresh_if_due(self, *, now=None) -> HotPatchReport | None:
        now = ensure_utc(now or utcnow())
        if not self.config.enabled:
            return None
        if self._last_checked_at is not None and (
            now - ensure_utc(self._last_checked_at)
        ).total_seconds() < max(1, self.config.check_interval_seconds):
            return None

        current = self._scan()
        changed_paths = [
            path for path, stamp in current.items() if self._known_mtimes.get(path) != stamp
        ]
        self._last_checked_at = now
        if not changed_paths:
            self._known_mtimes = current
            return None

        try:
            validation_checks: list[str] = []
            if self.config.shadow_validate and self.validate_patch is not None:
                validation_checks = self.validate_patch([str(path) for path in changed_paths]) or []
            changed_modules = self._reload_modules_if_needed(changed_paths)
            self.rebuild_runtime(
                [str(path) for path in changed_paths],
                changed_modules,
            )
            self._known_mtimes = current
            return HotPatchReport(
                changed_files=[str(path) for path in changed_paths],
                reloaded_modules=changed_modules,
                rebuilt_runtime=True,
                shadow_validated=self.config.shadow_validate and self.validate_patch is not None,
                validation_checks=validation_checks,
            )
        except Exception as exc:
            log_call_failure(
                "hotpatch.refresh",
                exc,
                context={
                    "changed_files": [str(path) for path in changed_paths],
                },
                expected_inputs=[
                    "Reloadable Python modules under src/lantern_house.",
                    "Syntactically valid updated project files.",
                ],
                retry_advice=(
                    "Fix the modified file and save it again. The runtime will retry the hot patch "
                    "on the next scan without exposing the failure to the live chat."
                ),
                fallback_used="previous-runtime-components",
            )
            return None

    def _scan(self) -> dict[Path, int]:
        snapshots: dict[Path, int] = {}
        for root in self._watch_roots:
            if root.is_dir():
                for path in root.rglob("*"):
                    if not path.is_file() or path.suffix not in self.config.watch_extensions:
                        continue
                    snapshots[path.resolve()] = path.stat().st_mtime_ns
                continue
            if root.is_file():
                snapshots[root.resolve()] = root.stat().st_mtime_ns
        return snapshots

    def _reload_modules_if_needed(self, changed_paths: list[Path]) -> list[str]:
        if not any(path.suffix == ".py" for path in changed_paths):
            return []

        importlib.invalidate_caches()
        modules = self._module_names()
        reloaded: list[str] = []
        for module_name in modules:
            module = importlib.import_module(module_name)
            importlib.reload(module)
            reloaded.append(module_name)
        return reloaded

    def _module_names(self) -> list[str]:
        src_root = (self.project_root / "src" / "lantern_house").resolve()
        modules: list[str] = []
        for path in src_root.rglob("*.py"):
            relative = path.relative_to(src_root.parent)
            module_name = ".".join(relative.with_suffix("").parts)
            if module_name in _UNSAFE_RELOAD_MODULES:
                continue
            modules.append(module_name)
        modules.sort(key=self._module_sort_key)
        return modules

    def _module_sort_key(self, module_name: str) -> tuple[int, int, str]:
        priority = 99
        for prefix, value in _MODULE_PRIORITY.items():
            if module_name.startswith(prefix):
                priority = value
                break
        return (priority, module_name.count("."), module_name)
