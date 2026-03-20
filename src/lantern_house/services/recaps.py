# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import re
from collections import Counter

from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import EventView, RecapBundle, RecapWindowSummary
from lantern_house.llm.ollama import OllamaClient
from lantern_house.runtime.failsafe import log_call_failure
from lantern_house.utils.resources import render_template
from lantern_house.utils.time import isoformat


class RecapService:
    def __init__(self, repository: StoryRepository, llm: OllamaClient, model_name: str) -> None:
        self.repository = repository
        self.llm = llm
        self.model_name = model_name

    async def generate_bundle(self, *, bucket_end_at) -> RecapBundle:
        events_1h = self.repository.load_events_for_window(bucket_end_at=bucket_end_at, hours=1)
        events_12h = self.repository.load_events_for_window(bucket_end_at=bucket_end_at, hours=12)
        events_24h = self.repository.load_events_for_window(bucket_end_at=bucket_end_at, hours=24)
        recent_summaries = self.repository.list_recent_summaries(limit=4)

        if len(events_24h) < 4:
            return RecapBundle(
                one_hour=self._fallback_window(events_1h, "Last hour"),
                twelve_hours=self._fallback_window(events_12h, "Last 12 hours"),
                twenty_four_hours=self._fallback_window(events_24h, "Last 24 hours"),
            )

        prompt = render_template(
            "lantern_house.prompts",
            "announcer.md",
            {
                "RECAP_CONTEXT": {
                    "bucket_end_at": isoformat(bucket_end_at),
                    "events_1h": self._window_digest(events_1h),
                    "events_12h": self._window_digest(events_12h),
                    "events_24h": self._window_digest(events_24h),
                    "recent_summaries": [summary.model_dump() for summary in recent_summaries],
                }
            },
        )

        try:
            payload, _stats = await self.llm.generate_json(
                model=self.model_name,
                prompt=prompt,
                temperature=0.5,
                max_output_tokens=520,
            )
            bundle = RecapBundle.model_validate(payload)
            if self._mentions_unknown_entities(bundle):
                log_call_failure(
                    "recap.generate_bundle",
                    ValueError("Recap bundle mentioned off-canon entities."),
                    context={
                        "model": self.model_name,
                        "bucket_end_at": isoformat(bucket_end_at),
                    },
                    expected_inputs=[
                        "A recap bundle grounded in current canon entities and stored events."
                    ],
                    retry_advice=(
                        "Retry with a canon-safe recap or let the deterministic recap fallback "
                        "summarize stored events."
                    ),
                    fallback_used="deterministic-recap-fallback",
                )
                return RecapBundle(
                    one_hour=self._fallback_window(events_1h, "Last hour"),
                    twelve_hours=self._fallback_window(events_12h, "Last 12 hours"),
                    twenty_four_hours=self._fallback_window(events_24h, "Last 24 hours"),
                )
            return bundle
        except Exception as exc:
            log_call_failure(
                "recap.generate_bundle",
                exc,
                context={
                    "model": self.model_name,
                    "bucket_end_at": isoformat(bucket_end_at),
                },
                expected_inputs=[
                    "A valid recap prompt context built from stored events and summaries.",
                    "A JSON recap bundle matching RecapBundle.",
                ],
                retry_advice=(
                    "Retry with a valid recap payload or let the deterministic recap fallback "
                    "summarize the current windows."
                ),
                fallback_used="deterministic-recap-fallback",
            )
            return RecapBundle(
                one_hour=self._fallback_window(events_1h, "Last hour"),
                twelve_hours=self._fallback_window(events_12h, "Last 12 hours"),
                twenty_four_hours=self._fallback_window(events_24h, "Last 24 hours"),
            )

    def _fallback_window(self, events: list[EventView], label: str) -> RecapWindowSummary:
        if not events:
            return RecapWindowSummary(
                headline=f"{label}: low visibility, tension still simmering",
                what_changed=["The house stayed in motion without a major breakthrough."],
                emotional_shifts=["Pressure remained controlled but unresolved."],
                clues=["No major clue surfaced."],
                unresolved_questions=["Which hidden pressure will break the calm next?"],
                loyalty_status="Loyalties remain conditional and situational.",
                romance_status="Romantic tension is present but unresolved.",
                watch_next="Watch for the next interruption, clue, or misdirected confession.",
            )

        top = sorted(events, key=lambda item: item.significance, reverse=True)[:3]
        types = Counter(event.event_type for event in events)
        questions = [event.details for event in events if event.event_type == "question"][:3] or [
            "Who is protecting the oldest lie now?"
        ]
        clues = [
            event.title for event in events if event.event_type in {"clue", "reveal", "financial"}
        ][:3]
        emotion = []
        if types.get("conflict"):
            emotion.append("Conflict sharpened inside the house.")
        if types.get("romance"):
            emotion.append("Romantic instability rose.")
        if not emotion:
            emotion.append("Private strain kept leaking into public conversation.")
        loyalty = "Alliances are shifting through pressure rather than trust."
        if types.get("alliance") or types.get("relationship"):
            loyalty = "Trust moved in small but meaningful increments, and nobody is fully safe."
        romance = "Old heat and new attraction continue complicating every practical decision."
        if not types.get("romance"):
            romance = "Romantic tension stayed indirect but active beneath the scene."
        return RecapWindowSummary(
            headline=f"{label}: {top[0].title}",
            what_changed=[event.details for event in top],
            emotional_shifts=emotion,
            clues=clues or ["Suspicion deepened without a clean clue."],
            unresolved_questions=questions,
            loyalty_status=loyalty,
            romance_status=romance,
            watch_next="Watch the next pair of characters who think they can talk privately.",
        )

    def _window_digest(self, events: list[EventView]) -> dict:
        top_events = sorted(events, key=lambda item: item.significance, reverse=True)[:8]
        latest_events = events[-5:]
        questions = [event.details for event in events if event.event_type == "question"][:5]
        return {
            "event_count": len(events),
            "type_counts": dict(Counter(event.event_type for event in events)),
            "top_events": [event.model_dump() for event in top_events],
            "latest_events": [event.model_dump() for event in latest_events],
            "open_questions": questions,
        }

    def _mentions_unknown_entities(self, bundle: RecapBundle) -> bool:
        world_title = self.repository.get_world_state_snapshot()["title"]
        known = {
            *re.findall(r"\b[A-Z][A-Za-zÀ-ÿ'-]{2,}\b", world_title),
            "House",
            "Blackwake",
            "Evelyn",
            "Ren",
        }
        for character in self.repository.list_characters():
            known.update(re.findall(r"\b[A-Z][A-Za-zÀ-ÿ'-]{2,}\b", character["full_name"]))
        neutral = {
            "Last",
            "Trust",
            "Watch",
            "Changed",
            "Emotion",
            "Clues",
            "Questions",
            "Romance",
            "The",
            "A",
            "An",
            "No",
        }
        text = " ".join(
            [
                bundle.one_hour.headline,
                *bundle.one_hour.what_changed,
                *bundle.one_hour.emotional_shifts,
                *bundle.one_hour.clues,
                *bundle.one_hour.unresolved_questions,
                bundle.one_hour.loyalty_status,
                bundle.one_hour.romance_status,
                bundle.one_hour.watch_next,
                bundle.twelve_hours.headline,
                *bundle.twelve_hours.what_changed,
                *bundle.twelve_hours.emotional_shifts,
                *bundle.twelve_hours.clues,
                *bundle.twelve_hours.unresolved_questions,
                bundle.twelve_hours.loyalty_status,
                bundle.twelve_hours.romance_status,
                bundle.twelve_hours.watch_next,
                bundle.twenty_four_hours.headline,
                *bundle.twenty_four_hours.what_changed,
                *bundle.twenty_four_hours.emotional_shifts,
                *bundle.twenty_four_hours.clues,
                *bundle.twenty_four_hours.unresolved_questions,
                bundle.twenty_four_hours.loyalty_status,
                bundle.twenty_four_hours.romance_status,
                bundle.twenty_four_hours.watch_next,
            ]
        )
        tokens = re.findall(r"\b[A-Z][A-Za-zÀ-ÿ'-]{2,}\b", text)
        unknown = [token for token in tokens if token not in known and token not in neutral]
        return len(set(unknown)) >= 3
