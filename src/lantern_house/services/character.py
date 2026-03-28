# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from copy import deepcopy
from typing import ClassVar

from lantern_house.domain.contracts import (
    CharacterContextPacket,
    CharacterTurn,
    EventCandidate,
    InferencePolicySnapshot,
    RelationshipUpdate,
    TurnCriticReport,
)
from lantern_house.domain.enums import EventType
from lantern_house.llm.ollama import InvocationStats, OllamaClient
from lantern_house.runtime.failsafe import log_call_failure
from lantern_house.utils.resources import render_template


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
    _TEMPLATE_MESSAGE_MARKERS: ClassVar[set[str]] = {
        "the visible message",
        "visible message",
        "the public message",
    }
    _INVALID_THOUGHT_PULSE_MARKERS: ClassVar[set[str]] = {
        "rare",
        "null",
        "none",
        "n/a",
        "short internal pulse",
        "one short internal sentence",
        "rare short internal pulse or null",
        "one short internal sentence or null",
    }

    def __init__(
        self,
        llm: OllamaClient,
        model_name: str,
        repair_model_name: str | None = None,
    ) -> None:
        self.llm = llm
        self.model_name = model_name
        self.repair_model_name = repair_model_name or model_name

    async def generate(
        self,
        *,
        packet: CharacterContextPacket,
        thought_pulse_allowed: bool,
        policy: InferencePolicySnapshot | None = None,
    ) -> tuple[CharacterTurn, InvocationStats | None, bool]:
        turns = await self.generate_candidates(
            packet=packet,
            thought_pulse_allowed=thought_pulse_allowed,
            candidate_count=1,
            policy=policy,
        )
        return turns[0]

    async def generate_candidates(
        self,
        *,
        packet: CharacterContextPacket,
        thought_pulse_allowed: bool,
        candidate_count: int = 2,
        policy: InferencePolicySnapshot | None = None,
    ) -> list[tuple[CharacterTurn, InvocationStats | None, bool]]:
        attempts = max(1, min(3, candidate_count))
        candidates: list[tuple[CharacterTurn, InvocationStats | None, bool]] = []
        for index in range(attempts):
            turn, stats, degraded = await self._invoke_turn(
                packet=packet,
                thought_pulse_allowed=thought_pulse_allowed,
                variation_index=index,
                multi_candidate=attempts > 1,
                policy=policy,
            )
            candidates.append((turn, stats, degraded))
        return candidates

    async def _invoke_turn(
        self,
        *,
        packet: CharacterContextPacket,
        thought_pulse_allowed: bool,
        variation_index: int,
        multi_candidate: bool,
        policy: InferencePolicySnapshot | None,
    ) -> tuple[CharacterTurn, InvocationStats | None, bool]:
        prompt = render_template(
            "lantern_house.prompts",
            "character.md",
            {
                "CHARACTER_CONTEXT": {
                    **packet.model_dump(mode="json"),
                    "candidate_variation_note": (
                        f"Variation lane {variation_index + 1}: keep the same canon and voice, "
                        "but choose a different phrasing, leverage point, or emotional tactic."
                        if multi_candidate
                else ""
                    ),
                },
                "THOUGHT_PULSE_ALLOWED": "true" if thought_pulse_allowed else "false",
            },
        )
        if policy is not None and not policy.allow_model_call:
            return self._fallback(packet, thought_pulse_allowed=thought_pulse_allowed), None, True
        try:
            payload, stats = await self.llm.generate_json(
                model=self.model_name,
                prompt=prompt,
                temperature=0.9 if variation_index == 0 else 0.82,
                max_retries=policy.max_retries if policy is not None else None,
                timeout_seconds=policy.timeout_seconds if policy is not None else None,
            )
            payload = self._coerce_payload(payload)
            turn = CharacterTurn.model_validate(payload)
            sanitized = self._sanitize(turn, thought_pulse_allowed=thought_pulse_allowed)
            if self._looks_like_template_leak(sanitized):
                raise ValueError("character model echoed prompt template placeholders")
            return sanitized, stats, False
        except Exception as exc:
            log_call_failure(
                "character.generate",
                exc,
                context={
                    "character_slug": packet.character_slug,
                    "model": self.model_name,
                    "location": packet.current_location,
                    "variation_index": variation_index,
                },
                expected_inputs=[
                    "A valid character context packet.",
                    "A JSON character turn matching CharacterTurn.",
                ],
                retry_advice=(
                    "Retry with a valid JSON turn payload or let the continuity-safe character "
                    "fallback carry the live chat."
                ),
                fallback_used="deterministic-character-fallback",
            )
            return self._fallback(packet, thought_pulse_allowed=thought_pulse_allowed), None, True

    def _sanitize(self, turn: CharacterTurn, *, thought_pulse_allowed: bool) -> CharacterTurn:
        message = " ".join(turn.public_message.split())
        if len(message) > 280:
            message = message[:277].rstrip() + "..."
        return CharacterTurn(
            public_message=message,
            thought_pulse=self._sanitize_thought_pulse(
                turn.thought_pulse,
                thought_pulse_allowed=thought_pulse_allowed,
            ),
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

    async def repair_with_model(
        self,
        *,
        packet: CharacterContextPacket,
        original_turn: CharacterTurn,
        critic_report: TurnCriticReport,
        thought_pulse_allowed: bool,
        policy: InferencePolicySnapshot | None = None,
    ) -> tuple[CharacterTurn, InvocationStats | None, bool]:
        prompt = render_template(
            "lantern_house.prompts",
            "repair.md",
            {
                "CHARACTER_CONTEXT": packet.model_dump(mode="json"),
                "ORIGINAL_TURN": original_turn.model_dump(mode="json"),
                "CRITIC_REPORT": critic_report.model_dump(mode="json"),
                "THOUGHT_PULSE_ALLOWED": "true" if thought_pulse_allowed else "false",
            },
        )
        if policy is not None and not policy.allow_model_call:
            return self._fallback(packet, thought_pulse_allowed=thought_pulse_allowed), None, True
        try:
            payload, stats = await self.llm.generate_json(
                model=self.repair_model_name,
                prompt=prompt,
                temperature=0.35,
                max_output_tokens=260,
                max_retries=policy.max_retries if policy is not None else 1,
                timeout_seconds=policy.timeout_seconds if policy is not None else None,
            )
            turn = CharacterTurn.model_validate(self._coerce_payload(payload))
            sanitized = self._sanitize(turn, thought_pulse_allowed=thought_pulse_allowed)
            if self._looks_like_template_leak(sanitized):
                raise ValueError("repair model echoed template placeholders")
            return sanitized, stats, False
        except Exception as exc:
            log_call_failure(
                "character.repair_with_model",
                exc,
                context={
                    "character_slug": packet.character_slug,
                    "model": self.repair_model_name,
                    "critic_reasons": critic_report.reasons,
                },
                expected_inputs=[
                    "A valid character context packet.",
                    "A valid original CharacterTurn.",
                    "A JSON repaired turn matching CharacterTurn.",
                ],
                retry_advice=(
                    "Retry with a valid repaired JSON turn or let the deterministic fallback "
                    "protect the live stream."
                ),
                fallback_used="deterministic-character-fallback",
            )
            return self._fallback(packet, thought_pulse_allowed=thought_pulse_allowed), None, True

    def _fallback(
        self, packet: CharacterContextPacket, *, thought_pulse_allowed: bool
    ) -> CharacterTurn:
        directive_lead = packet.manager_directive.split(".")[0].lower()
        message = f"I can keep pretending this is normal, but {directive_lead} isn't going away."
        live_pressure = packet.live_pressures[0] if packet.live_pressures else ""
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
        if live_pressure:
            message = f"{message} Also, {live_pressure.lower().rstrip('.')}."
        if packet.daily_life_schedule:
            message = f"{message} I still have {packet.daily_life_schedule[0].lower().rstrip('.')}."
        if packet.payoff_debt_pressure:
            message = f"{message} And {packet.payoff_debt_pressure[0].lower().rstrip('.')}."

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

    def _sanitize_thought_pulse(
        self,
        value: str | None,
        *,
        thought_pulse_allowed: bool,
    ) -> str | None:
        if not thought_pulse_allowed or not value:
            return None
        pulse = " ".join(str(value).split())[:160].strip("\"'")
        if not pulse:
            return None
        lowered = pulse.lower().rstrip(".")
        if lowered in self._EMPTY_MARKERS or lowered in self._INVALID_THOUGHT_PULSE_MARKERS:
            return None
        if len(pulse.split()) < 2:
            return None
        return pulse

    def _looks_like_template_leak(self, turn: CharacterTurn) -> bool:
        message = " ".join(turn.public_message.lower().split()).strip("\"'")
        if message in self._TEMPLATE_MESSAGE_MARKERS:
            return True
        if any(
            candidate.title.lower() == "short event title" for candidate in turn.event_candidates
        ):
            return True
        if any(
            update.summary.lower() == "why the relationship shifted"
            for update in turn.relationship_updates
        ):
            return True
        return False
