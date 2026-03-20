# Lantern House Agent Rules

Every code change in this repository must preserve these constraints:

1. Fail safe first.
   The live stream must keep running conservatively when a subsystem fails. Prefer bounded fallback, last-good-state reuse, cooldowns, and structured recovery over crashing the loop.

2. Never leak internals into the public stream.
   Debug text, stack traces, retry notices, validation errors, and recovery messages must never be rendered as chat, recap, or thought-pulse output.

3. Log every recovered failure with context.
   Recovered or suppressed failures must be written to `logs/error.txt` with operation name, failure reason, context, expectations, retry guidance, and fallback choice so later Codex passes can repair them.

4. Keep hot-patch compatibility.
   New code should be safe to soft-reload during a live run whenever feasible. Avoid unnecessary global side effects, one-shot import-time state, and patterns that prevent runtime service rebuilds.

5. Protect continuity.
   If an operation cannot complete safely, prefer skipping or degrading that step over emitting unpersisted or off-canon public output.

6. Be explicit about boundaries.
   Functions and services should validate inputs, explain what they expected, and offer a retry path to callers or recovery wrappers instead of failing opaquely.
