<!-- Lantern House core instruction: stay fail-safe, never leak debug or error text into the live chat, log recovered failures to logs/error.txt with context, and preserve hot-patch compatibility for uninterrupted long-running operation. -->
# Operations

## Local Runtime Requirements

- Python 3.12+
- MySQL 8.4
- Ollama running locally
- `gemma3:1b`, `gemma3:4b`, and `gemma3:12b` pulled into Ollama

## Recommended Startup Sequence

```bash
./start.sh
```

`./start.sh` is the preferred operator entrypoint. It creates or repairs the virtual environment, installs dependencies when needed, ensures the configured MySQL database exists, ensures Ollama and the configured models are available, runs `migrate`, runs idempotent `seed`, performs `healthcheck`, and then starts the resumable live runtime under a restart supervisor.

Useful variants:

```bash
./start.sh --once
./start.sh --config /absolute/path/to/runtime.toml
./start.sh --no-restart
```

If you want manual control instead of the supervisor, the old CLI sequence still works:

```bash
source .venv/bin/activate
lantern-house healthcheck
lantern-house migrate
lantern-house seed
lantern-house dashboard
lantern-house broadcast-assets --limit 5
lantern-house simulate --hours 24 --turns-per-hour 90
lantern-house soak-audit
lantern-house run
```

If you are moving from an older story bible to the current globally optimized cast, reseed into a fresh database so the new character-context fields and seed canon are consistent.

## Live Steering

- Edit [update.txt](/Users/andreborchert/Library/CloudStorage/Dropbox/Chatbot/update.txt) to steer the live story from subscriber votes.
- Edit [viewer_signals.yaml](/Users/andreborchert/Library/CloudStorage/Dropbox/Chatbot/viewer_signals.yaml) to feed in real audience observations like ship spikes, theory bursts, faction splits, clip replays, or recap drop-off.
- Drop harvested YouTube-native JSONL files into [youtube_signals/README.md](/Users/andreborchert/Library/CloudStorage/Dropbox/Chatbot/youtube_signals/README.md)'s directory structure when you want the runtime to derive signals from comments, clips, retention, or live chat.
- The runtime checks the file every 10 minutes by default.
- The viewer-signal layer also polls every 10 minutes by default and persists only bounded active signals, so noisy observations age out instead of bloating canon.
- The YouTube adapter reads harvested JSONL files incrementally and persists file offsets, so large backlogs do not replay from the beginning after restarts.
- Relative paths in config are resolved from the active config file location, so custom runtime TOML files can safely point at their own `update.txt`, log directory, and optional custom seed YAML.
- The manager interprets those changes gradually over the configured rollout window, which defaults to 24 hours.
- Use the file for tone dials, cast additions/removals, location changes, relationship votes, freeform requests, and "must happen" or "avoid for now" guidance.
- Major vote requests are compiled into staged rollout beats and stored both in the existing `beats` table and in dedicated rollout-tracking tables.
- Later rollout beats stay gated by their due windows, so a long-form request like a baby arc must pass through prerequisite relationship and domestic beats before payoff.

## Operational Behavior

