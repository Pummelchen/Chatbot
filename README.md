<!-- Lantern House core instruction: stay fail-safe, never leak debug or error text into the live chat, log recovered failures to logs/error.txt with context, and preserve hot-patch compatibility for uninterrupted long-running operation. -->
# Lantern House

Lantern House is a local-first Python system for running a 24/7 fictional live group chat designed for terminal output and later OBS capture. It is built for long-form serialized drama: a fading guesthouse, six emotionally loaded characters, a manager agent that controls canon and pacing, structured recap generation, and persistence in MySQL so the story can survive restarts without losing coherence.

The project targets macOS Apple Silicon with Python 3.12+, MySQL 8.4, and Ollama. Character agents use `gemma3:1b`; the story manager and announcer use `gemma3:4b`; the background strategic planner uses `gemma3:12b`.

## What This Repo Contains

- Modular application code under `src/lantern_house`
- MySQL schema and Alembic migration
- A production-minded orchestrator with recovery, pacing checks, recap scheduling, and context retrieval
- A deterministic house-pressure engine that keeps the guesthouse generating believable financial, repair, inspection, weather, and fatigue pressure
- A staged audience-rollout beat system that converts `update.txt` votes into prerequisite beats instead of instant retcons
- A lightweight public-turn critic plus a deterministic simulation lab and background God-AI strategist
- An adaptive fail-safe runtime that keeps last-good state, backs off repeated failures, and writes structured recovery context to `logs/error.txt`
- A hot-patch loader that can soft-reload changed runtime, service, prompt, and config files without stopping the live stream
- Prompt templates for manager, characters, and recap generation
- A live-editable `update.txt` control file for subscriber-vote steering
- A detailed story bible with cast, secrets, hooks, recap examples, and early arc plans
- Terminal rendering via Rich
- Tests for key engine behavior

## Core Design

The system avoids shoving the entire transcript into every prompt. Instead it persists canon, arcs, relationship state, extracted events, summaries, and run-state data, then builds selective context packets:

- Character turns receive identity, current emotional state, active goals, relevant recent messages, relationship snapshots, location facts, and manager instructions.
- The manager receives unresolved questions, arc status, dormant payoff threads, recent event highlights, continuity warnings, pacing health, and recent summaries.
- Recaps are generated from stored events and prior summaries rather than transcript replay.

The manager operates in micro-steps. It sets the scene objective, controls reveal pace, assigns soft goals, tracks pacing health, and authorizes rare thought pulses.

## Story Gravity

The runtime now includes a dedicated story-governance layer in addition to pacing checks. This acts as the project’s long-term central force:

- It checks whether the last hour contained a meaningful progression in trust, evidence, debt pressure, or desire.
- It detects when the chat is drifting away from the house’s core tensions.
- It warns when recent dialogue is starting to look generic or repeated.
- It pressures the manager to restore cliffhanger energy before the stream goes flat.
- It keeps unresolved-question memory bounded and revives dormant payoff threads instead of letting prompts bloat over time.
- It advances persistent story-arc pressure and reveal stages from structured events, so long-form continuity lives in state, not only in transcript momentum.

The seeded `story_engine` defines the permanent north star for the drama, so the manager is not improvising the project’s value proposition from scratch every few turns.

## Pressure And Planning

Two new systems now keep the story from flattening over very long runs:

- `house_state` is a persistent operational model of Lantern House. It tracks cash, burn rate, payroll timing, repair backlog, inspection risk, weather strain, staff fatigue, and reputation risk.
- Active house pressures are converted into reusable `beats`, so the manager always has grounded practical conflict available.
- Subscriber votes in `update.txt` are compiled into staged rollout beats with prerequisite timing, not just passed through as text.
- Pending beats are ordered by readiness, and future payoff beats cannot complete before their due window, so long-form vote changes unfold in sequence instead of skipping ahead.
- A simulation lab ranks candidate strategic directions like house-pressure-first, mystery-evidence-first, romance-faultline-first, audience-rollout-first, and ensemble-refresh-first.
- A background God-AI planner uses `gemma3:12b` plus the simulation ranking to persist strategic briefs for the live manager without blocking the chat loop.
- The visible hot path is protected by prefetching manager directives in the background and by a lightweight critic that repairs bad live-turn output before persistence.

