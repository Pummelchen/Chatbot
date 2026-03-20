from __future__ import annotations

import logging
from copy import deepcopy
from typing import ClassVar

from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    EventCandidate,
    RelationshipUpdate,
)
from lantern_house.domain.enums import EventType
from lantern_house.llm.ollama import InvocationStats, OllamaClient
from lantern_house.utils.resources import render_template

logger = logging.getLogger(__name__)


class CharacterService:
    _QUESTION_LEADS: ClassVar[tuple[str, ...]] = (
        "who",
        "what",
        "why",
        "how",
        "where",
        "when",
        "which",
        "is",
        "are",
        "can",
        "did",
    )
    _EMPTY_MARKERS: ClassVar[set[str]] = {"none", "n/a", "na", "nothing", "unknown"}

    def __init__(self, llm: OllamaClient, model_name: str) -> None:
        self.llm = llm
        self.model_name = model_name

    async def generate(
        self,
        *,
        packet: CharacterContextPacket,
        thought_pulse_allowed: bool,
    ) -> tuple[CharacterTurn, InvocationStats | None, bool]:
        prompt = render_template(
            "lantern_house.prompts",
            "character.md",
            {
                "CHARACTER_CONTEXT": packet.model_dump(),
                "THOUGHT_PULSE_ALLOWED": "true" if thought_pulse_allowed else "false",
            },
        )
        try:
            payload, stats = await self.llm.generate_json(
                model=self.model_name, prompt=prompt, temperature=0.9
            )
            payload = self._coerce_payload(payload)
            turn = CharacterTurn.model_validate(payload)
            sanitized = self._sanitize(turn, thought_pulse_allowed=thought_pulse_allowed)
            return sanitized, stats, False
        except Exception as exc:
            logger.warning("character fallback for %s: %s", packet.character_slug, exc)
            return self._fallback(packet, thought_pulse_allowed=thought_pulse_allowed), None, True

    def _sanitize(self, turn: CharacterTurn, *, thought_pulse_allowed: bool) -> CharacterTurn:
        message = " ".join(turn.public_message.split())
        if len(message) > 280:
            message = message[:277].rstrip() + "..."
        pulse = None
        if thought_pulse_allowed and turn.thought_pulse:
            pulse = " ".join(turn.thought_pulse.split())[:160]
        return CharacterTurn(
            public_message=message,
            thought_pulse=pulse,
            event_candidates=turn.event_candidates[:4],
            relationship_updates=turn.relationship_updates[:3],
            new_questions=self._sanitize_questions(turn.new_questions),
            answered_questions=self._sanitize_questions(turn.answered_questions),
            tone=turn.tone,
            silence=False,
        )

    def repair(
        self,
        *,
        packet: CharacterContextPacket,
        thought_pulse_allowed: bool,
    ) -> CharacterTurn:
        return self._fallback(packet, thought_pulse_allowed=thought_pulse_allowed)

    def _fallback(
        self, packet: CharacterContextPacket, *, thought_pulse_allowed: bool
    ) -> CharacterTurn:
        directive_lead = packet.manager_directive.split(".")[0].lower()
        message = f"I can keep pretending this is normal, but {directive_lead} isn't going away."
        role = packet.ensemble_role.lower()
        if "young worker" in role or "reception" in role or "helper" in role:
            message = (
                "If everyone is going to lie in shifts, "
                "at least let me schedule the lies "
                "so the lobby stays charming."
            )
        elif "handyman" in role or "fixer" in role:
            message = (
                "If we're opening old doors tonight, "
                "pick one and stop hovering like "
                "the house owes you courage."
            )
        elif "manager" in role:
            message = (
                "No one is tearing this place open on adrenaline. "
                "Say what you actually want, then we decide."
            )
        elif "observer" in role or "guest" in role:
            message = (
                "Interesting how every answer in this house arrives wearing a different disguise."
            )
        elif "heir" in role or "claimant" in role or "relative" in role:
            message = (
                "I would love to be treated like the problem "
                "after someone shows me a document "
                "that isn't already lying."
            )
        elif "returning" in role or "past" in role:
            message = (
                "Funny thing about old houses: they remember who ran when the storm got personal."
            )

        events = [
            EventCandidate(
                event_type=EventType.CONFLICT,
                title=f"{packet.character_slug} escalates the room",
                details=message,
                significance=6,
                tags=["fallback"],
            )
        ]
        relationship_updates = []
        if packet.relationship_snapshots:
            target_slug = packet.relationship_snapshots[0].split(":")[0]
            relationship_updates.append(
                RelationshipUpdate(
                    character_slug=target_slug,
                    trust_delta=-1,
                    desire_delta=0,
                    suspicion_delta=1,
                    obligation_delta=0,
                    summary=(
                        f"{packet.character_slug} forced tension "
                        f"into the open around {target_slug}."
                    ),
                )
            )

        pulse = None
        if thought_pulse_allowed:
            pulse = "I am closer to saying the wrong thing than they know."
        return CharacterTurn(
            public_message=message,
            thought_pulse=pulse,
            event_candidates=events,
            relationship_updates=relationship_updates,
            tone="sharp",
            silence=False,
        )

    def _coerce_payload(self, payload: dict) -> dict:
        coerced = deepcopy(payload)
        candidates = coerced.get("event_candidates")
        if isinstance(candidates, list):
            normalized_candidates = []
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                raw_type = candidate.get("event_type")
                candidate["event_type"] = self._coerce_event_type(
                    raw_type,
                    title=str(candidate.get("title", "")),
                    details=str(candidate.get("details", "")),
                )
                normalized_candidates.append(candidate)
            coerced["event_candidates"] = normalized_candidates

        relationship_updates = coerced.get("relationship_updates")
        if isinstance(relationship_updates, list):
            normalized_updates = []
            for update in relationship_updates:
                if not isinstance(update, dict):
                    continue
                character_slug = str(update.get("character_slug", "")).strip()
                if not character_slug:
                    continue
                update["character_slug"] = character_slug
                for delta_key in (
                    "trust_delta",
                    "desire_delta",
                    "suspicion_delta",
                    "obligation_delta",
                ):
                    update[delta_key] = self._coerce_delta(update.get(delta_key))
                summary = str(update.get("summary", "")).strip()
                if not summary:
                    summary = f"Tension shifted around {character_slug}."
                update["summary"] = summary
                normalized_updates.append(update)
            coerced["relationship_updates"] = normalized_updates
        return coerced

    def _coerce_event_type(self, raw_type: object, *, title: str, details: str) -> str:
        if isinstance(raw_type, EventType):
            return raw_type.value

        valid = {item.value for item in EventType}
        text = str(raw_type or "").strip().lower()
        if text in valid:
            return text

        if "|" in text:
            options = [item.strip() for item in text.split("|")]
            for option in options:
                if option in valid:
                    text = option
                    break

        combined = f"{title} {details}".lower()
        heuristics = [
            ("romance", ("kiss", "touch", "want", "flirt", "jealous", "confess")),
            ("financial", ("debt", "invoice", "money", "payment", "sale", "blackwake")),
            ("threat", ("threat", "danger", "warn", "cornered")),
            ("question", ("?", "why", "who", "what", "how")),
            ("reveal", ("admit", "confession", "truth comes out", "finally said")),
            ("clue", ("key", "ledger", "record", "recording", "evidence", "document", "page")),
            ("relationship", ("trust", "alliance", "bond", "distance", "relationship")),
            ("humor", ("joke", "laugh", "funny")),
            ("routine", ("tea", "kitchen", "desk", "clean", "repair")),
        ]
        for event_type, markers in heuristics:
            if any(marker in combined for marker in markers):
                return event_type
        if text in valid:
            return text
        return "conflict"

    def _coerce_delta(self, value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return max(-3, min(3, parsed))

    def _sanitize_questions(self, questions: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for question in questions:
            normalized = " ".join(str(question).split())
            if not normalized:
                continue
            lowered = normalized.lower().rstrip(".")
            if lowered in self._EMPTY_MARKERS:
                continue
            if len(normalized.rstrip("?").split()) < 5:
                continue
            if not normalized.endswith("?") and not lowered.startswith(self._QUESTION_LEADS):
                continue
            if not normalized.endswith("?"):
                normalized = normalized.rstrip(".") + "?"
            key = normalized.lower()
            if key in seen:
                continue
            cleaned.append(normalized)
            seen.add(key)
            if len(cleaned) >= 2:
                break
        return cleaned
