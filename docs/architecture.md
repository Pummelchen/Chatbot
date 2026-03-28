<!-- Lantern House core instruction: stay fail-safe, never leak debug or error text into the live chat, log recovered failures to logs/error.txt with context, and preserve hot-patch compatibility for uninterrupted long-running operation. -->
# Architecture Overview

## System Shape

Lantern House is split into seven major layers:

1. `db`: SQLAlchemy models, sessions, repositories, migrations
2. `context`: selective retrieval and prompt-packet assembly
3. `quality`: pacing and story-governance evaluators, continuity guardrails
4. `services`: manager, character, audience-control, viewer-signal ingestion, chronology graph, voice fingerprinting, guest circulation, house pressure, hourly ledger, programming grid, season planner, canon distillation, canon court, world tracking, turn selection, highlight packaging, monetization packaging, broadcast-asset packaging, load orchestration, ops dashboard, soak audit, story gravity, beat planning, critic, progression, recap, event extraction, simulation, God-AI strategy, seeding, shadow canary
5. `runtime`: scheduler, orchestrator, recovery, long-running loop
6. `rendering`: terminal presentation for public output
7. `prompts`: editable role instructions for manager, characters, announcer, and God-AI strategy

## Runtime Loop

Each loop iteration follows the same pattern:

1. Recover or refresh run-state data.
2. Check whether full-clock-hour recaps are due.
3. Refresh the audience-control file state when its poll interval is due.
4. Sync subscriber-vote rollout requests and rollout beats.
5. Refresh deterministic house pressure, the hourly beat ledger, the daily/weekly programming grid, the season planner, canon capsules, deterministic world tracking, and persistent story-gravity state.
6. Refresh voice fingerprints, the chronology graph, and guest circulation so the manager sees current style, evidence, and outsider pressure.
7. Optionally apply any safe hot-patch file changes, but only after a shadow canary validates the changed files against a seeded service graph.
8. Evaluate pacing, continuity, story-governance health, recap quality, recent public-turn review signals, and contradiction pressure.
9. Refresh the manager directive when required, blocking only for the first directive and otherwise using a prefetched background plan.
10. Select the next speaker based on scene state, weights, recency, and burst/lull logic.
11. Build a selective character context packet with timeline grounding and voice fingerprints.
12. Generate one or more structured turn candidates from Ollama when the moment is important enough to justify reranking.
13. Preview candidate turns through extraction, continuity, canon court, criticism, and reranking, then choose the best candidate against hourly needs, strategic urgency, and viewer-value signals.
14. Extract events, reconcile beats, advance arc state, refresh the hourly ledger, programming grid, season planner, canon capsules, chronology graph, and world-tracking state, persist the result, and persist turn-review plus highlight, monetization, and broadcast-asset telemetry.
15. Render the public message to the terminal.
16. Sleep for a variable delay before the next turn.

Parallel background loops:

- God-AI strategist: analyzes recent structured events, review telemetry, recap quality, story gravity, and simulation rankings, then persists a structured strategic brief.
- House-pressure engine: keeps grounded operational pressure alive and turns it into reusable beats.
- Audience-rollout engine: converts `update.txt` steering into staged rollout requests and rollout beats.
- Viewer-signal ingestion: normalizes local audience-signal observations from `viewer_signals.yaml` into bounded retention/fandom inputs for the strategist and manager.
- World-tracking engine: grounds room occupancy, alibis, deadlines, and important-object possession into deterministic state that the canon court and manager can both consume.
- Soak-audit harness: runs long-horizon deterministic stress checks so the strategist sees drift and stagnation before the live loop feels it.
- Ops telemetry: captures runtime/load/checkpoint/recap/strategy health so the operator and auto-remediation rules can see whether the live system is decaying.
- Checkpoint loop: writes periodic restart-safe snapshots independent of turn persistence.

## Persistence Strategy

The system persists:

- Canon facts and location/object state
- Character identity and current state
- Character cultural background, family pressure, conflict style, privacy boundaries, value instincts, and emotional expression cues
- Relationship tension values
- Secrets and reveal stages
- Arc state and reveal ladders
- Scene and beat state
- Deterministic house-pressure state
- Persistent story-gravity state
- Manager directives
- Strategic briefs produced by the background God-AI planner
- Simulation lab runs and ranked strategy candidates
- Hourly progress ledgers
- Programming-grid slots
- Season-planner slots
- Canon capsules
- Canon-court findings
- Timeline facts and object-possession state
- Viewer-signal observations
- Chronology graph nodes and edges
- Voice fingerprints
- Guest profiles
- Highlight packages
- Monetization packages
- Broadcast-asset packages
- Soak-audit runs
- Ops telemetry
- Hot-patch canary runs
- Rollout requests and rollout beats compiled from `update.txt`
- Public-turn reviews, clip-value scores, fandom-signal candidates, and recap-quality scores
- Dormant-thread registry rows
- Public chat messages
- Thought pulses
- Extracted events
- Summaries
- Continuity flags
- Run/scheduler state

This allows recovery without replaying the entire transcript.

