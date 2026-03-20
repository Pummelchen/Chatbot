from __future__ import annotations

import json
import logging
from collections import Counter

from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import EventView, RecapBundle, RecapWindowSummary
from lantern_house.llm.ollama import OllamaClient, OllamaClientError
from lantern_house.utils.resources import render_template
from lantern_house.utils.time import isoformat

logger = logging.getLogger(__name__)


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

        prompt = render_template(
            "lantern_house.prompts",
            "announcer.md",
            {
                "RECAP_CONTEXT": {
                    "bucket_end_at": isoformat(bucket_end_at),
                    "events_1h": [event.model_dump() for event in events_1h],
                    "events_12h": [event.model_dump() for event in events_12h],
                    "events_24h": [event.model_dump() for event in events_24h],
                    "recent_summaries": [summary.model_dump() for summary in recent_summaries],
                }
            },
        )

        try:
            payload, _stats = await self.llm.generate_json(model=self.model_name, prompt=prompt, temperature=0.5)
            return RecapBundle.model_validate(payload)
        except Exception as exc:
            logger.warning("recap fallback due to model issue: %s", exc)
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
        questions = [
            event.details
            for event in events
            if event.event_type == "question"
        ][:3] or ["Who is protecting the oldest lie now?"]
        clues = [event.title for event in events if event.event_type in {"clue", "reveal", "financial"}][:3]
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
