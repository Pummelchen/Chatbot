from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, desc, func, or_, select, update

from lantern_house.db import models
from lantern_house.db.session import SessionFactory
from lantern_house.domain.contracts import (
    CharacterTurn,
    ContinuityFlagDraft,
    EventCandidate,
    EventView,
    ManagerDirectivePlan,
    MessageView,
    RelationshipSnapshot,
    StoryArcSnapshot,
    SummaryView,
)
from lantern_house.domain.enums import MessageKind, SummaryWindow
from lantern_house.utils.time import floor_to_hour, utcnow


class StoryRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def seed_exists(self) -> bool:
        with self.session_factory.session_scope() as session:
            return session.scalar(select(func.count(models.Character.id))) > 0

    def ensure_run_state(self) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            run_state = session.scalar(select(models.RunState).where(models.RunState.runtime_key == "primary"))
            if run_state is None:
                run_state = models.RunState(runtime_key="primary", status="idle")
                session.add(run_state)
                session.flush()
            return self._run_state_dict(run_state)

    def get_run_state(self) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            run_state = session.scalar(select(models.RunState).where(models.RunState.runtime_key == "primary"))
            if run_state is None:
                raise RuntimeError("run_state is missing; seed or bootstrap first")
            return self._run_state_dict(run_state)

    def set_runtime_status(self, status: str, *, degraded_mode: bool | None = None) -> None:
        with self.session_factory.session_scope() as session:
            run_state = self._get_run_state_model(session)
            run_state.status = status
            if degraded_mode is not None:
                run_state.degraded_mode = degraded_mode

    def list_missing_recap_hours(self, now=None) -> list:
        now = now or utcnow()
        bucket = floor_to_hour(now)
        run_state = self.get_run_state()
        last_recap = run_state["last_recap_hour"]
        if last_recap is None:
            last_public = run_state["last_public_message_at"]
            if last_public is None or floor_to_hour(last_public) >= bucket:
                return []
            return [bucket]

        hours = []
        current = floor_to_hour(last_recap) + timedelta(hours=1)
        while current <= bucket:
            hours.append(current)
            current += timedelta(hours=1)
        return hours

    def get_character_color_map(self) -> dict[str, str]:
        with self.session_factory.session_scope() as session:
            rows = session.execute(select(models.Character.slug, models.Character.color)).all()
            return {slug: color for slug, color in rows}

    def list_characters(self) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            characters = session.scalars(select(models.Character).order_by(models.Character.id)).all()
            return [
                {
                    "slug": row.slug,
                    "full_name": row.full_name,
                    "public_persona": row.public_persona,
                    "hidden_wound": row.hidden_wound,
                    "long_term_desire": row.long_term_desire,
                    "private_fear": row.private_fear,
                    "message_style": row.message_style,
                    "ensemble_role": row.ensemble_role,
                    "color": row.color,
                }
                for row in characters
            ]

    def list_character_states(self) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            stmt = (
                select(models.Character.slug, models.CharacterState.last_spoke_at, models.CharacterState.silence_streak)
                .join(models.CharacterState, models.Character.id == models.CharacterState.character_id)
                .order_by(models.Character.id)
            )
            return [
                {"slug": slug, "last_spoke_at": last_spoke_at, "silence_streak": silence_streak}
                for slug, last_spoke_at, silence_streak in session.execute(stmt).all()
            ]

    def get_character_overview(self, slug: str) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            stmt = (
                select(models.Character, models.CharacterState, models.Location)
                .join(models.CharacterState, models.Character.id == models.CharacterState.character_id)
                .join(models.Location, models.Location.id == models.CharacterState.current_location_id, isouter=True)
                .where(models.Character.slug == slug)
            )
            row = session.execute(stmt).one_or_none()
            if row is None:
                raise KeyError(f"Unknown character slug: {slug}")
            character, state, location = row
            return {
                "slug": character.slug,
                "full_name": character.full_name,
                "public_persona": character.public_persona,
                "hidden_wound": character.hidden_wound,
                "long_term_desire": character.long_term_desire,
                "private_fear": character.private_fear,
                "message_style": character.message_style,
                "ensemble_role": character.ensemble_role,
                "location_name": location.name if location else "Unknown",
                "emotional_state": state.emotional_state,
                "current_goals": state.active_goals,
                "stress_level": state.stress_level,
                "romance_heat": state.romance_heat,
            }

    def list_relationship_snapshots(self, slug: str) -> list[RelationshipSnapshot]:
        with self.session_factory.session_scope() as session:
            character = session.scalar(select(models.Character).where(models.Character.slug == slug))
            if character is None:
                raise KeyError(slug)
            stmt = (
                select(models.Relationship, models.Character.slug)
                .join(
                    models.Character,
                    or_(
                        and_(
                            models.Character.id == models.Relationship.character_a_id,
                            models.Relationship.character_b_id == character.id,
                        ),
                        and_(
                            models.Character.id == models.Relationship.character_b_id,
                            models.Relationship.character_a_id == character.id,
                        ),
                    ),
                )
                .where(
                    or_(
                        models.Relationship.character_a_id == character.id,
                        models.Relationship.character_b_id == character.id,
                    )
                )
            )
            result = []
            for relationship, counterpart_slug in session.execute(stmt).all():
                result.append(
                    RelationshipSnapshot(
                        counterpart_slug=counterpart_slug,
                        trust_score=relationship.trust_score,
                        desire_score=relationship.desire_score,
                        suspicion_score=relationship.suspicion_score,
                        obligation_score=relationship.obligation_score,
                        summary=relationship.summary,
                    )
                )
            return result

    def list_recent_messages(self, *, limit: int = 20, speaker_slugs: list[str] | None = None) -> list[MessageView]:
        with self.session_factory.session_scope() as session:
            stmt = select(models.Message).order_by(desc(models.Message.created_at)).limit(limit)
            if speaker_slugs:
                stmt = stmt.where(models.Message.speaker_slug.in_(speaker_slugs))
            rows = list(reversed(session.scalars(stmt).all()))
            return [
                MessageView(
                    speaker_label=row.speaker_label,
                    content=row.content,
                    kind=row.message_kind,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def list_recent_events(
        self,
        *,
        hours: int = 24,
        limit: int = 20,
        minimum_significance: int = 1,
    ) -> list[EventView]:
        threshold = utcnow() - timedelta(hours=hours)
        with self.session_factory.session_scope() as session:
            stmt = (
                select(models.ExtractedEvent)
                .where(
                    models.ExtractedEvent.created_at >= threshold,
                    models.ExtractedEvent.significance >= minimum_significance,
                )
                .order_by(desc(models.ExtractedEvent.created_at))
                .limit(limit)
            )
            rows = list(reversed(session.scalars(stmt).all()))
            return [
                EventView(
                    event_type=row.event_type,
                    title=row.title,
                    details=row.details,
                    significance=row.significance,
                    payload=row.payload,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def list_recent_summaries(self, *, limit: int = 6) -> list[SummaryView]:
        with self.session_factory.session_scope() as session:
            rows = list(
                reversed(
                    session.scalars(select(models.Summary).order_by(desc(models.Summary.created_at)).limit(limit)).all()
                )
            )
            return [
                SummaryView(
                    summary_window=row.summary_window,
                    content=row.content,
                    structured_highlights=row.structured_highlights,
                    bucket_end_at=row.bucket_end_at,
                )
                for row in rows
            ]

    def list_open_arcs(self, *, limit: int = 6) -> list[StoryArcSnapshot]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.StoryArc)
                .where(models.StoryArc.status != "resolved")
                .order_by(desc(models.StoryArc.pressure_score), models.StoryArc.stage_index)
                .limit(limit)
            ).all()
            return [
                StoryArcSnapshot(
                    slug=row.slug,
                    title=row.title,
                    summary=row.summary,
                    stage_index=row.stage_index,
                    unresolved_questions=row.unresolved_questions,
                    reveal_ladder=row.reveal_ladder,
                    pressure_score=row.pressure_score,
                )
                for row in rows
            ]

    def list_open_continuity_flags(self, *, limit: int = 10) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.ContinuityFlag)
                .where(models.ContinuityFlag.status == "open")
                .order_by(desc(models.ContinuityFlag.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "severity": row.severity,
                    "flag_type": row.flag_type,
                    "description": row.description,
                    "related_entity": row.related_entity,
                }
                for row in rows
            ]

    def get_world_state_snapshot(self) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            row = session.scalar(select(models.WorldState).order_by(desc(models.WorldState.id)))
            if row is None:
                raise RuntimeError("world_state missing")
            return {
                "title": row.title,
                "active_scene_key": row.active_scene_key,
                "current_story_day": row.current_story_day,
                "emotional_temperature": row.emotional_temperature,
                "reveal_pressure": row.reveal_pressure,
                "unresolved_questions": row.unresolved_questions,
                "archived_threads": row.archived_threads,
                "metadata": row.metadata_json,
            }

    def get_scene_snapshot(self) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            stmt = (
                select(models.SceneState, models.Location.name)
                .join(models.Location, models.Location.id == models.SceneState.location_id, isouter=True)
                .where(models.SceneState.status == "active")
                .order_by(desc(models.SceneState.started_at))
            )
            row = session.execute(stmt).first()
            if row is None:
                raise RuntimeError("scene_state missing")
            scene, location_name = row
            return {
                "id": scene.id,
                "scene_key": scene.scene_key,
                "objective": scene.objective,
                "location_name": location_name or "Unknown",
                "location_id": scene.location_id,
                "emotional_temperature": scene.emotional_temperature,
                "mystery_pressure": scene.mystery_pressure,
                "romance_pressure": scene.romance_pressure,
                "comedic_pressure": scene.comedic_pressure,
                "active_character_slugs": scene.active_character_slugs,
            }

    def get_latest_manager_directive(self) -> dict[str, Any] | None:
        with self.session_factory.session_scope() as session:
            row = session.scalar(select(models.ManagerDirective).order_by(desc(models.ManagerDirective.created_at)))
            if row is None:
                return None
            return self._directive_dict(row)

    def get_relevant_facts(self, *, location_id: int | None, limit: int = 6) -> list[str]:
        with self.session_factory.session_scope() as session:
            facts: list[str] = []
            if location_id is not None:
                location = session.get(models.Location, location_id)
                if location:
                    facts.append(location.description)
                    facts.extend(location.public_facts[:3])
            canon = session.scalars(
                select(models.CanonFact)
                .where(models.CanonFact.visibility.in_(["public", "shared"]))
                .order_by(desc(models.CanonFact.confidence), models.CanonFact.id)
                .limit(limit)
            ).all()
            facts.extend(row.content for row in canon)
            return facts[:limit]

    def get_forbidden_boundaries(self, *, character_slug: str, limit: int = 6) -> list[str]:
        with self.session_factory.session_scope() as session:
            character = session.scalar(select(models.Character).where(models.Character.slug == character_slug))
            if character is None:
                return []
            rows = session.scalars(
                select(models.Secret)
                .where(
                    models.Secret.is_public.is_(False),
                    or_(
                        models.Secret.holder_character_id.is_(None),
                        models.Secret.holder_character_id != character.id,
                    ),
                )
                .order_by(models.Secret.exposure_stage, models.Secret.id)
                .limit(limit)
            ).all()
            return [row.reveal_guardrail for row in rows]

    def record_manager_directive(self, plan: ManagerDirectivePlan, *, tick_no: int, now=None) -> dict[str, Any]:
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            scene = session.scalar(
                select(models.SceneState).where(models.SceneState.status == "active").order_by(desc(models.SceneState.id))
            )
            row = models.ManagerDirective(
                scene_id=scene.id if scene else None,
                tick_no=tick_no,
                objective=plan.objective,
                desired_developments=plan.desired_developments,
                reveal_budget=plan.reveal_budget,
                emotional_temperature=plan.emotional_temperature,
                active_character_slugs=plan.active_character_slugs,
                speaker_weights=plan.speaker_weights,
                per_character={slug: goal.model_dump() for slug, goal in plan.per_character.items()},
                thought_pulse=plan.thought_pulse.model_dump(),
                pacing_actions=plan.pacing_actions,
                continuity_watch=plan.continuity_watch,
                unresolved_questions_to_push=plan.unresolved_questions_to_push,
                recentering_hint=plan.recentering_hint,
                created_at=now,
            )
            session.add(row)
            if scene is not None:
                scene.objective = plan.objective
                scene.emotional_temperature = plan.emotional_temperature
                scene.active_character_slugs = plan.active_character_slugs
                scene.current_hour_bucket = floor_to_hour(now)

            world = session.scalar(select(models.WorldState).order_by(desc(models.WorldState.id)))
            if world is not None:
                world.active_scene_key = scene.scene_key if scene else world.active_scene_key
                world.emotional_temperature = plan.emotional_temperature
                world.reveal_pressure = plan.reveal_budget

            run_state = self._get_run_state_model(session)
            run_state.last_manager_run_at = now
            session.flush()
            return self._directive_dict(row)

    def record_turn(
        self,
        *,
        speaker_slug: str,
        speaker_label: str,
        turn: CharacterTurn,
        events: list[EventCandidate],
        flags: list[ContinuityFlagDraft],
        directive_id: int | None,
        degraded_mode: bool,
        latency_ms: int | None,
        now=None,
    ) -> dict[str, Any]:
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            run_state = self._get_run_state_model(session)
            run_state.status = "running"
            run_state.degraded_mode = degraded_mode
            next_tick = run_state.last_tick_no + 1

            speaker = session.scalar(select(models.Character).where(models.Character.slug == speaker_slug))
            scene = session.scalar(
                select(models.SceneState).where(models.SceneState.status == "active").order_by(desc(models.SceneState.id))
            )
            if speaker is None:
                raise KeyError(f"Unknown speaker slug: {speaker_slug}")

            message = models.Message(
                tick_no=next_tick,
                scene_id=scene.id if scene else None,
                speaker_character_id=speaker.id,
                speaker_slug=speaker.slug,
                speaker_label=speaker_label,
                message_kind=MessageKind.CHAT.value,
                content=turn.public_message,
                hidden_metadata={
                    "tone": turn.tone,
                    "new_questions": turn.new_questions,
                    "answered_questions": turn.answered_questions,
                },
                created_at=now,
                latency_ms=latency_ms,
            )
            session.add(message)
            session.flush()

            speaker_state = session.scalar(
                select(models.CharacterState).where(models.CharacterState.character_id == speaker.id)
            )
            if speaker_state is not None:
                speaker_state.last_spoke_at = now
                speaker_state.silence_streak = 0
                emotional_state = dict(speaker_state.emotional_state)
                if turn.tone:
                    emotional_state["current"] = turn.tone
                emotional_state["last_public_move"] = turn.public_message[:120]
                speaker_state.emotional_state = emotional_state
                if any(event.event_type.value in {"conflict", "threat", "reveal"} for event in events):
                    speaker_state.stress_level = _clamp(speaker_state.stress_level + 1, 0, 10)
                elif turn.tone in {"warm", "playful"}:
                    speaker_state.stress_level = _clamp(speaker_state.stress_level - 1, 0, 10)
                if any(event.event_type.value == "romance" for event in events):
                    speaker_state.romance_heat = _clamp(speaker_state.romance_heat + 1, 0, 10)

            session.execute(
                update(models.CharacterState)
                .where(models.CharacterState.character_id != speaker.id)
                .values(silence_streak=models.CharacterState.silence_streak + 1)
            )

            relationship_lookup = self._relationship_index(session)
            for delta in turn.relationship_updates:
                counterpart = session.scalar(select(models.Character).where(models.Character.slug == delta.character_slug))
                if counterpart is None:
                    continue
                pair_key = tuple(sorted((speaker.id, counterpart.id)))
                relationship = relationship_lookup.get(pair_key)
                if relationship is None:
                    relationship = models.Relationship(
                        character_a_id=pair_key[0],
                        character_b_id=pair_key[1],
                        summary=delta.summary,
                    )
                    session.add(relationship)
                    relationship_lookup[pair_key] = relationship
                relationship.trust_score = _clamp(relationship.trust_score + delta.trust_delta)
                relationship.desire_score = _clamp(relationship.desire_score + delta.desire_delta)
                relationship.suspicion_score = _clamp(relationship.suspicion_score + delta.suspicion_delta)
                relationship.obligation_score = _clamp(relationship.obligation_score + delta.obligation_delta)
                relationship.summary = delta.summary
                relationship.last_shift_at = now

            for event in events:
                session.add(
                    models.ExtractedEvent(
                        source_message_id=message.id,
                        event_type=event.event_type.value,
                        title=event.title,
                        details=event.details,
                        payload={
                            "speaker_slug": speaker_slug,
                            "tags": event.tags,
                        },
                        significance=event.significance,
                        affects_arc_slug=event.arc_slug,
                        affects_relationships=[delta.character_slug for delta in turn.relationship_updates],
                        created_at=now,
                    )
                )

            pulse_content = None
            if turn.thought_pulse:
                session.add(
                    models.ThoughtPulse(
                        tick_no=next_tick,
                        character_id=speaker.id,
                        content=turn.thought_pulse,
                        source_directive_id=directive_id,
                        created_at=now,
                    )
                )
                pulse_content = turn.thought_pulse
                run_state.last_thought_pulse_at = now

            for flag in flags:
                session.add(
                    models.ContinuityFlag(
                        severity=flag.severity.value,
                        flag_type=flag.flag_type,
                        description=flag.description,
                        related_entity=flag.related_entity,
                        related_message_id=message.id,
                    )
                )

            self._update_unresolved_questions(session, turn.new_questions, turn.answered_questions)

            run_state.last_tick_no = next_tick
            run_state.last_public_message_at = now
            session.flush()

            return {
                "tick_no": next_tick,
                "created_at": now,
                "message_id": message.id,
                "thought_pulse": pulse_content,
            }

    def save_recap_bundle(self, *, bucket_end_at, bundle, generated_by: str = "announcer") -> None:
        with self.session_factory.session_scope() as session:
            for window, summary in {
                SummaryWindow.ONE_HOUR.value: bundle.one_hour,
                SummaryWindow.TWELVE_HOURS.value: bundle.twelve_hours,
                SummaryWindow.TWENTY_FOUR_HOURS.value: bundle.twenty_four_hours,
            }.items():
                existing = session.scalar(
                    select(models.Summary).where(
                        models.Summary.summary_window == window,
                        models.Summary.bucket_end_at == bucket_end_at,
                    )
                )
                if existing is not None:
                    continue
                content = " | ".join(
                    [
                        summary.headline,
                        f"Changed: {'; '.join(summary.what_changed)}",
                        f"Emotion: {'; '.join(summary.emotional_shifts)}",
                        f"Clues: {'; '.join(summary.clues)}",
                        f"Questions: {'; '.join(summary.unresolved_questions)}",
                        f"Trust: {summary.loyalty_status}",
                        f"Romance: {summary.romance_status}",
                        f"Watch: {summary.watch_next}",
                    ]
                )
                session.add(
                    models.Summary(
                        summary_window=window,
                        bucket_end_at=bucket_end_at,
                        content=content,
                        structured_highlights=summary.model_dump(),
                        generated_by=generated_by,
                    )
                )

            run_state = self._get_run_state_model(session)
            run_state.last_recap_hour = bucket_end_at
            run_state.last_public_message_at = bucket_end_at

    def load_events_for_window(self, *, bucket_end_at, hours: int) -> list[EventView]:
        start = bucket_end_at - timedelta(hours=hours)
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.ExtractedEvent)
                .where(
                    models.ExtractedEvent.created_at >= start,
                    models.ExtractedEvent.created_at < bucket_end_at,
                )
                .order_by(models.ExtractedEvent.created_at)
            ).all()
            return [
                EventView(
                    event_type=row.event_type,
                    title=row.title,
                    details=row.details,
                    significance=row.significance,
                    payload=row.payload,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def get_relationship_map(self) -> list[str]:
        with self.session_factory.session_scope() as session:
            characters = {
                row.id: row.slug
                for row in session.scalars(select(models.Character).order_by(models.Character.id)).all()
            }
            rows = session.scalars(select(models.Relationship).order_by(desc(models.Relationship.last_shift_at))).all()
            result = []
            for row in rows:
                a = characters.get(row.character_a_id, "?")
                b = characters.get(row.character_b_id, "?")
                result.append(
                    f"{a}<->{b}: trust {row.trust_score}, desire {row.desire_score}, suspicion {row.suspicion_score}, obligation {row.obligation_score}. {row.summary}"
                )
            return result

    def add_continuity_flags(self, flags: list[ContinuityFlagDraft]) -> None:
        if not flags:
            return
        with self.session_factory.session_scope() as session:
            for flag in flags:
                session.add(
                    models.ContinuityFlag(
                        severity=flag.severity.value,
                        flag_type=flag.flag_type,
                        description=flag.description,
                    related_entity=flag.related_entity,
                    )
                )

    def count_recent_thought_pulses(self, *, hours: int = 1) -> int:
        threshold = utcnow() - timedelta(hours=hours)
        with self.session_factory.session_scope() as session:
            return session.scalar(
                select(func.count(models.ThoughtPulse.id)).where(models.ThoughtPulse.created_at >= threshold)
            ) or 0

    def _get_run_state_model(self, session) -> models.RunState:
        run_state = session.scalar(select(models.RunState).where(models.RunState.runtime_key == "primary"))
        if run_state is None:
            run_state = models.RunState(runtime_key="primary")
            session.add(run_state)
            session.flush()
        return run_state

    def _update_unresolved_questions(
        self,
        session,
        new_questions: list[str],
        answered_questions: list[str],
    ) -> None:
        if not new_questions and not answered_questions:
            return
        world = session.scalar(select(models.WorldState).order_by(desc(models.WorldState.id)))
        if world is None:
            return
        existing = list(world.unresolved_questions)
        for question in new_questions:
            if question not in existing:
                existing.append(question)
        for question in answered_questions:
            if question in existing:
                existing.remove(question)
        world.unresolved_questions = existing

    def _directive_dict(self, row: models.ManagerDirective) -> dict[str, Any]:
        return {
            "id": row.id,
            "tick_no": row.tick_no,
            "objective": row.objective,
            "desired_developments": row.desired_developments,
            "reveal_budget": row.reveal_budget,
            "emotional_temperature": row.emotional_temperature,
            "active_character_slugs": row.active_character_slugs,
            "speaker_weights": row.speaker_weights,
            "per_character": row.per_character,
            "thought_pulse": row.thought_pulse,
            "pacing_actions": row.pacing_actions,
            "continuity_watch": row.continuity_watch,
            "unresolved_questions_to_push": row.unresolved_questions_to_push,
            "recentering_hint": row.recentering_hint,
            "created_at": row.created_at,
        }

    def _run_state_dict(self, row: models.RunState) -> dict[str, Any]:
        return {
            "status": row.status,
            "last_tick_no": row.last_tick_no,
            "last_public_message_at": row.last_public_message_at,
            "last_manager_run_at": row.last_manager_run_at,
            "last_recap_hour": row.last_recap_hour,
            "last_thought_pulse_at": row.last_thought_pulse_at,
            "degraded_mode": row.degraded_mode,
            "metadata": row.metadata_json,
        }

    def _relationship_index(self, session) -> dict[tuple[int, int], models.Relationship]:
        lookup: dict[tuple[int, int], models.Relationship] = {}
        for relationship in session.scalars(select(models.Relationship)).all():
            key = tuple(sorted((relationship.character_a_id, relationship.character_b_id)))
            lookup[key] = relationship
        return lookup


def _clamp(value: int, minimum: int = -10, maximum: int = 10) -> int:
    return max(minimum, min(maximum, value))
