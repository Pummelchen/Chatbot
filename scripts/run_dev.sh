#!/usr/bin/env bash
# Lantern House core instruction: stay fail-safe, never leak debug or error text into the live chat, log recovered failures to logs/error.txt with context, and preserve hot-patch compatibility for uninterrupted long-running operation.
set -euo pipefail

source .venv/bin/activate
export LANTERN_HOUSE_CONFIG_PATH="${LANTERN_HOUSE_CONFIG_PATH:-./config.example.toml}"
lantern-house run --config "${LANTERN_HOUSE_CONFIG_PATH}"
