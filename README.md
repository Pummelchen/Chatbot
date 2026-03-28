<!-- Lantern House core instruction: stay fail-safe, never leak debug or error text into the live chat, log recovered failures to logs/error.txt with context, and preserve hot-patch compatibility for uninterrupted long-running operation. -->
# Lantern House

Lantern House is a local-first Python system for running a 24/7 fictional live group chat designed for terminal output and later OBS capture. It is built for long-form serialized drama: a fading guesthouse, six emotionally loaded characters, a manager agent that controls canon and pacing, structured recap generation, and persistence in MySQL so the story can survive restarts without losing coherence.

The project targets macOS Apple Silicon with Python 3.12+, MySQL 8.4, and Ollama. Character agents use `gemma3:1b`; the story manager and announcer use `gemma3:4b`; the background strategic planner uses `gemma3:12b`.

## What This Repo Contains

- Modular application code under `src/lantern_house`
- MySQL schema and Alembic migration
- A production-minded orchestrator with recovery, pacing checks, recap scheduling, and context retrieval
- A deterministic house-pressure engine that keeps the guesthouse generating believable financial, repair, inspection, weather, and fatigue pressure
- A deterministic hourly beat ledger that tracks whether each clock hour landed a real shift in trust, desire, evidence, debt, power, or loyalty
- A daily and weekly programming grid that makes sure each day and week land planned tentpoles instead of only decent local turns
- A season planner that projects 30-day and 90-day reveal windows, ship cycles, inheritance turns, and cast-refresh points above the daily grid
- Multi-resolution canon capsules for `1h`, `6h`, `24h`, `7d`, and `30d` memory distillation
- A deterministic timeline, possession, and alibi layer that tracks who was where, which object was last grounded where, room occupancy, money deadlines, and repair state
- A deterministic chronology and evidence graph that links sightings, claims, object movement, deadlines, and contested facts into reusable mystery logic
- A per-character voice-fingerprint layer that persists cadence, conflict tone, humor markers, taboo markers, and lexical habits to keep public turns distinct and non-robotic
- A guest and NPC circulation engine that injects recurring outsiders as controlled pressure, not random sprawl
- A high-stakes multi-candidate turn selector that generates and reranks alternative public turns only when the moment is strategically important
- A live viewer-signal ingestion layer driven by `viewer_signals.yaml` plus local `youtube_signals/*.jsonl` harvest files for comments, clips, retention, and live chat
- Automatic highlight packaging that turns strong turns into clip-ready and quote-ready metadata
- A deeper monetization packaging pipeline that turns strong turns into title, hook, quote, faction, theory, and comment-prompt assets
- A broadcast-asset pipeline that turns strong turns into reusable clip manifests, descriptions, chapter markers, ship/theory labels, and “why this matters” export packages
- A deterministic soak-audit harness that stress-tests long-run strategy over `24h`, `72h`, and `7d` horizons
- A persistent story-gravity layer that keeps the show anchored to the house, its debt, hidden records, ownership conflict, and unstable bonds
- A staged audience-rollout beat system that converts `update.txt` votes into prerequisite beats instead of instant retcons
- A lightweight public-turn critic plus a deterministic simulation lab and a background God-AI strategist that persists structured strategic briefs
- A canon-court layer that softens or blocks contradiction-prone turns before they hit persistence
- A load-aware orchestration layer that keeps the visible loop smooth by budgeting planner and repair work against real runtime latency
- A terminal ops dashboard and telemetry layer for 24/7 oversight plus auto-remediation hints
- A small repair-model path for weak public turns, with deterministic fallback if repair fails
- An adaptive fail-safe runtime that keeps last-good state, backs off repeated failures, and writes structured recovery context to `logs/error.txt`
- A hot-patch loader that can soft-reload changed runtime, service, prompt, and config files without stopping the live stream
- A shadow canary for hot patches that validates changed files against a seeded runtime graph before live reload is accepted
- Prompt templates for manager, characters, and recap generation
- A live-editable `update.txt` control file for subscriber-vote steering
- A detailed story bible with cast, secrets, hooks, recap examples, and early arc plans
- Terminal rendering via Rich
- Tests for key engine behavior

