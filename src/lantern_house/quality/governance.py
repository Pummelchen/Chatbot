from __future__ import annotations

import re
from datetime import timedelta
from typing import ClassVar

from lantern_house.domain.contracts import EventView, MessageView, StoryGovernanceReport
from lantern_house.utils.time import ensure_utc, utcnow


class StoryGovernanceEvaluator:
    _CLIFFHANGER_TYPES: ClassVar[set[str]] = {
        "question",
        "threat",
        "reveal",
        "romance",
        "conflict",
        "financial",
    }
    _MEANINGFUL_TYPES: ClassVar[set[str]] = {
        "clue",
        "relationship",
        "reveal",
        "question",
        "financial",
        "threat",
        "romance",
        "conflict",
        "alliance",
    }
    _GENERIC_MARKERS = (
        "the truth is",
        "this changes everything",
        "we both know",
        "i can't keep doing this",
        "not like this",
        "it's not that simple",
        "you don't understand",
    )

    def evaluate(
        self,
        *,
        messages: list[MessageView],
        events: list[EventView],
        world_metadata: dict,
        unresolved_questions: list[str],
    ) -> StoryGovernanceReport:
        score = 100
        story_engine = world_metadata.get("story_engine", {})
        last_hour_threshold = utcnow() - timedelta(hours=1)
        events_last_hour = [
            event for event in events if ensure_utc(event.created_at) >= last_hour_threshold
        ]
        meaningful_progressions_last_hour = sum(
            1
            for event in events_last_hour
            if event.event_type in self._MEANINGFUL_TYPES and event.significance >= 6
        )
        hourly_progression_met = meaningful_progressions_last_hour >= 1
        if not hourly_progression_met:
            score -= 25

        active_gravity_axes = self._active_gravity_axes(
            messages=messages, events=events, story_engine=story_engine
        )
        core_drift = bool(story_engine.get("core_tensions")) and len(active_gravity_axes) < 2
        if core_drift:
            score -= 20

        robotic_voice_risk = self._robotic_voice_risk(messages)
        if robotic_voice_risk:
            score -= 15

        cliffhanger_pressure_low = self._cliffhanger_pressure_low(messages=messages, events=events)
        if cliffhanger_pressure_low:
            score -= 12

        recommendations: list[str] = []
        if not hourly_progression_met:
            recommendations.append(
                "Within the next hour, land one irreversible shift in trust, "
                "evidence, debt, or desire."
            )
        if core_drift:
            recommendations.append(
                "Recenter on the house's survival, the ownership fight, "
                "hidden records, and unstable bonds."
            )
        if cliffhanger_pressure_low:
            recommendations.append(
                "End the next exchange with a sharper question, interruption, "
                "threat, or romantic complication."
            )
        if robotic_voice_risk:
            recommendations.append(
                "Use concrete objects, money pressure, family stakes, and "
                "subtext instead of abstract speeches."
            )
        if unresolved_questions and not events_last_hour:
            recommendations.append(
                "Push one open question back into the room before the current hour closes."
            )

        return StoryGovernanceReport(
            viewer_value_score=max(0, min(100, score)),
            hourly_progression_met=hourly_progression_met,
            meaningful_progressions_last_hour=meaningful_progressions_last_hour,
            core_drift=core_drift,
            robotic_voice_risk=robotic_voice_risk,
            cliffhanger_pressure_low=cliffhanger_pressure_low,
            active_gravity_axes=active_gravity_axes,
            recommendations=recommendations,
        )

    def _active_gravity_axes(
        self,
        *,
        messages: list[MessageView],
        events: list[EventView],
        story_engine: dict,
    ) -> list[str]:
        text = " ".join(
            [event.title for event in events[-12:]]
            + [event.details for event in events[-12:]]
            + [message.content for message in messages[-8:]]
        ).lower()
        active: list[str] = []
        for axis in story_engine.get("core_tensions", []):
            keywords = [keyword.lower() for keyword in axis.get("keywords", [])]
            if keywords and any(keyword in text for keyword in keywords):
                active.append(axis.get("key", "unnamed-axis"))
        return active

    def _robotic_voice_risk(self, messages: list[MessageView]) -> bool:
        recent = messages[-8:]
        if len(recent) < 4:
            return False
        stems = []
        generic_hits = 0
        for message in recent:
            lowered = message.content.lower()
            if any(marker in lowered for marker in self._GENERIC_MARKERS):
                generic_hits += 1
            normalized = re.sub(r"[^a-z0-9 ]+", "", lowered)
            stems.append(" ".join(normalized.split()[:3]))
        repeated_stems = len(stems) - len(set(stems))
        return generic_hits >= 2 or repeated_stems >= 3

    def _cliffhanger_pressure_low(
        self, *, messages: list[MessageView], events: list[EventView]
    ) -> bool:
        recent_events = events[-6:]
        if any(event.event_type in self._CLIFFHANGER_TYPES for event in recent_events):
            return False
        recent_messages = messages[-6:]
        suspense_markers = ("?", "if", "unless", "before", "tonight", "now")
        return not any(
            any(marker in message.content.lower() for marker in suspense_markers)
            for message in recent_messages
        )
