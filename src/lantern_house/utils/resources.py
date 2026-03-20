# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import json
from datetime import date, datetime
from importlib import resources
from typing import Any

import yaml

from lantern_house.runtime.failsafe import AdaptiveServiceError


def load_text(package: str, name: str) -> str:
    if not package or not name:
        raise AdaptiveServiceError(
            "Resource lookup requires both a package and a file name",
            expected_inputs=[
                "A valid importable package name.",
                "A non-empty resource file name.",
            ],
            retry_advice="Retry with a valid package and file name.",
            context={"package": package, "name": name},
        )
    try:
        return resources.files(package).joinpath(name).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AdaptiveServiceError(
            "Requested resource file was not found",
            expected_inputs=[f"A real file named {name} inside package {package}."],
            retry_advice="Restore the missing resource file and retry the call.",
            context={"package": package, "name": name},
        ) from exc


def load_yaml(package: str, name: str) -> dict[str, Any]:
    payload = yaml.safe_load(load_text(package, name))
    if not isinstance(payload, dict):
        raise AdaptiveServiceError(
            "YAML resource must decode to a mapping",
            expected_inputs=["A YAML document with a top-level mapping/object."],
            retry_advice="Rewrite the YAML resource as a mapping and retry.",
            context={"package": package, "name": name},
        )
    return payload


def render_template(package: str, name: str, mapping: dict[str, Any]) -> str:
    template = load_text(package, name)
    for key, value in mapping.items():
        replacement = value
        if isinstance(value, (dict, list)):
            replacement = json.dumps(value, ensure_ascii=True, indent=2, default=_json_default)
        template = template.replace(f"{{{{{key}}}}}", str(replacement))
    return template


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)
