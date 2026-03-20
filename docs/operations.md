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

## Operational Behavior

- The runtime keeps a persistent `run_state` row with the last tick, message, recap hour, and degraded-mode markers.
- Recovery checks for missed recap windows and produces them on the next start.
- Manager refreshes are interval-based with health-triggered overrides.
- Logs are written to `logs/lantern_house.log`.

## Failure Handling

- If Ollama times out, the runtime retries with backoff.
- If the model response is malformed, the client attempts JSON extraction before falling back.
- If model generation still fails and degraded mode is enabled, the service emits conservative continuity-safe output.
- Database errors should stop the runtime rather than risk silent canon loss.

## Extension Points

- Add more arcs or revise secrets in `src/lantern_house/seeds/story_bible.yaml`
- Tune prompt behavior in `src/lantern_house/prompts`
- Adjust pacing thresholds in configuration
- Replace the terminal renderer with a stream adapter later without rewriting the domain layer

