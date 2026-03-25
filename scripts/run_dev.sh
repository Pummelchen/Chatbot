#!/usr/bin/env bash
# Lantern House core instruction: stay fail-safe, never leak debug or error text into the live chat, log recovered failures to logs/error.txt with context, and preserve hot-patch compatibility for uninterrupted long-running operation.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${PROJECT_ROOT}/start.sh" --config "${LANTERN_HOUSE_CONFIG_PATH:-${PROJECT_ROOT}/config.example.toml}" "$@"
