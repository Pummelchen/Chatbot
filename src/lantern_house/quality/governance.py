# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import re
from datetime import timedelta
from typing import ClassVar

from lantern_house.domain.contracts import (
    EventView,
    MessageView,
    StoryGovernanceReport,
    SummaryView,
)
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
        summaries: list[SummaryView] | None,
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

        trust_progression = sum(
            1
            for event in events_last_hour
            if event.event_type in {"relationship", "alliance"} and event.significance >= 6
        )
        desire_progression = sum(
            1
            for event in events_last_hour
            if event.event_type == "romance" and event.significance >= 6
        )
        evidence_progression = sum(
            1
            for event in events_last_hour
            if event.event_type in {"clue", "reveal", "question"} and event.significance >= 6
        )
        debt_progression = sum(
            1
            for event in events_last_hour
            if event.event_type == "financial" and event.significance >= 6
        )
        power_progression = sum(
            1
            for event in events_last_hour
            if event.event_type in {"conflict", "threat", "reveal"} and event.significance >= 6
        )
        loyalty_progression = sum(
            1
            for event in events_last_hour
            if event.event_type in {"alliance", "relationship", "conflict"}
            and event.significance >= 6
        )

        active_gravity_axes = self._active_gravity_axes(
            messages=messages, events=events, story_engine=story_engine
        )
        core_drift = bool(story_engine.get("core_tensions")) and len(active_gravity_axes) < 2
        if core_drift:
            score -= 20

        robotic_voice_risk = self._robotic_voice_risk(messages)
        if robotic_voice_risk:
            score -= 15

        repeated_dialogue_patterns = self._repeated_dialogue_patterns(messages)
        if repeated_dialogue_patterns:
            score -= 8

        collapsing_distinctiveness = self._collapsing_distinctiveness(messages)
        if collapsing_distinctiveness:
            score -= 10

        cliffhanger_pressure_low = self._cliffhanger_pressure_low(messages=messages, events=events)
        if cliffhanger_pressure_low:
            score -= 12

        mystery_flattened = evidence_progression == 0 and not any(
            event.event_type in {"clue", "question", "reveal"} for event in events[-8:]
        )
        if mystery_flattened:
            score -= 10

        romance_flattened = desire_progression == 0 and not any(
            event.event_type == "romance" for event in events[-8:]
        )
        if romance_flattened:
            score -= 8

        recap_weakness = self._recap_weakness(summaries or [])
        if recap_weakness:
            score -= 8

        unresolved_thread_overload = len(unresolved_questions) > 8
        if unresolved_thread_overload:
            score -= 10

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
        if repeated_dialogue_patterns:
            recommendations.append(
                "Break the repeated dialogue loop with a new object, practical problem, or "
                "character pairing."
            )
        if collapsing_distinctiveness:
            recommendations.append(
                "Separate voices more sharply through motive, class pressure, shame, and humor."
            )
        if mystery_flattened:
            recommendations.append(
                "Feed one new inconsistency, clue, or sharper question into the next hour."
            )
        if romance_flattened:
            recommendations.append(
                "Push interrupted intimacy, jealousy, or an almost-confession back into play."
            )
        if recap_weakness:
            recommendations.append(
                "Strengthen recap material with cleaner clues, clearer emotional shifts, and a "
                "stronger watch-next hook."
            )
        if unresolved_thread_overload:
            recommendations.append(
                "Pay off or archive one weak thread so the open-question stack stays legible."
            )
        if unresolved_questions and not events_last_hour:
            recommendations.append(
                "Push one open question back into the room before the current hour closes."
            )

        clip_value_score = _bound_score(
            42
            + evidence_progression * 10
            + desire_progression * 8
            + power_progression * 7
            - int(robotic_voice_risk) * 10
        )
        reentry_value_score = _bound_score(
            48
            + meaningful_progressions_last_hour * 10
            + len(active_gravity_axes) * 5
            - int(recap_weakness) * 12
            - int(unresolved_thread_overload) * 8
        )
        fandom_discussion_value = _bound_score(
            45
            + desire_progression * 9
            + evidence_progression * 8
            + loyalty_progression * 6
            + int(cliffhanger_pressure_low is False) * 8
            - int(collapsing_distinctiveness) * 8
        )
        daily_uniqueness_score = _bound_score(
            44
            + len({event.event_type for event in events_last_hour}) * 8
            + len(active_gravity_axes) * 4
            - int(repeated_dialogue_patterns) * 10
        )

        return StoryGovernanceReport(
            viewer_value_score=max(0, min(100, score)),
            hourly_progression_met=hourly_progression_met,
            meaningful_progressions_last_hour=meaningful_progressions_last_hour,
            trust_progression_last_hour=trust_progression,
            desire_progression_last_hour=desire_progression,
            evidence_progression_last_hour=evidence_progression,
            debt_pressure_progression_last_hour=debt_progression,
            power_progression_last_hour=power_progression,
            loyalty_progression_last_hour=loyalty_progression,
            core_drift=core_drift,
            robotic_voice_risk=robotic_voice_risk,
            cliffhanger_pressure_low=cliffhanger_pressure_low,
            repeated_dialogue_patterns=repeated_dialogue_patterns,
            collapsing_distinctiveness=collapsing_distinctiveness,
            mystery_flattened=mystery_flattened,
            romance_flattened=romance_flattened,
            recap_weakness=recap_weakness,
            unresolved_thread_overload=unresolved_thread_overload,
            clip_value_score=clip_value_score,
            reentry_value_score=reentry_value_score,
            fandom_discussion_value=fandom_discussion_value,
            daily_uniqueness_score=daily_uniqueness_score,
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

    def _repeated_dialogue_patterns(self, messages: list[MessageView]) -> bool:
        recent = messages[-6:]
        if len(recent) < 4:
            return False
        stems = [
            " ".join(re.sub(r"[^a-z0-9 ]+", "", message.content.lower()).split()[:4])
            for message in recent
        ]
        return len(stems) - len(set(stems)) >= 2

    def _collapsing_distinctiveness(self, messages: list[MessageView]) -> bool:
        recent = messages[-6:]
        if len(recent) < 4:
            return False
        speaker_profiles: dict[str, set[str]] = {}
        for message in recent:
            speaker_profiles.setdefault(message.speaker_label, set()).update(
                re.findall(r"[a-z]{4,}", message.content.lower())
            )
        if len(speaker_profiles) < 2:
            return False
        profiles = list(speaker_profiles.values())
        if len(profiles) < 2:
            return False
        overlap = len(profiles[0].intersection(*profiles[1:]))
        smallest = min(len(profile) for profile in profiles)
        return smallest > 0 and overlap >= smallest

    def _recap_weakness(self, summaries: list[SummaryView]) -> bool:
        if not summaries:
            return False
        latest = summaries[-1].content.lower()
        generic_hits = sum(marker in latest for marker in self._GENERIC_MARKERS)
        return generic_hits >= 2 or latest.count("|") < 4

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


def _bound_score(value: int) -> int:
    return max(0, min(100, value))
