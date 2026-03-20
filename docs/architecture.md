# Architecture Overview

## System Shape

Lantern House is split into five major layers:

1. `db`: SQLAlchemy models, sessions, repositories, migrations
2. `context`: selective retrieval and prompt-packet assembly
3. `quality`: pacing and story-governance evaluators, continuity guardrails
4. `services`: manager, character, audience-control, progression, recap, event extraction, seeding
5. `runtime`: scheduler, orchestrator, recovery, long-running loop
6. `rendering`: terminal presentation for public output

## Runtime Loop

Each loop iteration follows the same pattern:

1. Recover or refresh run-state data.
2. Check whether full-clock-hour recaps are due.
3. Refresh the audience-control file state when its poll interval is due.
4. Evaluate pacing and continuity health.
5. Refresh the manager directive when required, blocking only for the first directive and otherwise allowing background refresh.
6. Select the next speaker based on scene state, weights, recency, and burst/lull logic.
7. Build a selective character context packet.
8. Generate a structured turn from Ollama.
9. Extract events, advance arc state, apply relationship deltas, persist the result, and optionally emit a thought pulse.
10. Render the public message to the terminal.
11. Sleep for a variable delay before the next turn.

## Persistence Strategy

The system persists:

- Canon facts and location/object state
- Character identity and current state
- Character cultural background, family pressure, conflict style, privacy boundaries, value instincts, and emotional expression cues
- Relationship tension values
- Secrets and reveal stages
- Arc state and reveal ladders
- Scene and beat state
- Manager directives
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

## Anti-Drift Controls

Anti-drift is explicit and layered:

- Canon facts are stored separately from chat history.
- Reveal ladders and unresolved questions are tracked at the arc level.
- Arc pressure and active beats advance from structured event hits, not only from prompt text.
- The manager is given pacing health and continuity warnings.
- The manager is also given a story-governance report covering hourly progression, core-tension drift, cliffhanger pressure, and robotic-voice risk.
- The manager also receives a normalized audience-control report built from `update.txt`, including tone dials, vote requests, and rollout stage.
- Repetition, romance stalls, mystery stalls, and low-progression windows are scored.
- Unresolved-question memory is bounded and overflow is pushed into dormant payoff threads.
- Forbidden-knowledge boundaries are injected into character packets.
- Prose-like or robotic public turns can be repaired before they are committed.
- Thought pulses are budgeted and cooldown-limited.
- Recaps are generated from bounded event digests and prior summaries, not raw transcript replay.
- A seeded `story_engine` defines the permanent dramatic north star so the runtime keeps recentering on house survival, hidden records, inheritance conflict, loyalty fractures, and unstable attraction.

## Design Tradeoffs

- Sync SQLAlchemy was chosen over async ORM complexity to keep the data layer reliable and straightforward.
- Prompt templates are plain editable markdown files instead of deeply embedded strings.
- A degraded-mode fallback exists to protect continuity during transient model failures.
- Terminal-first output keeps the MVP narrow while preserving later OBS and YouTube integration paths.
