from __future__ import annotations

import json
import logging

from lantern_house.domain.contracts import CharacterContextPacket, CharacterTurn, EventCandidate, RelationshipUpdate
from lantern_house.domain.enums import EventType
from lantern_house.llm.ollama import InvocationStats, OllamaClient, OllamaClientError
from lantern_house.utils.resources import render_template

logger = logging.getLogger(__name__)


class CharacterService:
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
            payload, stats = await self.llm.generate_json(model=self.model_name, prompt=prompt, temperature=0.9)
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
            new_questions=turn.new_questions[:2],
            answered_questions=turn.answered_questions[:2],
            tone=turn.tone,
            silence=False,
        )

    def _fallback(self, packet: CharacterContextPacket, *, thought_pulse_allowed: bool) -> CharacterTurn:
        other = packet.relationship_snapshots[0] if packet.relationship_snapshots else "someone in the room"
        message = (
            f"I can keep pretending this is normal, but {packet.manager_directive.split('.')[0].lower()} isn't going away."
        )
        if packet.character_slug == "nia":
            message = "If everyone is going to lie in shifts, at least let me schedule the lies so the lobby stays charming."
        elif packet.character_slug == "elias":
            message = "If we're opening old doors tonight, pick one and stop hovering like the house owes you courage."
        elif packet.character_slug == "mara":
            message = "No one is tearing this place open on adrenaline. Say what you actually want, then we decide."
        elif packet.character_slug == "sora":
            message = "Interesting how every answer in this house arrives wearing a different disguise."
        elif packet.character_slug == "julian":
            message = "I would love to be treated like the problem after someone shows me a document that isn't already lying."
        elif packet.character_slug == "luca":
            message = "Funny thing about old houses: they remember who ran when the storm got personal."

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
                    summary=f"{packet.character_slug} forced tension into the open around {target_slug}.",
                )
            )

        pulse = None
        if thought_pulse_allowed:
            pulse = f"I am closer to saying the wrong thing than they know."
        return CharacterTurn(
            public_message=message,
            thought_pulse=pulse,
            event_candidates=events,
            relationship_updates=relationship_updates,
            tone="sharp",
            silence=False,
        )