Run-state persistence is layered:

- Every turn commits message, events, relationship deltas, and run-state updates transactionally.
- A checkpoint snapshot is written on a background interval so recovery still has fresh state even if the machine reboots mid-scene.
- Startup inspects the prior run-state status and emits an unclean-shutdown continuity flag when the last run died in `starting` or `running`.
- Structured failure records are written to `logs/error.txt`, with operation name, expectations, retry advice, fallback choice, and context for later repair.

## Anti-Drift Controls

Anti-drift is explicit and layered:

- Canon facts are stored separately from chat history.
- Reveal ladders and unresolved questions are tracked at the arc level.
- Arc pressure and active beats advance from structured event hits, not only from prompt text.
- Subscriber-vote requests are compiled into prerequisite beats with due windows instead of treated as raw prompt text.
- Beat retrieval prioritizes `active` and `ready` work ahead of future planned beats, and planned future beats cannot be completed early from incidental keyword overlap.
- A deterministic `house_state` keeps financial, repair, inspection, weather, fatigue, and reputation pressure alive even if the models drift.
- The manager is given pacing health and continuity warnings.
- The manager is also given a story-governance report covering hourly progression, core-tension drift, cliffhanger pressure, and robotic-voice risk.
- The manager is also given a persisted hourly ledger that acts as a hard contract for each clock hour.
- The manager is also given a persisted daily and weekly programming grid so day-level and week-level tentpoles do not silently collapse while hourly turns still look fine.
- The manager is also given persisted `30d` and `90d` season-plan slots so the story keeps moving toward larger reveal windows, ship cycles, and cast-refresh points.
- The manager is also given bounded canon capsules instead of needing broad transcript replay for longer windows.
- A deterministic world-tracking layer persists room occupancy, alibi claims, money deadlines, repair state, and important-object possession so mystery and betrayal turns can be checked against grounded state.
- A chronology graph turns those grounded facts into reusable evidence relationships and contested-fact warnings for the manager, God AI, and canon court.
- A persistent voice-fingerprint layer keeps visible dialogue tied to recognizable cadence, humor, conflict behavior, and lexical habits instead of flattening over time.
- A guest-circulation layer introduces recurring outsider pressure in bounded, reusable form so the house can refresh without losing focus.
- The canon court can soften or block contradiction-prone turns before they are persisted as public truth.
- The manager also receives a normalized audience-control report built from `update.txt`, including tone dials, vote requests, rollout stage, and staged rollout beats.
- The manager also receives normalized viewer-signal digests and broadcast-asset packaging signals so the strategist can shape reentry value, clip packaging, and fandom discussion without directly rewriting canon.
- The manager also receives house-pressure summaries, story-gravity state, dormant-thread registry snapshots, recap-quality alerts, public-turn review signals, highlight packages, monetization signals, soak-audit warnings, ops alerts, simulation rankings, and the latest strategic brief when available.
- Repetition, romance stalls, mystery stalls, and low-progression windows are scored.
- Unresolved-question memory is bounded and overflow is pushed into dormant payoff threads.
- Forbidden-knowledge boundaries are injected into character packets.
- Strategically important turns can run through multi-candidate generation and reranking instead of trusting the first visible line from the 1B model.
- Prose-like or robotic public turns can be repaired by a small dedicated model before they are committed, with deterministic fallback if repair fails.
- A deterministic simulation lab ranks likely next directions, and a background God-AI planner converts that into structured strategic guidance without blocking the live loop.
- A load-aware orchestration layer budgets repair/model/planner work against recent latency so the visible cadence stays stable under pressure.
- A fail-safe executor wraps critical runtime calls, caches last-good values, and applies cooldowns after repeated failures so the loop keeps going conservatively instead of thrashing.
- New governance tables degrade to no-op/empty reads if code is hot-patched ahead of migrations, so live upgrades do not immediately destabilize the stream.
- A hot-patch controller can soft-reload runtime/service/prompt/config code paths in place. SQLAlchemy ORM model modules are intentionally excluded from live reload because they are not safe to redefine mid-process.
- A shadow canary validates changed files against a seeded runtime graph before hot-patch rebuilds are accepted, reducing the risk of live reload regressions.
- Thought pulses are budgeted and cooldown-limited.
- Recaps are generated from bounded event digests and prior summaries, not raw transcript replay.
- A seeded `story_engine` defines the permanent dramatic north star so the runtime keeps recentering on house survival, hidden records, inheritance conflict, loyalty fractures, and unstable attraction.

## Design Tradeoffs

- Sync SQLAlchemy was chosen over async ORM complexity to keep the data layer reliable and straightforward.
- Prompt templates are plain editable markdown files instead of deeply embedded strings.
- A degraded-mode fallback exists to protect continuity during transient model failures.
- The God-AI planner is intentionally background-only and low-frequency; it is valuable for direction, but not allowed to tax the visible cadence loop.
- Console logging is disabled by default during live runs so only the diegetic renderer owns the operator-facing terminal.
- Terminal-first output keeps the MVP narrow while preserving later OBS and YouTube integration paths.
