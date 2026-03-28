# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.

# YouTube Signal Harvest

This directory is the local-first intake point for real audience-signal harvests.

The runtime can read these JSONL files:

- `comments.jsonl`
- `clips.jsonl`
- `retention.jsonl`
- `live_chat.jsonl`

Each line must be one JSON object. Invalid lines are ignored conservatively.

Recommended shapes:

`comments.jsonl`
```json
{"text":"Amelia and Rafael are doomed but I can't stop watching","likes":17}
```

`clips.jsonl`
```json
{"title":"Lucía just changed the ownership war","text":"If the codicil is fake, someone wanted the house buried.","views":1200}
```

`retention.jsonl`
```json
{"segment":"00:12:00-00:15:00","drop_percent":4,"summary":"Viewers stayed through the ledger argument."}
```

`live_chat.jsonl`
```json
{"text":"Hana knows way too much","author":"viewer42"}
```

These files steer strategy only. They do not directly override canon.