## Core Design

The system avoids shoving the entire transcript into every prompt. Instead it persists canon, arcs, relationship state, extracted events, summaries, and run-state data, then builds selective context packets:

- Character turns receive identity, current emotional state, active goals, relevant recent messages, relationship snapshots, location facts, and manager instructions.
- The manager receives unresolved questions, arc status, dormant payoff threads, recent event highlights, continuity warnings, pacing health, and recent summaries.
- The manager also receives the latest hourly ledger status, canon capsule digests, highlight signals, and soak-audit warnings.
- The manager also receives season-plan signals, viewer-signal digests, broadcast-asset packaging signals, and timeline/possession/alibi summaries.
- Recaps are generated from stored events and prior summaries rather than transcript replay.

The manager operates in micro-steps. It sets the scene objective, controls reveal pace, assigns soft goals, tracks pacing health, and authorizes rare thought pulses.

## Story Gravity

The runtime now includes a dedicated story-governance layer in addition to pacing checks. This acts as the project’s long-term central force:

- It checks whether the last hour contained a meaningful progression in trust, evidence, debt pressure, or desire.
- It detects when the chat is drifting away from the house’s core tensions.
- It warns when recent dialogue is starting to look generic or repeated.
- It pressures the manager to restore cliffhanger energy before the stream goes flat.
- It keeps unresolved-question memory bounded and revives dormant payoff threads instead of letting prompts bloat over time.
- It enforces a daily and weekly programming grid so every 24h and 7d window still contains planned house, clue, romance, and alliance tentpoles.
- It advances persistent story-arc pressure and reveal stages from structured events, so long-form continuity lives in state, not only in transcript momentum.
- It persists `story_gravity_state`, dormant threads, recap quality scores, clip-value scores, fandom signals, public-turn review data, hourly ledgers, canon capsules, highlight packages, and soak-audit runs so the strategist and manager can steer from structured memory instead of vague prompt residue.

The seeded `story_engine` defines the permanent north star for the drama, so the manager is not improvising the project’s value proposition from scratch every few turns.

## Pressure And Planning

Two new systems now keep the story from flattening over very long runs:

- `house_state` is a persistent operational model of Lantern House. It tracks cash, burn rate, payroll timing, repair backlog, inspection risk, weather strain, staff fatigue, and reputation risk.
- Active house pressures are converted into reusable `beats`, so the manager always has grounded practical conflict available.
- Subscriber votes in `update.txt` are compiled into staged rollout beats with prerequisite timing, not just passed through as text.
- Pending beats are ordered by readiness, and future payoff beats cannot complete before their due window, so long-form vote changes unfold in sequence instead of skipping ahead.
- The hourly beat ledger persists a hard contract for each clock hour, so the manager and strategist can see when the stream is generating tension without actually changing anything.
- Canon capsules distill the story into bounded memory windows, which keeps prompts compact while still preserving weeks of continuity.
- A canon-court layer checks risky turns for premature finality and protected-truth bleed, then softens or repairs them before public persistence.
- Highlight packages turn strong public turns into reusable metadata for clips, quotes, ship angles, and theory angles.
- Monetization packages extend those highlights into usable YouTube-facing assets: title options, hook lines, recap blurbs, faction labels, tags, and comment prompts.
- A simulation lab ranks candidate strategic directions like house-pressure-first, mystery-evidence-first, romance-faultline-first, audience-rollout-first, and ensemble-refresh-first.
- A programming grid keeps daily and weekly tentpoles visible to the manager and strategist, so “good hour, weak day” drift is caught structurally.
- A soak-audit harness uses those deterministic strategy rankings across `24h`, `72h`, and `7d` horizons to detect slow-death failure modes like repetition, recap decay, clip drought, ship stagnation, and strategy lock-in.
- A background God-AI planner uses `gemma3:12b` plus the simulation ranking to persist strategic briefs with north-star objective, arc ranking, reveal permissions, urgency scores, recap priorities, clip value, and fandom value for the live manager without blocking the chat loop.
- The visible hot path is protected by prefetching manager directives in the background, by a lightweight critic, by load-aware inference budgeting, and by a small repair-model pass that can salvage weak turns before persistence.
- On important turns only, the live loop can generate two 1B candidates and rerank them against hourly needs, clip value, fandom tension, and strategic urgency before persistence.

