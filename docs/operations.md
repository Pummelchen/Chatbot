# Operations

## Local Runtime Requirements

- Python 3.12+
- MySQL 8.4
- Ollama running locally
- `gemma3:1b`, `gemma3:4b`, and `gemma3:12b` pulled into Ollama

## Recommended Startup Sequence

```bash
source .venv/bin/activate
lantern-house healthcheck
lantern-house migrate
lantern-house seed
lantern-house simulate --hours 24 --turns-per-hour 90
lantern-house run
```

If you are moving from an older story bible to the current globally optimized cast, reseed into a fresh database so the new character-context fields and seed canon are consistent.

## Live Steering

- Edit [update.txt](/Users/andreborchert/Library/CloudStorage/Dropbox/Chatbot/update.txt) to steer the live story from subscriber votes.
- The runtime checks the file every 10 minutes by default.
- The manager interprets those changes gradually over the configured rollout window, which defaults to 24 hours.
- Use the file for tone dials, cast additions/removals, location changes, relationship votes, freeform requests, and "must happen" or "avoid for now" guidance.
- Major vote requests are compiled into staged rollout beats and stored in the existing `beats` table.
- Later rollout beats stay gated by their due windows, so a long-form request like a baby arc must pass through prerequisite relationship and domestic beats before payoff.

## Operational Behavior

- The runtime keeps a persistent `run_state` row with the last tick, message, recap hour, and degraded-mode markers.
- The runtime also keeps a persistent `house_state` row that models financial pressure, repair backlog, inspections, weather strain, fatigue, and reputation risk.
- The runtime writes a structured checkpoint snapshot into `run_state.metadata` on every configured flush and on a background heartbeat.
- Default settings checkpoint every minute even if the scene is stalled, and also snapshot on every turn.
- Recovery checks for missed recap windows and produces them on the next start.
- Recovery marks an `unclean-shutdown` continuity flag if the prior process died while `run_state.status` was `starting` or `running`.
- Manager refreshes are interval-based with health-triggered overrides, and after the first directive they are prefetched in the background instead of blocking every visible turn.
- A background God-AI planner uses `gemma3:12b` plus the deterministic simulation lab to persist strategic briefs during live operation.
- `run --once` intentionally skips the God-AI background loop so smoke tests stay fast and deterministic.
- Audience-control state from `update.txt` is persisted in `run_state.metadata.audience_control`, so the last good live-vote interpretation survives the next manager step and can survive malformed file edits.
- The manager also receives a story-governance report that checks hourly progression, core-story drift, cliffhanger pressure, and robotic-voice risk.
- The manager also receives pending house-pressure and audience-rollout beats, so practical pressure and vote steering are both staged explicitly.
- Arc progression is persisted from structured event hits, and unresolved-question memory is capped so long unattended runs do not inflate prompts.
- Recap generation uses compact event digests rather than replaying every event in the raw 12h or 24h window.
- Logs are written to `logs/lantern_house.log`.

## Failure Handling

- If Ollama times out, the runtime retries with backoff.
- Manager and God-AI paths use shorter retry budgets than character turns because both have deterministic fallbacks and should fail over quickly.
- If the model response is malformed, the client attempts JSON extraction before falling back.
- If a character payload omits optional-but-expected relationship details, the coercion layer fills safe defaults instead of crashing the turn.
- If a generated turn is low-value, overly generic, or drifts into prose, the lightweight critic can force a conservative repair before persistence.
- If model generation still fails and degraded mode is enabled, the service emits conservative continuity-safe output.
- If a generated chat turn reads like robotic dialogue or prose narration, the runtime can repair it with a continuity-safe fallback before persistence.
- Database errors should stop the runtime rather than risk silent canon loss.

## Extension Points

- Add more arcs or revise secrets in `src/lantern_house/seeds/story_bible.yaml`
- Tune prompt behavior in `src/lantern_house/prompts`
- Adjust pacing thresholds in configuration
- Replace the terminal renderer with a stream adapter later without rewriting the domain layer
