#!/usr/bin/env bash
set -euo pipefail

python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e ".[dev]"

echo "Ensure MySQL 8.4 and Ollama are running before continuing."
echo "Pull models with: ollama pull gemma3:1b && ollama pull gemma3:4b"
echo "Then run:"
echo "  lantern-house migrate"
echo "  lantern-house seed"
echo "  lantern-house run"