- The runtime keeps a persistent `run_state` row with the last tick, message, recap hour, and degraded-mode markers.
- `start.sh` relies on that persisted `run_state`, recap state, checkpoints, and canon memory so a restart resumes the live story instead of reseeding or starting over.
- The runtime also keeps a persistent `house_state` row that models financial pressure, repair backlog, inspections, weather strain, fatigue, and reputation risk.
- The runtime also keeps a persistent hourly beat ledger so each clock hour can be audited for real progression.
- The runtime also keeps a deterministic daily-life schedule so shifts, chores, meals, guest movement, and private appointments create grounded scene collisions.
- The runtime also keeps a payoff-debt ledger so unresolved lies, promises, clues, threats, flirtations, and rollout outcomes have due windows and revival pressure.
- The runtime also keeps a persistent daily and weekly programming grid so the manager and strategist can see whether the day and week are landing planned tentpoles.
- The runtime also keeps a `30d` and `90d` season planner so the strategist can steer toward larger reveal windows, ship cycles, and cast-refresh points.
- The runtime also keeps multi-window canon capsules so long memory stays bounded and queryable.
- The runtime also keeps canon-court findings, monetization packages, timeline facts, object-possession state, viewer signals, and broadcast-asset packages so contradiction risk, world grounding, and reusable YouTube packaging stay visible as structured telemetry.
- The runtime also keeps a persistent `story_gravity_state` row that tracks the north star, active axes, dormant threads, recap focus, and drift score.
- The runtime writes a structured checkpoint snapshot into `run_state.metadata` on every configured flush and on a background heartbeat.
- Default settings checkpoint every minute even if the scene is stalled, and also snapshot on every turn.
- Recovery checks for missed recap windows and produces them on the next start.
- Recovery marks an `unclean-shutdown` continuity flag if the prior process died while `run_state.status` was `starting` or `running`.
- Manager refreshes are interval-based with health-triggered overrides, and after the first directive they are prefetched in the background instead of blocking every visible turn.
- A background God-AI planner uses `gemma3:12b` plus the deterministic simulation lab to persist strategic briefs during live operation.
- The strategist stack also persists simulation runs, strategy rankings, recap-quality scores, public-turn reviews, clip-value scores, fandom signals, dormant-thread registry rows, highlight packages, and soak-audit runs.
- The strategist stack also persists programming-grid slots, canon-court findings, monetization packages, and ops-telemetry snapshots.
- The strategist stack also persists daily-life slots, payoff-debt items, YouTube adapter state, and shadow-replay runs.
- `run --once` intentionally skips the God-AI background loop so smoke tests stay fast and deterministic.
- `soak-audit` is the deterministic long-run health command. It uses the same strategy engine as the God-AI stack, but stretches it across `24h`, `72h`, and `7d` horizons to catch slow drift before it hits the live audience.
- Audience-control state from `update.txt` is persisted in `run_state.metadata.audience_control`, so the last good live-vote interpretation survives the next manager step and can survive malformed file edits.
- Viewer-signal state from `viewer_signals.yaml` is persisted in `run_state.metadata.viewer_signals`, so the strategist can keep the last good audience-signal picture if the file is malformed later.
- The manager also receives a story-governance report that checks hourly progression, core-story drift, cliffhanger pressure, and robotic-voice risk.
- The manager also receives pending house-pressure and audience-rollout beats, so practical pressure and vote steering are both staged explicitly.
- The manager also receives programming-grid, season-plan, monetization, canon-court, world-tracking, viewer-signal, daily-life, payoff-debt, inference-policy, broadcast-asset, load, and ops signals so it can trade off story ambition against runtime health.
- Important turns can trigger multi-candidate generation and reranking. Under load, the runtime falls back to single-candidate mode automatically.
- World tracking refreshes room occupancy and house anchors on startup, and then captures new alibi or possession facts after each persisted turn.
- Broadcast assets are created only after a turn is already persisted and scored highly enough, so export packaging can never leak failed or non-canonical output.
- Arc progression is persisted from structured event hits, and unresolved-question memory is capped so long unattended runs do not inflate prompts.
- Recap generation uses compact event digests rather than replaying every event in the raw 12h or 24h window.
- Logs are written to `logs/lantern_house.log`.
- Structured failure context is written to `logs/error.txt`.
- Console logging is disabled by default during `run`, so the live operator terminal stays clean for story output only.
- Runtime hot-patch scanning watches `src/lantern_house` plus the active config file, `.env`, and the resolved audience steering file path, so a `--config` runtime does not silently fall back to the default example config during a reload.
- Runtime hot-patch scanning also watches the resolved YouTube-signal harvest directory, and shadow validation can be triggered manually with `lantern-house shadow-check`.
- `lantern-house shadow-check` now runs both the seeded shadow canary and a recent-turn shadow replay, so hot patches have to clear static wiring and live-turn regression checks.

## Failure Handling

- If Ollama times out, the runtime retries with backoff.
- If Ollama slows down persistently, the inference governor shortens timeouts, trims retry budgets, disables noncritical model roles, and preserves the visible loop first.
- CLI commands fail with concise operator messages and also log structured failure context to `logs/error.txt`; normal setup mistakes should not dump raw Python tracebacks anymore.
- Manager and God-AI paths use shorter retry budgets than character turns because both have deterministic fallbacks and should fail over quickly.
- If the model response is malformed, the client attempts JSON extraction before falling back.
- If a character payload omits optional-but-expected relationship details, the coercion layer fills safe defaults instead of crashing the turn.
- If a generated turn is low-value, overly generic, or drifts into prose, the lightweight critic can force a conservative repair before persistence.
- If model generation still fails and degraded mode is enabled, the service emits conservative continuity-safe output.
- If a generated chat turn reads like robotic dialogue or prose narration, the runtime first tries the configured small repair model and then falls back to a continuity-safe deterministic line if repair fails.
- Critical runtime calls are wrapped in a fail-safe executor that can reuse last-good state, fall back conservatively, and apply cooldowns after repeated failures.
- Hot-patch failures are logged and ignored; the process keeps running on the previous healthy runtime bundle.
- Hot-patch shadow validation runs before a live rebuild when enabled. If the canary fails, the rebuild is rejected and the current runtime bundle stays live.
- Hot-patch promotion also rejects patches that fail shadow replay against recent persisted turns, so a patch can be blocked even if the seeded canary still passes.
- New governance-table reads and writes degrade to empty or no-op behavior if code is deployed before migrations land, so live hot patches do not immediately crash the stream on missing-table errors.
- Internal errors, retries, and recovery notices must never be emitted into the public chat stream.
- Internal errors, retries, and recovery notices should also stay out of the live operator console unless `logging.console_enabled=true` is set explicitly.
- Live reload intentionally excludes SQLAlchemy ORM model modules and database schema changes; those still require a controlled migration window.

## Extension Points

- Add more arcs or revise secrets in `src/lantern_house/seeds/story_bible.yaml`
- Tune prompt behavior in `src/lantern_house/prompts`
- Adjust pacing thresholds in configuration
- Tune daily-life cadence, payoff-debt windows, inference budgets, YouTube adapter thresholds, daily/weekly/season tentpoles, viewer-signal polling, world-tracking thresholds, multi-candidate selection, broadcast packaging, load thresholds, canon-court behavior, monetization packaging, and ops dashboard rules in `config.example.toml`
- Replace the terminal renderer with a stream adapter later without rewriting the domain layer
