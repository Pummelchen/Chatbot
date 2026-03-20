# Operations

## Local Runtime Requirements

- Python 3.12+
- MySQL 8.4
- Ollama running locally
- `gemma3:1b` and `gemma3:4b` pulled into Ollama

## Recommended Startup Sequence

```bash
source .venv/bin/activate
lantern-house healthcheck
lantern-house migrate
lantern-house seed
lantern-house run
```

If you are moving from an older story bible to the current globally optimized cast, reseed into a fresh database so the new character-context fields and seed canon are consistent.

## Operational Behavior

- The runtime keeps a persistent `run_state` row with the last tick, message, recap hour, and degraded-mode markers.
- The runtime writes a structured checkpoint snapshot into `run_state.metadata` on every configured flush and on a background heartbeat.
- Default settings checkpoint every minute even if the scene is stalled, and also snapshot on every turn.
- Recovery checks for missed recap windows and produces them on the next start.
- Recovery marks an `unclean-shutdown` continuity flag if the prior process died while `run_state.status` was `starting` or `running`.
- Manager refreshes are interval-based with health-triggered overrides, and after the first directive they can complete in the background instead of blocking every visible turn.
- The manager also receives a story-governance report that checks hourly progression, core-story drift, cliffhanger pressure, and robotic-voice risk.
- Arc progression is persisted from structured event hits, and unresolved-question memory is capped so long unattended runs do not inflate prompts.
- Recap generation uses compact event digests rather than replaying every event in the raw 12h or 24h window.
- Logs are written to `logs/lantern_house.log`.

## Failure Handling

- If Ollama times out, the runtime retries with backoff.
- If the model response is malformed, the client attempts JSON extraction before falling back.
- If a character payload omits optional-but-expected relationship details, the coercion layer fills safe defaults instead of crashing the turn.
- If model generation still fails and degraded mode is enabled, the service emits conservative continuity-safe output.
- If a generated chat turn reads like robotic dialogue or prose narration, the runtime can repair it with a continuity-safe fallback before persistence.
- Database errors should stop the runtime rather than risk silent canon loss.

## Extension Points

- Add more arcs or revise secrets in `src/lantern_house/seeds/story_bible.yaml`
- Tune prompt behavior in `src/lantern_house/prompts`
- Adjust pacing thresholds in configuration
- Replace the terminal renderer with a stream adapter later without rewriting the domain layer
