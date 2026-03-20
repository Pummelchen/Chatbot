#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate
export LANTERN_HOUSE_CONFIG_PATH="${LANTERN_HOUSE_CONFIG_PATH:-./config.example.toml}"
lantern-house run --config "${LANTERN_HOUSE_CONFIG_PATH}"