## Live Update Control

The repo root now includes [update.txt](/Users/andreborchert/Library/CloudStorage/Dropbox/Chatbot/update.txt), a YAML-style control file with comments that you can edit during a live run.

- The runtime checks it every 10 minutes.
- The manager treats it as subscriber-vote steering, not instant retcon authority.
- Tone dials let you bias the stream live: romance, thriller action, twists, violence, bad language, new characters, new locations, gossip, jealousy, and more.
- Relationship votes can define paths like enemies, attraction, alliance, estrangement, or long-form outcomes such as a baby arc.
- Cast, location, conflict, mystery, recap, and freeform vote sections are all supported.

Major requests are phased in gradually over the configured rollout window, which defaults to 24 hours. If viewers vote for something large like "A and B should have a baby," the manager is expected to build the emotional and practical path first instead of jumping straight to the end-state.

The repo root also includes [viewer_signals.yaml](/Users/andreborchert/Library/CloudStorage/Dropbox/Chatbot/viewer_signals.yaml), a local-first signal file for real audience observations such as ship spikes, theory bursts, clip replays, faction splits, or recap drop-off. The adjacent [youtube_signals/README.md](/Users/andreborchert/Library/CloudStorage/Dropbox/Chatbot/youtube_signals/README.md) documents optional JSONL harvest files for comments, clips, retention, and live chat. These signals steer the strategist and manager, but do not directly retcon canon.

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

3. Copy `.env.example` to `.env`, then adjust credentials or edit `config.example.toml`.
4. Start everything with the bootstrap supervisor:

```bash
./start.sh
```

`start.sh` will:

- create or repair `.venv`
- install dependencies when needed
- ensure the configured MySQL database exists
- ensure Ollama is reachable and the configured models are present
- run `migrate`, `seed`, and `healthcheck`
- start the live runtime with auto-restart supervision
- resume from persisted `run_state` if the project was already running before

5. Edit `update.txt` whenever you want to steer the live story. The manager will absorb the changes on its next 10-minute audience-control check.
6. Edit `viewer_signals.yaml` whenever you want to feed real audience-signal observations into the strategist and manager.
7. If you keep multiple runtime configs, run `./start.sh --config /absolute/path/to/runtime.toml`. Hot patching now keeps tracking that active config file instead of snapping back to the default example config.

Manual CLI startup is still available if you want more control:

```bash
source .venv/bin/activate
lantern-house migrate
lantern-house seed
lantern-house run
```

## CLI Commands

- `lantern-house migrate`: apply Alembic migrations
- `lantern-house seed`: load the initial story bible into MySQL
- `lantern-house run`: start the live terminal chat runtime
- `lantern-house simulate`: run the accelerated deterministic simulation lab against the current world state
- `lantern-house soak-audit`: run the long-horizon deterministic soak audit against the current world state
- `lantern-house broadcast-assets`: inspect the most recent reusable broadcast/clip export packages
- `lantern-house shadow-check`: run the shadow canary used by hot-patch validation
- `lantern-house dashboard`: show the current ops telemetry snapshot for runtime, load, checkpoint freshness, recap freshness, and active strategy
- `lantern-house recap-now`: generate recap blocks immediately
- `lantern-house healthcheck`: verify database and Ollama availability

All CLI commands now fail with concise operator messages plus logged context in `logs/error.txt`; they no longer dump raw Python tracebacks for normal setup mistakes like bad DB credentials or running `seed` before `migrate`.

## Runtime Notes

