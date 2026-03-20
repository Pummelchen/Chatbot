from __future__ import annotations

import json
from datetime import date, datetime
from importlib import resources
from typing import Any

import yaml


def load_text(package: str, name: str) -> str:
    return resources.files(package).joinpath(name).read_text(encoding="utf-8")


def load_yaml(package: str, name: str) -> dict[str, Any]:
    return yaml.safe_load(load_text(package, name))


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
