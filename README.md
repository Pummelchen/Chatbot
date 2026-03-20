# Lantern House

Lantern House is a local-first Python system for running a 24/7 fictional live group chat designed for terminal output and later OBS capture. It is built for long-form serialized drama: a fading guesthouse, six emotionally loaded characters, a manager agent that controls canon and pacing, structured recap generation, and persistence in MySQL so the story can survive restarts without losing coherence.

The project targets macOS Apple Silicon with Python 3.12+, MySQL 8.4, and Ollama. Character agents use `gemma3:1b`; the story manager and announcer use `gemma3:4b`.

## What This Repo Contains

- Modular application code under `src/lantern_house`
- MySQL schema and Alembic migration
- A production-minded orchestrator with recovery, pacing checks, recap scheduling, and context retrieval
- Prompt templates for manager, characters, and recap generation
- A detailed story bible with cast, secrets, hooks, recap examples, and early arc plans
- Terminal rendering via Rich
- Tests for key engine behavior

## Core Design

The system avoids shoving the entire transcript into every prompt. Instead it persists canon, arcs, relationship state, extracted events, summaries, and run-state data, then builds selective context packets:

- Character turns receive identity, current emotional state, active goals, relevant recent messages, relationship snapshots, location facts, and manager instructions.
- The manager receives unresolved questions, arc status, recent event highlights, continuity warnings, pacing health, and recent summaries.
- Recaps are generated from stored events and prior summaries rather than transcript replay.

The manager operates in micro-steps. It sets the scene objective, controls reveal pace, assigns soft goals, tracks pacing health, and authorizes rare thought pulses.

## Seeded Ensemble

The default story bible is now built around a globally legible but story-first cast:

- Amelia Vale: Anglo house manager and emotional center
- Arjun Mehta: Indian long-term guest and careful observer
- Rafael Costa: Brazilian night fixer and volatile romantic fault line
- Ayu Pranata: Indonesian reception insider and audience bridge
- Lucía Ortega: Mexican family claimant with inheritance pressure
- Hana Seo: Korean returning figure tied to the old betrayal
- Ren Akiyama: reserved as a later-stage archive-and-history expander

These backgrounds are not cosmetic. They are persisted as structured character context so prompts can use family pressure, conflict style, privacy boundaries, value instincts, and emotional expression patterns without collapsing into caricature.

## Quick Start

1. Install Python 3.12+ and MySQL 8.4.
2. Install Ollama and pull the required models:

```bash
ollama pull gemma3:1b
ollama pull gemma3:4b
```

3. Create a database:

```sql
CREATE DATABASE lantern_house CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

4. Create a virtual environment and install dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

5. Copy `.env.example` to `.env`, then adjust credentials or use `config.example.toml`.
6. Run migrations:

```bash
lantern-house migrate
```

7. Seed the story world:

```bash
lantern-house seed
```

8. Start the runtime:

```bash
lantern-house run
```

## CLI Commands

- `lantern-house migrate`: apply Alembic migrations
- `lantern-house seed`: load the initial story bible into MySQL
- `lantern-house run`: start the live terminal chat runtime
- `lantern-house recap-now`: generate recap blocks immediately
- `lantern-house healthcheck`: verify database and Ollama availability

## Runtime Notes

- Public chat output goes only to the terminal renderer.
- Internal logs are written to `logs/lantern_house.log`.
- Hourly recap blocks emit 1h, 12h, and 24h summaries.
- Runtime state is persisted on every turn and checkpointed independently on a background interval.
- Default recovery protection includes per-turn checkpoint snapshots plus a 60-second heartbeat.
- Recovery logic resumes from persisted run state after restart and flags unclean shutdowns for the manager.
- Degraded mode can keep the simulation alive when a model request fails, but it does so conservatively.

## Quality Checks

For local verification before a presentation or long unattended run:

```bash
source .venv/bin/activate
python3 -m compileall alembic src tests
python3 -m ruff check src tests
pytest -q
lantern-house healthcheck
```

## Documentation

- [Architecture](docs/architecture.md)
- [Operations](docs/operations.md)