- Public chat output goes only to the terminal renderer.
- Internal logs are written to `logs/lantern_house.log`.
- Structured failure records are written to `logs/error.txt`.
- Console logging is disabled by default during `run`, so the terminal stays reserved for the diegetic stream and recap blocks.
- Hourly recap blocks emit 1h, 12h, and 24h summaries.
- Runtime state is persisted on every turn and checkpointed independently on a background interval.
- Default recovery protection includes per-turn checkpoint snapshots plus a 60-second heartbeat.
- Recovery logic resumes from persisted run state after restart and flags unclean shutdowns for the manager.
- `./start.sh` is the preferred operator entrypoint. It bootstraps dependencies, initializes missing infrastructure, and then hands off to the resumable runtime supervisor.
- After the first directive, manager refreshes can happen off the hot path so steady-state chat flow does not stop every time the planner updates.
- The manager also carries a persisted `audience_control` block sourced from `update.txt`, including tone dials, vote requests, rollout stage, and the last successful parse.
- Audience steering is also compiled into persisted rollout beats so major vote requests land as staged prerequisites over time.
- `house_state` is persisted separately from transcript memory, giving the manager a deterministic practical gravity field even when models get vague.
- The background God-AI planner can persist long-horizon strategic briefs during live operation, while `run --once` skips that loop to keep smoke runs fast.
- The strategist stack now also persists simulation runs, ranked strategy candidates, dormant-thread registry rows, public-turn review telemetry, recap-quality scores, clip-value scores, and fandom-signal candidates.
- The strategist stack now also persists hourly progress ledgers, programming-grid slots, canon capsules, canon-court findings, highlight packages, monetization packages, ops telemetry, and soak-audit runs.
- The strategist stack now also persists timeline facts, object-possession snapshots, viewer-signal observations, and broadcast-asset export packages.
- The live loop wraps critical subsystems in a fail-safe executor. Unexpected failures are logged with context, routed to conservative fallbacks or last-good state, and never printed into the public chat stream.
- Repeated failures enter a cooldown window instead of hammering the same broken dependency every turn.
- New persistence layers are hot-patch-safe: if live code lands before migrations do, the new repository paths degrade to empty/no-op behavior and keep the stream alive until the database is upgraded.
- Hot-patch scanning can rebuild runtime services from changed files without dropping the live process. ORM schema modules are intentionally excluded from live reload to avoid corrupting SQLAlchemy state.
- Hot-patch scanning now follows the active runtime config file, the resolved audience steering file, and `.env` in addition to the default source tree watchers, so live config edits are not silently ignored after startup.
- `story.seed_file` now works as a real setting: it can point either to a packaged seed resource name or a local YAML file path for custom world variants.
- Degraded mode can keep the simulation alive when a model request fails, but it does so conservatively.
- Manager and God-AI planners now use shorter retry budgets because both have deterministic fallbacks; this keeps fallback guidance timely instead of minutes late.
- On strategically important turns, the live loop can generate multiple 1B candidates, preview them through extraction and criticism, and rerank them before persistence.
- Deterministic world tracking now grounds room occupancy, alibis, house deadlines, and important-object possession so mystery turns stay anchored to explicit state.
- The season planner adds `30d` and `90d` tentpoles above the daily and weekly grid, and viewer-signal ingestion can steer those horizons without directly retconning canon.
- The broadcast-asset pipeline turns high-value turns into reusable export packages with title, hook, description, chapter markers, clip window, ship/theory labels, and a comment seed.
- Recap prompts are compacted into bounded event digests so 12h and 24h summaries stay stable during true 24/7 operation.
- Low-quality unresolved-question fragments are filtered before they enter canon memory.
- If a model turn drifts into robotic or prose-like register, the runtime repairs it before persisting public output.
- The repair path can use a dedicated small model configured as `models.repair`; if that model fails, the runtime falls back to the deterministic continuity-safe line instead of blocking.
- Hot patches can run through a shadow canary first, so changed code is validated against seeded runtime services before the live process swaps in rebuilt components.

## Quality Checks

For local verification before a presentation or long unattended run:

```bash
source .venv/bin/activate
python3 -m compileall alembic src tests
python3 -m ruff check src tests
pytest -q
lantern-house healthcheck
lantern-house simulate --hours 24 --turns-per-hour 90
lantern-house soak-audit
```

## Documentation

- [Architecture](docs/architecture.md)
- [Operations](docs/operations.md)
