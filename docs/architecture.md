# Architecture Overview

## System Shape

Lantern House is split into five major layers:

1. `db`: SQLAlchemy models, sessions, repositories, migrations
2. `context`: selective retrieval and prompt-packet assembly
3. `services`: manager, character, recap, event extraction, seeding
4. `runtime`: scheduler, orchestrator, recovery, long-running loop
5. `rendering`: terminal presentation for public output

## Runtime Loop

Each loop iteration follows the same pattern:

1. Recover or refresh run-state data.
2. Check whether full-clock-hour recaps are due.
3. Evaluate pacing and continuity health.
4. Refresh the manager directive when required.
5. Select the next speaker based on scene state, weights, recency, and burst/lull logic.
6. Build a selective character context packet.
7. Generate a structured turn from Ollama.
8. Extract events, apply relationship deltas, persist the result, and optionally emit a thought pulse.
9. Render the public message to the terminal.
10. Sleep for a variable delay before the next turn.

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
- The manager is given pacing health and continuity warnings.
- Repetition, romance stalls, mystery stalls, and low-progression windows are scored.
- Forbidden-knowledge boundaries are injected into character packets.
- Thought pulses are budgeted and cooldown-limited.
- Recaps are generated from event memory, not just messages.

## Design Tradeoffs

- Sync SQLAlchemy was chosen over async ORM complexity to keep the data layer reliable and straightforward.
- Prompt templates are plain editable markdown files instead of deeply embedded strings.
- A degraded-mode fallback exists to protect continuity during transient model failures.
- Terminal-first output keeps the MVP narrow while preserving later OBS and YouTube integration paths.
