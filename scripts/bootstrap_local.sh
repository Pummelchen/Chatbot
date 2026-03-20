#!/usr/bin/env bash
# Lantern House core instruction: stay fail-safe, never leak debug or error text into the live chat, log recovered failures to logs/error.txt with context, and preserve hot-patch compatibility for uninterrupted long-running operation.
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