## Live Update Control

The repo root now includes [update.txt](/Users/andreborchert/Library/CloudStorage/Dropbox/Chatbot/update.txt), a YAML-style control file with comments that you can edit during a live run.

- The runtime checks it every 10 minutes.
- The manager treats it as subscriber-vote steering, not instant retcon authority.
- Tone dials let you bias the stream live: romance, thriller action, twists, violence, bad language, new characters, new locations, gossip, jealousy, and more.
- Relationship votes can define paths like enemies, attraction, alliance, estrangement, or long-form outcomes such as a baby arc.
- Cast, location, conflict, mystery, recap, and freeform vote sections are all supported.

Major requests are phased in gradually over the configured rollout window, which defaults to 24 hours. If viewers vote for something large like "A and B should have a baby," the manager is expected to build the emotional and practical path first instead of jumping straight to the end-state.

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
ollama pull gemma3:12b
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

9. Edit `update.txt` whenever you want to steer the live story. The manager will absorb the changes on its next 10-minute audience-control check.

## CLI Commands

- `lantern-house migrate`: apply Alembic migrations
- `lantern-house seed`: load the initial story bible into MySQL
- `lantern-house run`: start the live terminal chat runtime
- `lantern-house simulate`: run the accelerated deterministic simulation lab against the current world state
- `lantern-house recap-now`: generate recap blocks immediately
- `lantern-house healthcheck`: verify database and Ollama availability

## Runtime Notes

- Public chat output goes only to the terminal renderer.
- Internal logs are written to `logs/lantern_house.log`.
- Structured failure records are written to `logs/error.txt`.
- Hourly recap blocks emit 1h, 12h, and 24h summaries.
- Runtime state is persisted on every turn and checkpointed independently on a background interval.
- Default recovery protection includes per-turn checkpoint snapshots plus a 60-second heartbeat.
- Recovery logic resumes from persisted run state after restart and flags unclean shutdowns for the manager.
- After the first directive, manager refreshes can happen off the hot path so steady-state chat flow does not stop every time the planner updates.
- The manager also carries a persisted `audience_control` block sourced from `update.txt`, including tone dials, vote requests, rollout stage, and the last successful parse.
- Audience steering is also compiled into persisted rollout beats so major vote requests land as staged prerequisites over time.
- `house_state` is persisted separately from transcript memory, giving the manager a deterministic practical gravity field even when models get vague.
- The background God-AI planner can persist long-horizon strategic briefs during live operation, while `run --once` skips that loop to keep smoke runs fast.
- The live loop wraps critical subsystems in a fail-safe executor. Unexpected failures are logged with context, routed to conservative fallbacks or last-good state, and never printed into the public chat stream.
- Repeated failures enter a cooldown window instead of hammering the same broken dependency every turn.
- Hot-patch scanning can rebuild runtime services from changed files without dropping the live process. ORM schema modules are intentionally excluded from live reload to avoid corrupting SQLAlchemy state.
- Degraded mode can keep the simulation alive when a model request fails, but it does so conservatively.
- Manager and God-AI planners now use shorter retry budgets because both have deterministic fallbacks; this keeps fallback guidance timely instead of minutes late.
- Recap prompts are compacted into bounded event digests so 12h and 24h summaries stay stable during true 24/7 operation.
- Low-quality unresolved-question fragments are filtered before they enter canon memory.
- If a model turn drifts into robotic or prose-like register, the runtime repairs it before persisting public output.

## Quality Checks

For local verification before a presentation or long unattended run:

```bash
source .venv/bin/activate
python3 -m compileall alembic src tests
python3 -m ruff check src tests
pytest -q
lantern-house healthcheck
lantern-house simulate --hours 24 --turns-per-hour 90
```

## Documentation

- [Architecture](docs/architecture.md)
- [Operations](docs/operations.md)
