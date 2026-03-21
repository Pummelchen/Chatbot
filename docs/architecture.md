<!-- Lantern House core instruction: stay fail-safe, never leak debug or error text into the live chat, log recovered failures to logs/error.txt with context, and preserve hot-patch compatibility for uninterrupted long-running operation. -->
# Architecture Overview

## System Shape

Lantern House is split into seven major layers:

1. `db`: SQLAlchemy models, sessions, repositories, migrations
2. `context`: selective retrieval and prompt-packet assembly
3. `quality`: pacing and story-governance evaluators, continuity guardrails
4. `services`: manager, character, audience-control, house pressure, story gravity, beat planning, critic, progression, recap, event extraction, simulation, God-AI strategy, seeding
5. `runtime`: scheduler, orchestrator, recovery, long-running loop
6. `rendering`: terminal presentation for public output
7. `prompts`: editable role instructions for manager, characters, announcer, and God-AI strategy

## Runtime Loop

Each loop iteration follows the same pattern:

1. Recover or refresh run-state data.
2. Check whether full-clock-hour recaps are due.
3. Refresh the audience-control file state when its poll interval is due.
4. Sync subscriber-vote rollout requests and rollout beats.
5. Refresh deterministic house pressure and persistent story-gravity state.
6. Optionally apply any safe hot-patch file changes and rebuild runtime services in-place.
7. Evaluate pacing, continuity, story-governance health, recap quality, and recent public-turn review signals.
8. Refresh the manager directive when required, blocking only for the first directive and otherwise using a prefetched background plan.
9. Select the next speaker based on scene state, weights, recency, and burst/lull logic.
10. Build a selective character context packet.
11. Generate a structured turn from Ollama.
12. Run the continuity guard and the lightweight turn critic before persistence.
13. Extract events, reconcile beats, advance arc state, apply relationship deltas, persist the result, and persist turn-review telemetry.
14. Render the public message to the terminal.
15. Sleep for a variable delay before the next turn.

Parallel background loops:

- God-AI strategist: analyzes recent structured events, review telemetry, recap quality, story gravity, and simulation rankings, then persists a structured strategic brief.
- House-pressure engine: keeps grounded operational pressure alive and turns it into reusable beats.
- Audience-rollout engine: converts `update.txt` steering into staged rollout requests and rollout beats.
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
- The manager also receives a normalized audience-control report built from `update.txt`, including tone dials, vote requests, rollout stage, and staged rollout beats.
- The manager also receives house-pressure summaries, story-gravity state, dormant-thread registry snapshots, recap-quality alerts, public-turn review signals, simulation rankings, and the latest strategic brief when available.
- Repetition, romance stalls, mystery stalls, and low-progression windows are scored.
- Unresolved-question memory is bounded and overflow is pushed into dormant payoff threads.
- Forbidden-knowledge boundaries are injected into character packets.
- Prose-like or robotic public turns can be repaired before they are committed.
- A deterministic simulation lab ranks likely next directions, and a background God-AI planner converts that into structured strategic guidance without blocking the live loop.
- A fail-safe executor wraps critical runtime calls, caches last-good values, and applies cooldowns after repeated failures so the loop keeps going conservatively instead of thrashing.
- A hot-patch controller can soft-reload runtime/service/prompt/config code paths in place. SQLAlchemy ORM model modules are intentionally excluded from live reload because they are not safe to redefine mid-process.
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
