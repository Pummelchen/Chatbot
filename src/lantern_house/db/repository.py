# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from lantern_house.db import models
from lantern_house.db.session import SessionFactory
from lantern_house.domain.contracts import (
    BeatPlanItem,
    BeatSnapshot,
    BroadcastAssetSnapshot,
    CanonCapsuleSnapshot,
    CanonCourtFindingSnapshot,
    CharacterTurn,
    ChronologyEdgeSnapshot,
    ChronologyNodeSnapshot,
    ContinuityFlagDraft,
    DormantThreadSnapshot,
    EventCandidate,
    EventView,
    GuestProfileSnapshot,
    HighlightPackageSnapshot,
    HotPatchCanaryRunSnapshot,
    HourlyProgressLedgerSnapshot,
    HouseStateSnapshot,
    ManagerDirectivePlan,
    MessageView,
    MonetizationPackageSnapshot,
    ObjectPossessionSnapshot,
    OpsTelemetrySnapshot,
    ProgrammingGridSlotSnapshot,
    RelationshipSnapshot,
    SimulationLabReport,
    SoakAuditSnapshot,
    StoryArcSnapshot,
    StoryGravityStateSnapshot,
    StoryProgressionPlan,
    StrategicBriefPlan,
    StrategicBriefSnapshot,
    SummaryView,
    TimelineFactSnapshot,
    TurnCriticReport,
    ViewerSignalSnapshot,
    VoiceFingerprintSnapshot,
)
from lantern_house.domain.enums import MessageKind, SummaryWindow
from lantern_house.utils.time import ensure_utc, floor_to_hour, isoformat, utcnow

_MAX_UNRESOLVED_QUESTIONS = 12
_MAX_ARCHIVED_THREADS = 24
logger = logging.getLogger(__name__)


class StoryRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def seed_exists(self) -> bool:
        with self.session_factory.session_scope() as session:
            return session.scalar(select(func.count(models.Character.id))) > 0

    def ensure_run_state(self) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            run_state = session.scalar(
                select(models.RunState).where(models.RunState.runtime_key == "primary")
            )
            if run_state is None:
                run_state = models.RunState(runtime_key="primary", status="idle")
                session.add(run_state)
                session.flush()
            return self._run_state_dict(run_state)

    def get_run_state(self) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            run_state = session.scalar(
                select(models.RunState).where(models.RunState.runtime_key == "primary")
            )
            if run_state is None:
                raise RuntimeError("run_state is missing; seed or bootstrap first")
            return self._run_state_dict(run_state)

    def mark_runtime_starting(self, *, now=None) -> dict[str, Any]:
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            run_state = self._get_run_state_model(session)
            previous = self._run_state_dict(run_state)
            metadata = dict(run_state.metadata_json)
            metadata["runtime_phase"] = "startup"
            metadata["last_start_at"] = isoformat(now)
            metadata["restart_count"] = int(metadata.get("restart_count", 0)) + 1
            run_state.status = "starting"
            run_state.last_checkpoint_at = now
            run_state.metadata_json = metadata
            return previous

    def set_runtime_status(
        self,
        status: str,
        *,
        degraded_mode: bool | None = None,
        phase: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
        now=None,
    ) -> None:
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            run_state = self._get_run_state_model(session)
            run_state.status = status
            if degraded_mode is not None:
                run_state.degraded_mode = degraded_mode
            metadata = dict(run_state.metadata_json)
            metadata["last_status_change_at"] = isoformat(now)
            if phase is not None:
                metadata["runtime_phase"] = phase
            if extra_metadata:
                metadata.update(extra_metadata)
            run_state.metadata_json = metadata

    def merge_runtime_metadata(self, payload: dict[str, Any], *, now=None) -> dict[str, Any]:
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            run_state = self._get_run_state_model(session)
            metadata = dict(run_state.metadata_json)
            metadata = _deep_merge_dicts(metadata, payload)
            run_state.metadata_json = metadata
            run_state.updated_at = now
            return metadata

    def list_missing_recap_hours(self, now=None) -> list:
        now = now or utcnow()
        bucket = floor_to_hour(now)
        run_state = self.get_run_state()
        last_recap = run_state["last_recap_hour"]
        if last_recap is None:
            last_public = run_state["last_public_message_at"]
            if last_public is None:
                return []
            current = floor_to_hour(last_public) + timedelta(hours=1)
            if current > bucket:
                return []
            hours = []
            while current <= bucket:
                hours.append(current)
                current += timedelta(hours=1)
            return hours

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
            characters = session.scalars(
                select(models.Character).order_by(models.Character.id)
            ).all()
            return [
                {
                    "slug": row.slug,
                    "full_name": row.full_name,
                    "cultural_background": row.cultural_background,
                    "public_persona": row.public_persona,
                    "hidden_wound": row.hidden_wound,
                    "long_term_desire": row.long_term_desire,
                    "private_fear": row.private_fear,
                    "family_expectations": row.family_expectations,
                    "conflict_style": row.conflict_style,
                    "privacy_boundaries": row.privacy_boundaries,
                    "value_instincts": row.value_instincts,
                    "emotional_expression": row.emotional_expression,
                    "message_style": row.message_style,
                    "ensemble_role": row.ensemble_role,
                    "humor_style": row.humor_style,
                    "color": row.color,
                }
                for row in characters
            ]

    def list_character_states(self) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            stmt = (
                select(
                    models.Character.slug,
                    models.CharacterState.last_spoke_at,
                    models.CharacterState.silence_streak,
                )
                .join(
                    models.CharacterState, models.Character.id == models.CharacterState.character_id
                )
                .order_by(models.Character.id)
            )
            return [
                {"slug": slug, "last_spoke_at": last_spoke_at, "silence_streak": silence_streak}
                for slug, last_spoke_at, silence_streak in session.execute(stmt).all()
            ]

    def list_locations(self) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(select(models.Location).order_by(models.Location.id)).all()
            return [
                {
                    "slug": row.slug,
                    "name": row.name,
                    "description": row.description,
                    "public_facts": row.public_facts,
                }
                for row in rows
            ]

    def list_story_objects(self) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            possession_lookup = {
                row.object_slug: row
                for row in session.scalars(select(models.ObjectPossession)).all()
            }
            stmt = (
                select(models.StoryObject, models.Location)
                .join(
                    models.Location,
                    models.Location.id == models.StoryObject.location_id,
                    isouter=True,
                )
                .order_by(models.StoryObject.id)
            )
            rows = session.execute(stmt).all()
            objects: list[dict[str, Any]] = []
            for story_object, location in rows:
                possession = possession_lookup.get(story_object.slug)
                objects.append(
                    {
                        "slug": story_object.slug,
                        "name": story_object.name,
                        "description": story_object.description,
                        "location_slug": (
                            possession.location_slug
                            if possession and possession.location_slug
                            else location.slug
                            if location
                            else None
                        ),
                        "location_name": (
                            possession.location_name
                            if possession and possession.location_name
                            else location.name
                            if location
                            else ""
                        ),
                        "holder_character_slug": (
                            possession.holder_character_slug if possession else None
                        ),
                        "possession_status": (
                            possession.possession_status if possession else "room"
                        ),
                        "summary": possession.summary if possession else "",
                        "significance": story_object.significance,
                        "seeded": possession is None,
                    }
                )
            return objects

    def list_character_positions(self) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            stmt = (
                select(models.Character, models.CharacterState, models.Location)
                .join(
                    models.CharacterState,
                    models.Character.id == models.CharacterState.character_id,
                )
                .join(
                    models.Location,
                    models.Location.id == models.CharacterState.current_location_id,
                    isouter=True,
                )
                .order_by(models.Character.id)
            )
            rows = session.execute(stmt).all()
            return [
                {
                    "slug": character.slug,
                    "full_name": character.full_name,
                    "location_slug": location.slug if location else None,
                    "location_name": location.name if location else "Unknown",
                    "last_spoke_at": state.last_spoke_at,
                    "stress_level": state.stress_level,
                }
                for character, state, location in rows
            ]

    def get_character_overview(self, slug: str) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            stmt = (
                select(models.Character, models.CharacterState, models.Location)
                .join(
                    models.CharacterState, models.Character.id == models.CharacterState.character_id
                )
                .join(
                    models.Location,
                    models.Location.id == models.CharacterState.current_location_id,
                    isouter=True,
                )
                .where(models.Character.slug == slug)
            )
            row = session.execute(stmt).one_or_none()
            if row is None:
                raise KeyError(f"Unknown character slug: {slug}")
            character, state, location = row
            return {
                "slug": character.slug,
                "full_name": character.full_name,
                "cultural_background": character.cultural_background,
                "public_persona": character.public_persona,
                "hidden_wound": character.hidden_wound,
                "long_term_desire": character.long_term_desire,
                "private_fear": character.private_fear,
                "family_expectations": character.family_expectations,
                "conflict_style": character.conflict_style,
                "privacy_boundaries": character.privacy_boundaries,
                "value_instincts": character.value_instincts,
                "emotional_expression": character.emotional_expression,
                "message_style": character.message_style,
                "ensemble_role": character.ensemble_role,
                "humor_style": character.humor_style,
                "location_name": location.name if location else "Unknown",
                "emotional_state": state.emotional_state,
                "current_goals": state.active_goals,
                "stress_level": state.stress_level,
                "romance_heat": state.romance_heat,
            }

    def list_relationship_snapshots(self, slug: str) -> list[RelationshipSnapshot]:
        with self.session_factory.session_scope() as session:
            character = session.scalar(
                select(models.Character).where(models.Character.slug == slug)
            )
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

    def list_recent_messages(
        self, *, limit: int = 20, speaker_slugs: list[str] | None = None
    ) -> list[MessageView]:
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

    def list_recent_message_metrics(self, *, limit: int = 12) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.Message)
                .where(models.Message.latency_ms.is_not(None))
                .order_by(desc(models.Message.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "tick_no": row.tick_no,
                    "speaker_slug": row.speaker_slug,
                    "latency_ms": row.latency_ms or 0,
                    "created_at": row.created_at,
                }
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
                    session.scalars(
                        select(models.Summary)
                        .order_by(desc(models.Summary.created_at))
                        .limit(limit)
                    ).all()
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
                    status=row.status,
                    arc_type=row.arc_type,
                    summary=row.summary,
                    stage_index=row.stage_index,
                    unresolved_questions=row.unresolved_questions,
                    reveal_ladder=row.reveal_ladder,
                    payoff_window=row.payoff_window,
                    pressure_score=row.pressure_score,
                    metadata=row.metadata_json,
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

    def get_house_state_snapshot(self) -> HouseStateSnapshot:
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.HouseState).where(models.HouseState.state_key == "primary")
            )
            if row is None:
                return HouseStateSnapshot()
            return HouseStateSnapshot(
                state_key=row.state_key,
                capacity=row.capacity,
                occupied_rooms=row.occupied_rooms,
                vacancy_pressure=row.vacancy_pressure,
                cash_on_hand=row.cash_on_hand,
                hourly_burn_rate=row.hourly_burn_rate,
                payroll_due_in_hours=row.payroll_due_in_hours,
                repair_backlog=row.repair_backlog,
                inspection_risk=row.inspection_risk,
                guest_tension=row.guest_tension,
                weather_pressure=row.weather_pressure,
                staff_fatigue=row.staff_fatigue,
                reputation_risk=row.reputation_risk,
                active_pressures=row.active_pressures,
                metadata=row.metadata_json,
                updated_at=row.updated_at,
            )

    def get_story_gravity_state_snapshot(self) -> StoryGravityStateSnapshot:
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.StoryGravityState).where(
                    models.StoryGravityState.state_key == "primary"
                )
            )
            if row is None:
                return StoryGravityStateSnapshot()
            return StoryGravityStateSnapshot(
                state_key=row.state_key,
                north_star_objective=row.north_star_objective,
                central_tension=row.central_tension,
                core_tensions=row.core_tensions,
                active_axes=row.active_axes,
                dormant_threads=[
                    DormantThreadSnapshot.model_validate(item)
                    for item in row.dormant_threads
                    if isinstance(item, dict)
                ],
                drift_score=row.drift_score,
                reentry_priority=row.reentry_priority,
                clip_priority=row.clip_priority,
                fandom_priority=row.fandom_priority,
                recap_focus=row.recap_focus,
                manager_guardrails=row.manager_guardrails,
                metadata=row.metadata_json,
                updated_at=row.updated_at,
            )

    def save_house_state(self, snapshot: HouseStateSnapshot, *, now=None) -> HouseStateSnapshot:
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.HouseState).where(models.HouseState.state_key == snapshot.state_key)
            )
            if row is None:
                row = models.HouseState(state_key=snapshot.state_key)
                session.add(row)
            row.capacity = snapshot.capacity
            row.occupied_rooms = snapshot.occupied_rooms
            row.vacancy_pressure = snapshot.vacancy_pressure
            row.cash_on_hand = snapshot.cash_on_hand
            row.hourly_burn_rate = snapshot.hourly_burn_rate
            row.payroll_due_in_hours = snapshot.payroll_due_in_hours
            row.repair_backlog = snapshot.repair_backlog
            row.inspection_risk = snapshot.inspection_risk
            row.guest_tension = snapshot.guest_tension
            row.weather_pressure = snapshot.weather_pressure
            row.staff_fatigue = snapshot.staff_fatigue
            row.reputation_risk = snapshot.reputation_risk
            row.active_pressures = [item.model_dump() for item in snapshot.active_pressures]
            row.metadata_json = dict(snapshot.metadata)
            row.updated_at = now
            for item in snapshot.active_pressures:
                session.add(
                    models.HousePressure(
                        state_key=snapshot.state_key,
                        signal_slug=item.slug,
                        label=item.label,
                        intensity=item.intensity,
                        summary=item.summary,
                        recommended_move=item.recommended_move,
                        source_metric=item.source_metric,
                        metadata_json={
                            "updated_at": isoformat(now),
                            "state_key": snapshot.state_key,
                        },
                        created_at=now,
                    )
                )
            session.flush()
            return snapshot.model_copy(update={"updated_at": now})

    def save_story_gravity_state(
        self,
        snapshot: StoryGravityStateSnapshot,
        *,
        now=None,
    ) -> StoryGravityStateSnapshot:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.StoryGravityState).where(
                    models.StoryGravityState.state_key == snapshot.state_key
                )
            )
            if row is None:
                row = models.StoryGravityState(state_key=snapshot.state_key)
                session.add(row)
            row.north_star_objective = snapshot.north_star_objective
            row.central_tension = snapshot.central_tension
            row.core_tensions = snapshot.core_tensions
            row.active_axes = snapshot.active_axes
            row.dormant_threads = [
                item.model_dump(mode="json") for item in snapshot.dormant_threads
            ]
            row.drift_score = snapshot.drift_score
            row.reentry_priority = snapshot.reentry_priority
            row.clip_priority = snapshot.clip_priority
            row.fandom_priority = snapshot.fandom_priority
            row.recap_focus = snapshot.recap_focus
            row.manager_guardrails = snapshot.manager_guardrails
            row.metadata_json = dict(snapshot.metadata)
            row.updated_at = now
            session.flush()
            return snapshot.model_copy(update={"updated_at": now})

    def get_scene_snapshot(self) -> dict[str, Any]:
        with self.session_factory.session_scope() as session:
            stmt = (
                select(models.SceneState, models.Location.name)
                .join(
                    models.Location,
                    models.Location.id == models.SceneState.location_id,
                    isouter=True,
                )
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
            row = session.scalar(
                select(models.ManagerDirective).order_by(desc(models.ManagerDirective.created_at))
            )
            if row is None:
                return None
            return self._directive_dict(row)

    def list_pending_beats(
        self,
        *,
        limit: int = 6,
        now=None,
        include_future_hours: int = 24,
    ) -> list[BeatSnapshot]:
        now = ensure_utc(now or utcnow())
        threshold = now + timedelta(hours=max(1, include_future_hours))
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.Beat)
                .where(models.Beat.status.in_(["planned", "ready", "active"]))
                .order_by(models.Beat.due_by, desc(models.Beat.significance), models.Beat.id)
            ).all()
            snapshots: list[BeatSnapshot] = []
            for row in rows:
                due_by = ensure_utc(row.due_by) if row.due_by else None
                if due_by is not None and due_by > threshold:
                    continue
                status = _effective_beat_status(row.status, due_by=due_by, now=now)
                snapshots.append(
                    BeatSnapshot(
                        id=row.id,
                        beat_key=_stringy(row.metadata_json.get("beat_key")),
                        beat_type=row.beat_type,
                        objective=row.objective,
                        status=status,
                        significance=row.significance,
                        due_by=due_by,
                        metadata=row.metadata_json,
                    )
                )
            snapshots.sort(key=lambda beat: _beat_sort_key(beat, now=now))
            return snapshots[:limit]

    def sync_beats(
        self,
        *,
        beat_type: str,
        items: list[BeatPlanItem],
        source_key: str,
        now=None,
    ) -> list[BeatSnapshot]:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            scene = session.scalar(
                select(models.SceneState)
                .where(models.SceneState.status == "active")
                .order_by(desc(models.SceneState.id))
            )
            if scene is None:
                raise RuntimeError("Cannot sync beats without an active scene.")
            rows = session.scalars(
                select(models.Beat).where(
                    models.Beat.beat_type == beat_type,
                    models.Beat.status.in_(["planned", "ready", "active"]),
                )
            ).all()
            existing = {
                row.metadata_json.get("beat_key"): row
                for row in rows
                if row.metadata_json.get("source_key") == source_key
            }
            active_keys = {item.beat_key for item in items}
            snapshots: list[BeatSnapshot] = []
            for item in items:
                row = existing.get(item.beat_key)
                due_by = _parse_optional_timestamp(item.ready_at, default=now)
                status = "ready" if due_by <= now else "planned"
                metadata = dict(item.metadata)
                metadata.update(
                    {
                        "beat_key": item.beat_key,
                        "source_key": source_key,
                        "keywords": item.keywords,
                    }
                )
                if row is None:
                    row = models.Beat(
                        scene_id=scene.id,
                        beat_type=beat_type,
                        objective=item.objective,
                        significance=item.significance,
                        due_by=due_by,
                        status=status,
                        metadata_json=metadata,
                    )
                    session.add(row)
                    session.flush()
                else:
                    row.objective = item.objective
                    row.significance = item.significance
                    row.due_by = due_by
                    row.status = status
                    row.metadata_json = metadata
                snapshots.append(
                    BeatSnapshot(
                        id=row.id,
                        beat_key=item.beat_key,
                        beat_type=beat_type,
                        objective=item.objective,
                        status=status,
                        significance=item.significance,
                        due_by=due_by,
                        metadata=metadata,
                    )
                )

            for beat_key, row in existing.items():
                if beat_key in active_keys:
                    continue
                row.status = "archived"
                metadata = dict(row.metadata_json)
                metadata["archived_at"] = isoformat(now)
                row.metadata_json = metadata

            return snapshots

    def complete_matching_beats(
        self, *, texts: list[str], now=None, limit: int = 4
    ) -> list[BeatSnapshot]:
        now = ensure_utc(now or utcnow())
        normalized_text = " ".join(_normalize_memory_item(text) for text in texts if text).strip()
        if not normalized_text:
            return []
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.Beat).where(models.Beat.status.in_(["planned", "ready", "active"]))
            ).all()
            completed: list[BeatSnapshot] = []
            for row in rows:
                due_by = ensure_utc(row.due_by) if row.due_by else None
                effective_status = _effective_beat_status(row.status, due_by=due_by, now=now)
                if effective_status == "planned":
                    continue
                metadata = dict(row.metadata_json)
                keywords = [
                    _normalize_memory_item(keyword)
                    for keyword in metadata.get("keywords", [])
                    if _normalize_memory_item(keyword)
                ]
                if not keywords:
                    continue
                required_hits = 1 if len(keywords) == 1 else min(2, len(keywords))
                hits = sum(keyword in normalized_text for keyword in keywords)
                if hits < required_hits:
                    continue
                row.status = "completed"
                metadata["completed_at"] = isoformat(now)
                metadata["completion_excerpt"] = normalized_text[:180]
                row.metadata_json = metadata
                completed.append(
                    BeatSnapshot(
                        id=row.id,
                        beat_key=_stringy(metadata.get("beat_key")),
                        beat_type=row.beat_type,
                        objective=row.objective,
                        status=row.status,
                        significance=row.significance,
                        due_by=due_by,
                        metadata=metadata,
                    )
                )
                if len(completed) >= limit:
                    break
            return completed

    def sync_rollout_requests(
        self,
        *,
        change_id: str | None,
        fingerprint: str | None,
        priority: int,
        requests: list[str],
        directives: list[str],
        active: bool,
        activated_at,
        now=None,
    ) -> None:
        now = ensure_utc(now or utcnow())
        change_id = change_id or "manual-unknown"
        fingerprint = fingerprint or "none"
        activated_dt = _parse_optional_timestamp(activated_at, default=now)
        with self.session_factory.session_scope() as session:
            active_rows = session.scalars(
                select(models.RolloutRequest).where(models.RolloutRequest.status == "active")
            ).all()
            active_lookup = {(row.fingerprint or "none", row.summary): row for row in active_rows}
            active_summaries = set(requests if active else [])
            for row in active_rows:
                if (row.fingerprint or "none") == fingerprint and row.summary in active_summaries:
                    continue
                row.status = "archived"

            if not active:
                return

            for request in requests:
                request_type = _classify_rollout_request(request)
                row = active_lookup.get((fingerprint, request))
                metadata = {
                    "change_id": change_id,
                    "request_type": request_type,
                    "fingerprint": fingerprint,
                }
                if row is None:
                    row = models.RolloutRequest(
                        change_id=change_id,
                        fingerprint=fingerprint,
                        request_type=request_type,
                        priority=priority,
                        status="active",
                        summary=request,
                        directives=directives[:8],
                        metadata_json=metadata,
                        activated_at=activated_dt,
                        created_at=now,
                    )
                    session.add(row)
                    continue
                row.change_id = change_id
                row.request_type = request_type
                row.priority = priority
                row.status = "active"
                row.directives = directives[:8]
                row.metadata_json = metadata
                row.activated_at = activated_dt

    def sync_rollout_beats(
        self,
        *,
        change_id: str | None,
        beat_items: list[BeatPlanItem],
        now=None,
    ) -> None:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            active_rows = session.scalars(
                select(models.RolloutBeat).where(
                    models.RolloutBeat.status.in_(["planned", "ready", "active"])
                )
            ).all()
            existing = {row.beat_key: row for row in active_rows}
            active_keys = {item.beat_key for item in beat_items}
            request_lookup = {
                row.summary: row.id
                for row in session.scalars(
                    select(models.RolloutRequest).where(
                        models.RolloutRequest.status == "active",
                        models.RolloutRequest.change_id == (change_id or "manual-unknown"),
                    )
                ).all()
            }
            for item in beat_items:
                metadata = dict(item.metadata)
                request_hint = _stringy(metadata.get("request_summary"))
                ready_at = _parse_optional_timestamp(item.ready_at, default=now)
                status = "ready" if ready_at <= now else "planned"
                row = existing.get(item.beat_key)
                if row is None:
                    row = models.RolloutBeat(
                        rollout_request_id=request_lookup.get(request_hint),
                        beat_key=item.beat_key,
                        beat_type=item.beat_type,
                        objective=item.objective,
                        status=status,
                        ready_at=ready_at,
                        significance=item.significance,
                        metadata_json=metadata,
                        created_at=now,
                    )
                    session.add(row)
                    continue
                row.rollout_request_id = request_lookup.get(request_hint)
                row.beat_type = item.beat_type
                row.objective = item.objective
                row.status = status
                row.ready_at = ready_at
                row.significance = item.significance
                row.metadata_json = metadata

            for beat_key, row in existing.items():
                if beat_key in active_keys:
                    continue
                row.status = "archived"
                metadata = dict(row.metadata_json)
                metadata["archived_at"] = isoformat(now)
                row.metadata_json = metadata

    def record_simulation_lab_run(
        self,
        *,
        report: SimulationLabReport,
        source: str,
        now=None,
    ) -> SimulationLabReport:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            winner = report.candidates[0].strategy_key if report.candidates else None
            row = models.SimulationLabRun(
                source=source,
                horizon_hours=report.horizon_hours,
                turns_per_hour=report.turns_per_hour,
                winner_key=winner,
                systemic_risks=report.systemic_risks,
                recommended_focus=report.recommended_focus,
                metadata_json={"generated_at": isoformat(report.generated_at or now)},
                created_at=now,
            )
            session.add(row)
            session.flush()
            for index, candidate in enumerate(report.candidates, start=1):
                session.add(
                    models.StrategyRanking(
                        simulation_run_id=row.id,
                        strategy_key=candidate.strategy_key,
                        rank_order=index,
                        score=candidate.score,
                        rationale=candidate.rationale,
                        next_hour_focus=candidate.next_hour_focus,
                        six_hour_path=candidate.six_hour_path,
                        value_profile=candidate.value_profile,
                        created_at=now,
                    )
                )
            return report.model_copy(
                update={
                    "run_id": row.id,
                    "generated_at": report.generated_at or now,
                    "ranked_strategy_keys": [
                        candidate.strategy_key for candidate in report.candidates
                    ],
                }
            )

    def record_soak_audit_run(
        self,
        *,
        snapshot: SoakAuditSnapshot,
        now=None,
    ) -> SoakAuditSnapshot:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            row = models.SoakAuditRun(
                horizons_hours=snapshot.horizons_hours,
                progression_miss_risk=snapshot.progression_miss_risk,
                drift_risk=snapshot.drift_risk,
                strategy_lock_risk=snapshot.strategy_lock_risk,
                recap_decay_risk=snapshot.recap_decay_risk,
                clip_drought_risk=snapshot.clip_drought_risk,
                ship_stagnation_risk=snapshot.ship_stagnation_risk,
                unresolved_overload_risk=snapshot.unresolved_overload_risk,
                recommended_direction=snapshot.recommended_direction,
                audit_notes=snapshot.audit_notes,
                candidate_pressure=snapshot.candidate_pressure,
                metadata_json=snapshot.metadata,
                created_at=now,
            )
            session.add(row)
            session.flush()
            return snapshot.model_copy(update={"run_id": row.id, "created_at": now})

    def get_latest_soak_audit(self) -> SoakAuditSnapshot | None:
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.SoakAuditRun).order_by(desc(models.SoakAuditRun.created_at))
            )
            if row is None:
                return None
            return SoakAuditSnapshot(
                run_id=row.id,
                horizons_hours=row.horizons_hours,
                progression_miss_risk=row.progression_miss_risk,
                drift_risk=row.drift_risk,
                strategy_lock_risk=row.strategy_lock_risk,
                recap_decay_risk=row.recap_decay_risk,
                clip_drought_risk=row.clip_drought_risk,
                ship_stagnation_risk=row.ship_stagnation_risk,
                unresolved_overload_risk=row.unresolved_overload_risk,
                recommended_direction=row.recommended_direction,
                audit_notes=row.audit_notes,
                candidate_pressure=row.candidate_pressure,
                metadata=row.metadata_json,
                created_at=row.created_at,
            )

    def get_latest_strategic_brief(
        self, *, now=None, active_only: bool = True
    ) -> StrategicBriefSnapshot | None:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.StrategicBrief).order_by(desc(models.StrategicBrief.created_at))
            )
            if row is None:
                return None
            if active_only and row.expires_at and ensure_utc(row.expires_at) < now:
                return None
            return StrategicBriefSnapshot(
                source=row.source,
                model_name=row.model_name,
                title=row.title,
                current_north_star_objective=row.current_north_star_objective or "",
                viewer_value_thesis=row.viewer_value_thesis,
                urgency=row.urgency,
                arc_priority_ranking=row.arc_priority_ranking or [],
                danger_of_drift_score=row.danger_of_drift_score or 25,
                cliffhanger_urgency=row.cliffhanger_urgency or 5,
                romance_urgency=row.romance_urgency or 5,
                mystery_urgency=row.mystery_urgency or 5,
                house_pressure_priority=row.house_pressure_priority or 5,
                audience_rollout_priority=row.audience_rollout_priority or 5,
                dormant_threads_to_revive=row.dormant_threads_to_revive or [],
                reveals_allowed_soon=row.reveals_allowed_soon or [],
                reveals_forbidden_for_now=row.reveals_forbidden_for_now or [],
                next_one_hour_intention=row.next_one_hour_intention or "",
                next_six_hour_intention=row.next_six_hour_intention or "",
                next_twenty_four_hour_intention=row.next_twenty_four_hour_intention or "",
                next_hour_focus=row.next_hour_focus,
                next_six_hours=row.next_six_hours,
                recap_priorities=row.recap_priorities or [],
                fan_theory_potential=row.fan_theory_potential or 5,
                clip_generation_potential=row.clip_generation_potential or 5,
                reentry_clarity_priority=row.reentry_clarity_priority or 5,
                quote_worthiness=row.quote_worthiness or 5,
                betrayal_value=row.betrayal_value or 5,
                daily_uniqueness=row.daily_uniqueness or 5,
                fandom_discussion_value=row.fandom_discussion_value or 5,
                recommendations=row.recommendations,
                risk_alerts=row.risk_alerts,
                house_pressure_actions=row.house_pressure_actions,
                audience_rollout_actions=row.audience_rollout_actions,
                manager_biases=row.manager_biases,
                simulation_ranking=row.simulation_ranking,
                created_at=row.created_at,
                expires_at=row.expires_at,
            )

    def record_timeline_facts(
        self,
        *,
        facts: list[TimelineFactSnapshot],
        now=None,
    ) -> list[TimelineFactSnapshot]:
        now = ensure_utc(now or utcnow())
        if not facts:
            return []
        try:
            with self.session_factory.session_scope() as session:
                persisted: list[TimelineFactSnapshot] = []
                recent_cutoff = now - timedelta(minutes=45)
                for fact in facts:
                    row = session.scalar(
                        select(models.TimelineFact).where(
                            models.TimelineFact.fact_type == fact.fact_type,
                            models.TimelineFact.subject_slug == fact.subject_slug,
                            models.TimelineFact.related_slug == fact.related_slug,
                            models.TimelineFact.location_slug == fact.location_slug,
                            models.TimelineFact.object_slug == fact.object_slug,
                            models.TimelineFact.summary == fact.summary,
                            models.TimelineFact.created_at >= recent_cutoff,
                        )
                    )
                    if row is None:
                        row = models.TimelineFact(
                            fact_type=fact.fact_type,
                            subject_slug=fact.subject_slug,
                            related_slug=fact.related_slug,
                            location_slug=fact.location_slug,
                            location_name=fact.location_name,
                            object_slug=fact.object_slug,
                            object_name=fact.object_name,
                            summary=fact.summary,
                            confidence=fact.confidence,
                            source=fact.source,
                            metadata_json=fact.metadata,
                            created_at=now,
                        )
                        session.add(row)
                    else:
                        row.location_name = fact.location_name or row.location_name
                        row.object_name = fact.object_name or row.object_name
                        row.confidence = max(row.confidence, fact.confidence)
                        row.metadata_json = _deep_merge_dicts(row.metadata_json, fact.metadata)
                    persisted.append(fact.model_copy(update={"created_at": row.created_at or now}))
                return persisted
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.record_timeline_facts",
                exc,
                context={"fact_count": len(facts)},
                expected_inputs=["A migrated timeline_facts table."],
                retry_advice="Run migrations so timeline tracking persistence can resume.",
                fallback_used="return-unpersisted-timeline-facts",
            )
            return [fact.model_copy(update={"created_at": now}) for fact in facts]

    def list_recent_timeline_facts(
        self,
        *,
        hours: int = 24,
        limit: int = 12,
    ) -> list[TimelineFactSnapshot]:
        threshold = ensure_utc(utcnow()) - timedelta(hours=max(1, hours))
        try:
            with self.session_factory.session_scope() as session:
                rows = session.scalars(
                    select(models.TimelineFact)
                    .where(models.TimelineFact.created_at >= threshold)
                    .order_by(desc(models.TimelineFact.created_at))
                    .limit(limit)
                ).all()
                return [
                    TimelineFactSnapshot(
                        fact_type=row.fact_type,
                        subject_slug=row.subject_slug,
                        related_slug=row.related_slug,
                        location_slug=row.location_slug,
                        location_name=row.location_name,
                        object_slug=row.object_slug,
                        object_name=row.object_name,
                        summary=row.summary,
                        confidence=row.confidence,
                        source=row.source,
                        metadata=row.metadata_json,
                        created_at=row.created_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_recent_timeline_facts",
                exc,
                context={"hours": hours, "limit": limit},
                expected_inputs=["A migrated timeline_facts table."],
                retry_advice="Run migrations so timeline reads can resume.",
                fallback_used="empty-timeline-facts",
            )
            return []

    def sync_object_possessions(
        self,
        *,
        snapshots: list[ObjectPossessionSnapshot],
        now=None,
    ) -> list[ObjectPossessionSnapshot]:
        now = ensure_utc(now or utcnow())
        if not snapshots:
            return []
        try:
            with self.session_factory.session_scope() as session:
                for snapshot in snapshots:
                    row = session.scalar(
                        select(models.ObjectPossession).where(
                            models.ObjectPossession.object_slug == snapshot.object_slug
                        )
                    )
                    if row is None:
                        row = models.ObjectPossession(
                            object_slug=snapshot.object_slug,
                            object_name=snapshot.object_name,
                            created_at=now,
                        )
                        session.add(row)
                    row.object_name = snapshot.object_name or row.object_name
                    row.holder_character_slug = snapshot.holder_character_slug
                    row.location_slug = snapshot.location_slug
                    row.location_name = snapshot.location_name
                    row.possession_status = snapshot.possession_status
                    row.summary = snapshot.summary
                    row.confidence = snapshot.confidence
                    row.metadata_json = snapshot.metadata
                    row.last_seen_at = ensure_utc(snapshot.last_seen_at or now)
                    row.updated_at = now
                return [
                    snapshot.model_copy(update={"created_at": now, "last_seen_at": now})
                    for snapshot in snapshots
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.sync_object_possessions",
                exc,
                context={"snapshot_count": len(snapshots)},
                expected_inputs=["A migrated object_possessions table."],
                retry_advice="Run migrations so object-possession persistence can resume.",
                fallback_used="return-unpersisted-object-possessions",
            )
            return [
                snapshot.model_copy(update={"created_at": now, "last_seen_at": now})
                for snapshot in snapshots
            ]

    def list_object_possessions(self, *, limit: int = 8) -> list[ObjectPossessionSnapshot]:
        try:
            with self.session_factory.session_scope() as session:
                rows = session.scalars(
                    select(models.ObjectPossession)
                    .order_by(desc(models.ObjectPossession.updated_at))
                    .limit(limit)
                ).all()
                return [
                    ObjectPossessionSnapshot(
                        object_slug=row.object_slug,
                        object_name=row.object_name,
                        holder_character_slug=row.holder_character_slug,
                        location_slug=row.location_slug,
                        location_name=row.location_name,
                        possession_status=row.possession_status,
                        summary=row.summary,
                        confidence=row.confidence,
                        metadata=row.metadata_json,
                        last_seen_at=row.last_seen_at,
                        created_at=row.created_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_object_possessions",
                exc,
                context={"limit": limit},
                expected_inputs=["A migrated object_possessions table."],
                retry_advice="Run migrations so possession reads can resume.",
                fallback_used="empty-object-possessions",
            )
            return []

    def sync_chronology_graph(
        self,
        *,
        nodes: list[ChronologyNodeSnapshot],
        edges: list[ChronologyEdgeSnapshot],
        now=None,
    ) -> tuple[list[ChronologyNodeSnapshot], list[ChronologyEdgeSnapshot]]:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                existing_nodes = {
                    row.node_key: row
                    for row in session.scalars(select(models.ChronologyGraphNode)).all()
                }
                for snapshot in nodes:
                    row = existing_nodes.get(snapshot.node_key)
                    if row is None:
                        row = models.ChronologyGraphNode(
                            node_key=snapshot.node_key,
                            created_at=now,
                        )
                        session.add(row)
                        existing_nodes[snapshot.node_key] = row
                    row.node_type = snapshot.node_type
                    row.label = snapshot.label
                    row.status = snapshot.status
                    row.metadata_json = snapshot.metadata
                    row.updated_at = now

                recent_cutoff = now - timedelta(hours=12)
                persisted_edges: list[ChronologyEdgeSnapshot] = []
                for snapshot in edges:
                    row = session.scalar(
                        select(models.ChronologyGraphEdge).where(
                            models.ChronologyGraphEdge.subject_key == snapshot.subject_key,
                            models.ChronologyGraphEdge.predicate == snapshot.predicate,
                            models.ChronologyGraphEdge.object_key == snapshot.object_key,
                            models.ChronologyGraphEdge.supporting_text
                            == snapshot.supporting_text,
                            models.ChronologyGraphEdge.created_at >= recent_cutoff,
                        )
                    )
                    if row is None:
                        row = models.ChronologyGraphEdge(
                            subject_key=snapshot.subject_key,
                            predicate=snapshot.predicate,
                            object_key=snapshot.object_key,
                            created_at=now,
                        )
                        session.add(row)
                    row.confidence = snapshot.confidence
                    row.contradiction_status = snapshot.contradiction_status
                    row.supporting_text = snapshot.supporting_text
                    row.source = snapshot.source
                    row.metadata_json = snapshot.metadata
                    row.updated_at = now
                    persisted_edges.append(
                        snapshot.model_copy(
                            update={"created_at": row.created_at or now, "updated_at": now}
                        )
                    )

                persisted_nodes = [
                    snapshot.model_copy(update={"created_at": now, "updated_at": now})
                    for snapshot in nodes
                ]
                return persisted_nodes, persisted_edges
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.sync_chronology_graph",
                exc,
                context={"node_count": len(nodes), "edge_count": len(edges)},
                expected_inputs=[
                    "Migrated chronology_graph_nodes and chronology_graph_edges tables."
                ],
                retry_advice="Run migrations so chronology graph persistence can resume.",
                fallback_used="return-unpersisted-chronology-graph",
            )
            return (
                [
                    snapshot.model_copy(update={"created_at": now, "updated_at": now})
                    for snapshot in nodes
                ],
                [
                    snapshot.model_copy(update={"created_at": now, "updated_at": now})
                    for snapshot in edges
                ],
            )

    def list_recent_chronology_edges(
        self,
        *,
        limit: int = 12,
        contradiction_only: bool = False,
    ) -> list[ChronologyEdgeSnapshot]:
        try:
            with self.session_factory.session_scope() as session:
                stmt = select(models.ChronologyGraphEdge).order_by(
                    desc(models.ChronologyGraphEdge.updated_at),
                    desc(models.ChronologyGraphEdge.created_at),
                )
                if contradiction_only:
                    stmt = stmt.where(models.ChronologyGraphEdge.contradiction_status != "clean")
                rows = session.scalars(stmt.limit(limit)).all()
                return [
                    ChronologyEdgeSnapshot(
                        subject_key=row.subject_key,
                        predicate=row.predicate,
                        object_key=row.object_key,
                        confidence=row.confidence,
                        contradiction_status=row.contradiction_status,
                        supporting_text=row.supporting_text,
                        source=row.source,
                        metadata=row.metadata_json,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_recent_chronology_edges",
                exc,
                context={"limit": limit, "contradiction_only": contradiction_only},
                expected_inputs=[
                    "Migrated chronology_graph_edges table."
                ],
                retry_advice="Run migrations so chronology graph reads can resume.",
                fallback_used="empty-chronology-edges",
            )
            return []

    def sync_viewer_signals(
        self,
        *,
        signals: list[ViewerSignalSnapshot],
        now=None,
    ) -> list[ViewerSignalSnapshot]:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                active_keys = {signal.signal_key for signal in signals}
                existing = session.scalars(select(models.ViewerSignal)).all()
                existing_by_key = {row.signal_key: row for row in existing}
                for signal in signals:
                    row = existing_by_key.get(signal.signal_key)
                    if row is None:
                        row = models.ViewerSignal(signal_key=signal.signal_key, created_at=now)
                        session.add(row)
                    row.signal_type = signal.signal_type
                    row.subject = signal.subject
                    row.intensity = signal.intensity
                    row.sentiment = signal.sentiment
                    row.summary = signal.summary
                    row.source = signal.source
                    row.retention_impact = signal.retention_impact
                    row.status = "active"
                    row.metadata_json = signal.metadata
                    row.expires_at = signal.expires_at
                    row.updated_at = now
                for key, row in existing_by_key.items():
                    if key in active_keys:
                        continue
                    row.status = "expired"
                    row.updated_at = now
                return [signal.model_copy(update={"created_at": now}) for signal in signals]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.sync_viewer_signals",
                exc,
                context={"signal_count": len(signals)},
                expected_inputs=["A migrated viewer_signals table."],
                retry_advice="Run migrations so viewer-signal persistence can resume.",
                fallback_used="return-unpersisted-viewer-signals",
            )
            return [signal.model_copy(update={"created_at": now}) for signal in signals]

    def list_active_viewer_signals(self, *, limit: int = 8, now=None) -> list[ViewerSignalSnapshot]:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                rows = session.scalars(
                    select(models.ViewerSignal)
                    .where(
                        models.ViewerSignal.status == "active",
                        or_(
                            models.ViewerSignal.expires_at.is_(None),
                            models.ViewerSignal.expires_at >= now,
                        ),
                    )
                    .order_by(
                        desc(models.ViewerSignal.retention_impact),
                        desc(models.ViewerSignal.intensity),
                        desc(models.ViewerSignal.updated_at),
                    )
                    .limit(limit)
                ).all()
                return [
                    ViewerSignalSnapshot(
                        signal_key=row.signal_key,
                        signal_type=row.signal_type,
                        subject=row.subject,
                        intensity=row.intensity,
                        sentiment=row.sentiment,
                        summary=row.summary,
                        source=row.source,
                        retention_impact=row.retention_impact,
                        metadata=row.metadata_json,
                        expires_at=row.expires_at,
                        created_at=row.created_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_active_viewer_signals",
                exc,
                context={"limit": limit},
                expected_inputs=["A migrated viewer_signals table."],
                retry_advice="Run migrations so viewer-signal reads can resume.",
                fallback_used="empty-viewer-signals",
            )
            return []

    def save_voice_fingerprints(
        self,
        *,
        fingerprints: list[VoiceFingerprintSnapshot],
        now=None,
    ) -> list[VoiceFingerprintSnapshot]:
        now = ensure_utc(now or utcnow())
        if not fingerprints:
            return []
        try:
            with self.session_factory.session_scope() as session:
                existing = {
                    row.character_slug: row
                    for row in session.scalars(select(models.VoiceFingerprint)).all()
                }
                for snapshot in fingerprints:
                    row = existing.get(snapshot.character_slug)
                    if row is None:
                        row = models.VoiceFingerprint(
                            character_slug=snapshot.character_slug,
                            created_at=now,
                        )
                        session.add(row)
                    row.signature_line = snapshot.signature_line
                    row.cadence_profile = snapshot.cadence_profile
                    row.conflict_tone = snapshot.conflict_tone
                    row.affection_tone = snapshot.affection_tone
                    row.humor_markers = snapshot.humor_markers
                    row.lexical_markers = snapshot.lexical_markers
                    row.taboo_markers = snapshot.taboo_markers
                    row.metadata_json = snapshot.metadata
                    row.updated_at = now
                return [
                    snapshot.model_copy(update={"updated_at": now}) for snapshot in fingerprints
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.save_voice_fingerprints",
                exc,
                context={"fingerprint_count": len(fingerprints)},
                expected_inputs=["A migrated voice_fingerprints table."],
                retry_advice="Run migrations so voice fingerprint persistence can resume.",
                fallback_used="return-unpersisted-voice-fingerprints",
            )
            return [snapshot.model_copy(update={"updated_at": now}) for snapshot in fingerprints]

    def list_voice_fingerprints(
        self,
        *,
        character_slugs: list[str] | None = None,
        limit: int = 8,
    ) -> list[VoiceFingerprintSnapshot]:
        try:
            with self.session_factory.session_scope() as session:
                stmt = select(models.VoiceFingerprint).order_by(
                    desc(models.VoiceFingerprint.updated_at)
                )
                if character_slugs:
                    stmt = stmt.where(models.VoiceFingerprint.character_slug.in_(character_slugs))
                rows = session.scalars(stmt.limit(limit)).all()
                return [
                    VoiceFingerprintSnapshot(
                        character_slug=row.character_slug,
                        signature_line=row.signature_line,
                        cadence_profile=row.cadence_profile,
                        conflict_tone=row.conflict_tone,
                        affection_tone=row.affection_tone,
                        humor_markers=row.humor_markers,
                        lexical_markers=row.lexical_markers,
                        taboo_markers=row.taboo_markers,
                        metadata=row.metadata_json,
                        updated_at=row.updated_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_voice_fingerprints",
                exc,
                context={"character_slugs": character_slugs, "limit": limit},
                expected_inputs=["A migrated voice_fingerprints table."],
                retry_advice="Run migrations so voice fingerprint reads can resume.",
                fallback_used="empty-voice-fingerprints",
            )
            return []

    def sync_guest_profiles(
        self,
        *,
        profiles: list[GuestProfileSnapshot],
        now=None,
    ) -> list[GuestProfileSnapshot]:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                active_keys = {profile.guest_key for profile in profiles}
                existing = {
                    row.guest_key: row for row in session.scalars(select(models.GuestProfile)).all()
                }
                for snapshot in profiles:
                    row = existing.get(snapshot.guest_key)
                    if row is None:
                        row = models.GuestProfile(
                            guest_key=snapshot.guest_key,
                            created_at=now,
                        )
                        session.add(row)
                    row.display_name = snapshot.display_name
                    row.role = snapshot.role
                    row.status = snapshot.status
                    row.pressure_tags = snapshot.pressure_tags
                    row.summary = snapshot.summary
                    row.hook = snapshot.hook
                    row.linked_location_slug = snapshot.linked_location_slug
                    row.metadata_json = snapshot.metadata
                    row.updated_at = now
                for guest_key, row in existing.items():
                    if guest_key in active_keys:
                        continue
                    row.status = "archived"
                    row.updated_at = now
                return [snapshot.model_copy(update={"updated_at": now}) for snapshot in profiles]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.sync_guest_profiles",
                exc,
                context={"profile_count": len(profiles)},
                expected_inputs=["A migrated guest_profiles table."],
                retry_advice="Run migrations so guest profile persistence can resume.",
                fallback_used="return-unpersisted-guest-profiles",
            )
            return [snapshot.model_copy(update={"updated_at": now}) for snapshot in profiles]

    def list_active_guest_profiles(self, *, limit: int = 6) -> list[GuestProfileSnapshot]:
        try:
            with self.session_factory.session_scope() as session:
                rows = session.scalars(
                    select(models.GuestProfile)
                    .where(models.GuestProfile.status == "active")
                    .order_by(desc(models.GuestProfile.updated_at))
                    .limit(limit)
                ).all()
                return [
                    GuestProfileSnapshot(
                        guest_key=row.guest_key,
                        display_name=row.display_name,
                        role=row.role,
                        status=row.status,
                        pressure_tags=row.pressure_tags,
                        summary=row.summary,
                        hook=row.hook,
                        linked_location_slug=row.linked_location_slug,
                        metadata=row.metadata_json,
                        updated_at=row.updated_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_active_guest_profiles",
                exc,
                context={"limit": limit},
                expected_inputs=["A migrated guest_profiles table."],
                retry_advice="Run migrations so guest profile reads can resume.",
                fallback_used="empty-guest-profiles",
            )
            return []

    def record_hot_patch_canary_run(
        self,
        *,
        snapshot: HotPatchCanaryRunSnapshot,
        now=None,
    ) -> HotPatchCanaryRunSnapshot:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                row = models.HotPatchCanaryRun(
                    status=snapshot.status,
                    changed_files=snapshot.changed_files,
                    checks=snapshot.checks,
                    error_summary=snapshot.error_summary,
                    metadata_json=snapshot.metadata,
                    created_at=now,
                )
                session.add(row)
                session.flush()
                return snapshot.model_copy(update={"created_at": now})
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.record_hot_patch_canary_run",
                exc,
                context={"status": snapshot.status, "changed_files": snapshot.changed_files},
                expected_inputs=["A migrated hot_patch_canary_runs table."],
                retry_advice="Run migrations so hot patch canary telemetry can resume.",
                fallback_used="return-unpersisted-hot-patch-canary-run",
            )
            return snapshot.model_copy(update={"created_at": now})

    def get_latest_hot_patch_canary_run(self) -> HotPatchCanaryRunSnapshot | None:
        try:
            with self.session_factory.session_scope() as session:
                row = session.scalar(
                    select(models.HotPatchCanaryRun).order_by(
                        desc(models.HotPatchCanaryRun.created_at)
                    )
                )
                if row is None:
                    return None
                return HotPatchCanaryRunSnapshot(
                    status=row.status,
                    changed_files=row.changed_files,
                    checks=row.checks,
                    error_summary=row.error_summary,
                    metadata=row.metadata_json,
                    created_at=row.created_at,
                )
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.get_latest_hot_patch_canary_run",
                exc,
                context={},
                expected_inputs=["A migrated hot_patch_canary_runs table."],
                retry_advice="Run migrations so hot patch canary reads can resume.",
                fallback_used="no-hot-patch-canary-run",
            )
            return None

    def record_strategic_brief(
        self,
        *,
        plan: StrategicBriefPlan,
        source: str,
        model_name: str | None,
        simulation_report: SimulationLabReport | None = None,
        now=None,
    ) -> StrategicBriefSnapshot:
        now = ensure_utc(now or utcnow())
        expires_at = now + timedelta(minutes=plan.expires_in_minutes)
        with self.session_factory.session_scope() as session:
            active_rows = session.scalars(
                select(models.StrategicBrief).where(models.StrategicBrief.status == "active")
            ).all()
            for row in active_rows:
                row.status = "archived"
            row = models.StrategicBrief(
                source=source,
                status="active",
                model_name=model_name,
                title=plan.title,
                current_north_star_objective=plan.current_north_star_objective,
                viewer_value_thesis=plan.viewer_value_thesis,
                urgency=plan.urgency,
                arc_priority_ranking=plan.arc_priority_ranking,
                danger_of_drift_score=plan.danger_of_drift_score,
                cliffhanger_urgency=plan.cliffhanger_urgency,
                romance_urgency=plan.romance_urgency,
                mystery_urgency=plan.mystery_urgency,
                house_pressure_priority=plan.house_pressure_priority,
                audience_rollout_priority=plan.audience_rollout_priority,
                dormant_threads_to_revive=plan.dormant_threads_to_revive,
                reveals_allowed_soon=plan.reveals_allowed_soon,
                reveals_forbidden_for_now=plan.reveals_forbidden_for_now,
                next_one_hour_intention=plan.next_one_hour_intention,
                next_six_hour_intention=plan.next_six_hour_intention,
                next_twenty_four_hour_intention=plan.next_twenty_four_hour_intention,
                next_hour_focus=plan.next_hour_focus,
                next_six_hours=plan.next_six_hours,
                recap_priorities=plan.recap_priorities,
                fan_theory_potential=plan.fan_theory_potential,
                clip_generation_potential=plan.clip_generation_potential,
                reentry_clarity_priority=plan.reentry_clarity_priority,
                quote_worthiness=plan.quote_worthiness,
                betrayal_value=plan.betrayal_value,
                daily_uniqueness=plan.daily_uniqueness,
                fandom_discussion_value=plan.fandom_discussion_value,
                recommendations=plan.recommendations,
                risk_alerts=plan.risk_alerts,
                house_pressure_actions=plan.house_pressure_actions,
                audience_rollout_actions=plan.audience_rollout_actions,
                manager_biases=plan.manager_biases,
                simulation_ranking=[
                    f"{candidate.strategy_key}: {candidate.score}"
                    for candidate in (simulation_report.candidates if simulation_report else [])
                ],
                metadata_json={
                    "expires_in_minutes": plan.expires_in_minutes,
                    "simulation_report": simulation_report.model_dump(mode="json")
                    if simulation_report
                    else {},
                },
                expires_at=expires_at,
                created_at=now,
            )
            session.add(row)
            session.flush()
            if simulation_report is not None:
                for ranking in session.scalars(
                    select(models.StrategyRanking).where(
                        models.StrategyRanking.simulation_run_id == simulation_report.run_id
                    )
                ).all():
                    ranking.strategic_brief_id = row.id
            return StrategicBriefSnapshot(
                source=row.source,
                model_name=row.model_name,
                title=row.title,
                current_north_star_objective=row.current_north_star_objective,
                viewer_value_thesis=row.viewer_value_thesis,
                urgency=row.urgency,
                arc_priority_ranking=row.arc_priority_ranking,
                danger_of_drift_score=row.danger_of_drift_score,
                cliffhanger_urgency=row.cliffhanger_urgency,
                romance_urgency=row.romance_urgency,
                mystery_urgency=row.mystery_urgency,
                house_pressure_priority=row.house_pressure_priority,
                audience_rollout_priority=row.audience_rollout_priority,
                dormant_threads_to_revive=row.dormant_threads_to_revive,
                reveals_allowed_soon=row.reveals_allowed_soon,
                reveals_forbidden_for_now=row.reveals_forbidden_for_now,
                next_one_hour_intention=row.next_one_hour_intention,
                next_six_hour_intention=row.next_six_hour_intention,
                next_twenty_four_hour_intention=row.next_twenty_four_hour_intention,
                next_hour_focus=row.next_hour_focus,
                next_six_hours=row.next_six_hours,
                recap_priorities=row.recap_priorities,
                fan_theory_potential=row.fan_theory_potential,
                clip_generation_potential=row.clip_generation_potential,
                reentry_clarity_priority=row.reentry_clarity_priority,
                quote_worthiness=row.quote_worthiness,
                betrayal_value=row.betrayal_value,
                daily_uniqueness=row.daily_uniqueness,
                fandom_discussion_value=row.fandom_discussion_value,
                recommendations=row.recommendations,
                risk_alerts=row.risk_alerts,
                house_pressure_actions=row.house_pressure_actions,
                audience_rollout_actions=row.audience_rollout_actions,
                manager_biases=row.manager_biases,
                simulation_ranking=row.simulation_ranking,
                created_at=row.created_at,
                expires_at=row.expires_at,
            )

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
            character = session.scalar(
                select(models.Character).where(models.Character.slug == character_slug)
            )
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

    def record_manager_directive(
        self, plan: ManagerDirectivePlan, *, tick_no: int, now=None
    ) -> dict[str, Any]:
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            scene = session.scalar(
                select(models.SceneState)
                .where(models.SceneState.status == "active")
                .order_by(desc(models.SceneState.id))
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
                per_character={
                    slug: goal.model_dump() for slug, goal in plan.per_character.items()
                },
                thought_pulse=plan.thought_pulse.model_dump(),
                pacing_actions=plan.pacing_actions,
                continuity_watch=plan.continuity_watch,
                unresolved_questions_to_push=plan.unresolved_questions_to_push,
                recentering_hint=plan.recentering_hint,
                created_at=now,
            )
            session.add(row)
            session.flush()
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
            metadata = dict(run_state.metadata_json)
            metadata["runtime_phase"] = "manager-planned"
            metadata["latest_directive_id"] = row.id
            run_state.metadata_json = metadata
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

            speaker = session.scalar(
                select(models.Character).where(models.Character.slug == speaker_slug)
            )
            scene = session.scalar(
                select(models.SceneState)
                .where(models.SceneState.status == "active")
                .order_by(desc(models.SceneState.id))
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
                select(models.CharacterState).where(
                    models.CharacterState.character_id == speaker.id
                )
            )
            if speaker_state is not None:
                speaker_state.last_spoke_at = now
                speaker_state.silence_streak = 0
                emotional_state = dict(speaker_state.emotional_state)
                if turn.tone:
                    emotional_state["current"] = turn.tone
                emotional_state["last_public_move"] = turn.public_message[:120]
                speaker_state.emotional_state = emotional_state
                if any(
                    event.event_type.value in {"conflict", "threat", "reveal"} for event in events
                ):
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
                counterpart = session.scalar(
                    select(models.Character).where(models.Character.slug == delta.character_slug)
                )
                if counterpart is None:
                    continue
                pair_key = tuple(sorted((speaker.id, counterpart.id)))
                relationship = relationship_lookup.get(pair_key)
                if relationship is None:
                    relationship = self._build_relationship(
                        pair_key=pair_key,
                        summary=delta.summary,
                        now=now,
                    )
                    session.add(relationship)
                    relationship_lookup[pair_key] = relationship
                relationship.trust_score = _clamp(relationship.trust_score + delta.trust_delta)
                relationship.desire_score = _clamp(relationship.desire_score + delta.desire_delta)
                relationship.suspicion_score = _clamp(
                    relationship.suspicion_score + delta.suspicion_delta
                )
                relationship.obligation_score = _clamp(
                    relationship.obligation_score + delta.obligation_delta
                )
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
                        affects_relationships=[
                            delta.character_slug for delta in turn.relationship_updates
                        ],
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
            metadata = dict(run_state.metadata_json)
            metadata["runtime_phase"] = "post-turn"
            metadata["active_speaker"] = speaker_slug
            metadata["latest_message_id"] = message.id
            run_state.metadata_json = metadata
            session.flush()

            return {
                "tick_no": next_tick,
                "created_at": now,
                "message_id": message.id,
                "thought_pulse": pulse_content,
            }

    def apply_story_progression(
        self, plan: StoryProgressionPlan, *, now=None
    ) -> StoryProgressionPlan:
        if not plan.arc_updates and not plan.surfaced_questions and not plan.archived_threads:
            return plan
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            arcs = {
                row.slug: row
                for row in session.scalars(
                    select(models.StoryArc).where(models.StoryArc.status != "resolved")
                ).all()
            }
            surfaced_questions = list(plan.surfaced_questions)
            archived_threads = list(plan.archived_threads)
            for update in plan.arc_updates:
                arc = arcs.get(update.slug)
                if arc is None:
                    continue
                arc.stage_index = update.stage_index
                arc.pressure_score = update.pressure_score
                metadata = dict(arc.metadata_json)
                metadata.update(update.metadata)
                metadata["last_progress_checkpoint_at"] = isoformat(now)
                arc.metadata_json = metadata
                surfaced_questions.extend(update.surfaced_questions)
                archived_threads.extend(update.archived_threads)

            self._update_unresolved_questions(
                session,
                surfaced_questions,
                [],
                archived_threads=archived_threads,
            )
        return plan

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
            metadata = dict(run_state.metadata_json)
            metadata["runtime_phase"] = "recap-complete"
            metadata["last_recap_generated_at"] = isoformat(bucket_end_at)
            run_state.metadata_json = metadata

    def record_recap_quality_scores(
        self,
        *,
        bucket_end_at,
        quality_scores: dict[str, dict[str, Any]],
        now=None,
    ) -> None:
        now = ensure_utc(now or utcnow())
        if not quality_scores:
            return
        with self.session_factory.session_scope() as session:
            summary_lookup = {
                row.summary_window: row
                for row in session.scalars(
                    select(models.Summary).where(models.Summary.bucket_end_at == bucket_end_at)
                ).all()
            }
            for window, payload in quality_scores.items():
                summary = summary_lookup.get(window)
                session.add(
                    models.RecapQualityScore(
                        summary_id=summary.id if summary else None,
                        summary_window=window,
                        bucket_end_at=bucket_end_at,
                        usefulness=_clamp(_int_or_default(payload.get("usefulness"), 5), 0, 10),
                        clarity=_clamp(_int_or_default(payload.get("clarity"), 5), 0, 10),
                        theory_value=_clamp(_int_or_default(payload.get("theory_value"), 5), 0, 10),
                        emotional_readability=_clamp(
                            _int_or_default(payload.get("emotional_readability"), 5),
                            0,
                            10,
                        ),
                        next_hook_strength=_clamp(
                            _int_or_default(payload.get("next_hook_strength"), 5),
                            0,
                            10,
                        ),
                        issues=[
                            _compact_reason(item)
                            for item in payload.get("issues", [])
                            if _compact_reason(item)
                        ],
                        created_at=now,
                    )
                )

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
                for row in session.scalars(
                    select(models.Character).order_by(models.Character.id)
                ).all()
            }
            rows = session.scalars(
                select(models.Relationship).order_by(desc(models.Relationship.last_shift_at))
            ).all()
            result = []
            for row in rows:
                a = characters.get(row.character_a_id, "?")
                b = characters.get(row.character_b_id, "?")
                result.append(
                    f"{a}<->{b}: trust {row.trust_score}, desire {row.desire_score}, "
                    f"suspicion {row.suspicion_score}, obligation {row.obligation_score}. "
                    f"{row.summary}"
                )
            return result

    def list_dormant_threads(self, *, limit: int = 6) -> list[DormantThreadSnapshot]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.DormantThreadRegistry)
                .where(models.DormantThreadRegistry.status != "archived")
                .order_by(
                    desc(models.DormantThreadRegistry.heat),
                    desc(models.DormantThreadRegistry.updated_at),
                )
                .limit(limit)
            ).all()
            return [
                DormantThreadSnapshot(
                    thread_key=row.thread_key,
                    summary=row.summary,
                    source=row.source,
                    status=row.status,
                    heat=row.heat,
                    last_seen_at=row.last_seen_at,
                    last_revived_at=row.last_revived_at,
                    metadata=row.metadata_json,
                )
                for row in rows
            ]

    def sync_dormant_threads(
        self,
        *,
        threads: list[DormantThreadSnapshot],
        now=None,
    ) -> list[DormantThreadSnapshot]:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            rows = session.scalars(select(models.DormantThreadRegistry)).all()
            existing = {row.thread_key: row for row in rows}
            active_keys = {thread.thread_key for thread in threads}
            for thread in threads:
                row = existing.get(thread.thread_key)
                metadata = dict(thread.metadata)
                metadata["synced_at"] = isoformat(now)
                if row is None:
                    row = models.DormantThreadRegistry(
                        thread_key=thread.thread_key,
                        summary=thread.summary,
                        source=thread.source,
                        status=thread.status,
                        heat=thread.heat,
                        last_seen_at=thread.last_seen_at or now,
                        last_revived_at=thread.last_revived_at,
                        metadata_json=metadata,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(row)
                    continue
                row.summary = thread.summary
                row.source = thread.source
                row.status = thread.status
                row.heat = thread.heat
                row.last_seen_at = thread.last_seen_at or now
                row.last_revived_at = thread.last_revived_at
                row.metadata_json = metadata
                row.updated_at = now

            for key, row in existing.items():
                if key in active_keys:
                    continue
                row.status = "archived"
                row.updated_at = now
            return threads

    def list_recent_recap_quality_scores(self, *, limit: int = 6) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.RecapQualityScore)
                .order_by(desc(models.RecapQualityScore.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "summary_window": row.summary_window,
                    "bucket_end_at": row.bucket_end_at,
                    "usefulness": row.usefulness,
                    "clarity": row.clarity,
                    "theory_value": row.theory_value,
                    "emotional_readability": row.emotional_readability,
                    "next_hook_strength": row.next_hook_strength,
                    "issues": row.issues,
                }
                for row in rows
            ]

    def save_hourly_progress_ledger(
        self,
        *,
        snapshot: HourlyProgressLedgerSnapshot,
        now=None,
    ) -> HourlyProgressLedgerSnapshot:
        now = ensure_utc(now or utcnow())
        bucket_start_at = ensure_utc(snapshot.bucket_start_at or floor_to_hour(now))
        bucket_end_at = ensure_utc(snapshot.bucket_end_at or (bucket_start_at + timedelta(hours=1)))
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.HourlyProgressLedger).where(
                    models.HourlyProgressLedger.bucket_start_at == bucket_start_at
                )
            )
            if row is None:
                row = models.HourlyProgressLedger(
                    bucket_start_at=bucket_start_at,
                    bucket_end_at=bucket_end_at,
                    created_at=now,
                )
                session.add(row)
            row.bucket_end_at = bucket_end_at
            row.meaningful_progressions = snapshot.meaningful_progressions
            row.trust_shift_count = snapshot.trust_shift_count
            row.desire_shift_count = snapshot.desire_shift_count
            row.evidence_shift_count = snapshot.evidence_shift_count
            row.debt_shift_count = snapshot.debt_shift_count
            row.power_shift_count = snapshot.power_shift_count
            row.loyalty_shift_count = snapshot.loyalty_shift_count
            row.contract_met = snapshot.contract_met
            row.dominant_axis = snapshot.dominant_axis
            row.blockers = snapshot.blockers
            row.recommended_push = snapshot.recommended_push
            row.metadata_json = snapshot.metadata
            row.updated_at = now
            return snapshot.model_copy(
                update={
                    "bucket_start_at": bucket_start_at,
                    "bucket_end_at": bucket_end_at,
                    "metadata": snapshot.metadata,
                }
            )

    def get_latest_hourly_progress_ledger(self) -> HourlyProgressLedgerSnapshot | None:
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.HourlyProgressLedger).order_by(
                    desc(models.HourlyProgressLedger.bucket_start_at)
                )
            )
            if row is None:
                return None
            return HourlyProgressLedgerSnapshot(
                bucket_start_at=row.bucket_start_at,
                bucket_end_at=row.bucket_end_at,
                meaningful_progressions=row.meaningful_progressions,
                trust_shift_count=row.trust_shift_count,
                desire_shift_count=row.desire_shift_count,
                evidence_shift_count=row.evidence_shift_count,
                debt_shift_count=row.debt_shift_count,
                power_shift_count=row.power_shift_count,
                loyalty_shift_count=row.loyalty_shift_count,
                contract_met=row.contract_met,
                dominant_axis=row.dominant_axis,
                blockers=row.blockers,
                recommended_push=row.recommended_push,
                metadata=row.metadata_json,
            )

    def sync_programming_grid_slots(
        self,
        *,
        slots: list[ProgrammingGridSlotSnapshot],
        now=None,
    ) -> list[ProgrammingGridSlotSnapshot]:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                for slot in slots:
                    window_start_at = ensure_utc(slot.window_start_at or now)
                    row = session.scalar(
                        select(models.ProgrammingGridSlot).where(
                            models.ProgrammingGridSlot.horizon == slot.horizon,
                            models.ProgrammingGridSlot.slot_key == slot.slot_key,
                            models.ProgrammingGridSlot.window_start_at == window_start_at,
                        )
                    )
                    if row is None:
                        row = models.ProgrammingGridSlot(
                            horizon=slot.horizon,
                            slot_key=slot.slot_key,
                            window_start_at=window_start_at,
                            created_at=now,
                        )
                        session.add(row)
                    row.label = slot.label
                    row.objective = slot.objective
                    row.target_axis = slot.target_axis
                    row.status = slot.status
                    row.priority = slot.priority
                    row.notes = slot.notes
                    row.metadata_json = slot.metadata
                    row.window_end_at = ensure_utc(slot.window_end_at or now)
                    row.updated_at = now
                return [slot.model_copy(update={"updated_at": now}) for slot in slots]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.sync_programming_grid_slots",
                exc,
                context={"slot_count": len(slots)},
                expected_inputs=["A migrated programming_grid_slots table."],
                retry_advice="Run migrations so programming-grid persistence can resume.",
                fallback_used="return-unpersisted-grid-slots",
            )
            return [slot.model_copy(update={"updated_at": now}) for slot in slots]

    def list_programming_grid_slots(
        self,
        *,
        horizon: str | None = None,
        limit: int = 10,
    ) -> list[ProgrammingGridSlotSnapshot]:
        try:
            with self.session_factory.session_scope() as session:
                stmt = select(models.ProgrammingGridSlot).order_by(
                    desc(models.ProgrammingGridSlot.window_start_at),
                    desc(models.ProgrammingGridSlot.priority),
                )
                if horizon:
                    stmt = stmt.where(models.ProgrammingGridSlot.horizon == horizon)
                rows = session.scalars(stmt.limit(limit)).all()
                return [
                    ProgrammingGridSlotSnapshot(
                        horizon=row.horizon,
                        slot_key=row.slot_key,
                        label=row.label,
                        objective=row.objective,
                        target_axis=row.target_axis,
                        status=row.status,
                        priority=row.priority,
                        notes=row.notes,
                        metadata=row.metadata_json,
                        window_start_at=row.window_start_at,
                        window_end_at=row.window_end_at,
                        updated_at=row.updated_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_programming_grid_slots",
                exc,
                context={"horizon": horizon, "limit": limit},
                expected_inputs=["A migrated programming_grid_slots table."],
                retry_advice="Run migrations so programming-grid reads can resume.",
                fallback_used="empty-programming-grid",
            )
            return []

    def list_recent_public_turn_reviews(self, *, limit: int = 8) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.PublicTurnReview)
                .order_by(desc(models.PublicTurnReview.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "speaker_slug": row.speaker_slug,
                    "review_status": row.review_status,
                    "critic_score": row.critic_score,
                    "repair_applied": row.repair_applied,
                    "reasons": row.reasons,
                    "repair_actions": row.repair_actions,
                    "quote_worthiness": row.quote_worthiness,
                    "clip_value": row.clip_value,
                    "fandom_discussion_value": row.fandom_discussion_value,
                    "novelty": row.novelty,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def record_canon_court_findings(
        self,
        *,
        findings: list[CanonCourtFindingSnapshot],
        message_id: int | None = None,
        now=None,
    ) -> list[CanonCourtFindingSnapshot]:
        if not findings:
            return []
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                persisted: list[CanonCourtFindingSnapshot] = []
                for finding in findings:
                    row = models.CanonCourtFinding(
                        message_id=message_id or finding.message_id,
                        issue_type=finding.issue_type,
                        severity=finding.severity,
                        action=finding.action,
                        summary=finding.summary,
                        evidence=finding.evidence,
                        metadata_json=finding.metadata,
                        created_at=now,
                    )
                    session.add(row)
                    session.flush()
                    persisted.append(
                        finding.model_copy(
                            update={
                                "message_id": row.message_id,
                                "created_at": now,
                            }
                        )
                    )
                return persisted
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.record_canon_court_findings",
                exc,
                context={"finding_count": len(findings), "message_id": message_id},
                expected_inputs=["A migrated canon_court_findings table."],
                retry_advice="Run migrations so canon-court persistence can resume.",
                fallback_used="return-unpersisted-canon-findings",
            )
            return [
                finding.model_copy(update={"message_id": message_id, "created_at": now})
                for finding in findings
            ]

    def list_recent_canon_court_findings(
        self,
        *,
        limit: int = 8,
    ) -> list[CanonCourtFindingSnapshot]:
        try:
            with self.session_factory.session_scope() as session:
                rows = session.scalars(
                    select(models.CanonCourtFinding)
                    .order_by(desc(models.CanonCourtFinding.created_at))
                    .limit(limit)
                ).all()
                return [
                    CanonCourtFindingSnapshot(
                        issue_type=row.issue_type,
                        severity=row.severity,
                        action=row.action,
                        summary=row.summary,
                        evidence=row.evidence,
                        metadata=row.metadata_json,
                        message_id=row.message_id,
                        created_at=row.created_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_recent_canon_court_findings",
                exc,
                context={"limit": limit},
                expected_inputs=["A migrated canon_court_findings table."],
                retry_advice="Run migrations so canon-court reads can resume.",
                fallback_used="empty-canon-findings",
            )
            return []

    def save_canon_capsule(
        self,
        *,
        snapshot: CanonCapsuleSnapshot,
        now=None,
    ) -> CanonCapsuleSnapshot:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            row = session.scalar(
                select(models.CanonCapsule).where(
                    models.CanonCapsule.window_key == snapshot.window_key
                )
            )
            if row is None:
                row = models.CanonCapsule(window_key=snapshot.window_key, created_at=now)
                session.add(row)
            row.headline = snapshot.headline
            row.state_of_play = snapshot.state_of_play
            row.key_clues = snapshot.key_clues
            row.relationship_fault_lines = snapshot.relationship_fault_lines
            row.active_pressures = snapshot.active_pressures
            row.unresolved_questions = snapshot.unresolved_questions
            row.protected_truths = snapshot.protected_truths
            row.recap_hooks = snapshot.recap_hooks
            row.metadata_json = snapshot.metadata
            row.updated_at = now
            created_at = row.created_at or now
            return snapshot.model_copy(update={"created_at": created_at})

    def list_canon_capsules(
        self,
        *,
        window_keys: list[str] | None = None,
    ) -> list[CanonCapsuleSnapshot]:
        with self.session_factory.session_scope() as session:
            stmt = select(models.CanonCapsule).order_by(models.CanonCapsule.window_key)
            if window_keys:
                stmt = stmt.where(models.CanonCapsule.window_key.in_(window_keys))
            rows = session.scalars(stmt).all()
            return [
                CanonCapsuleSnapshot(
                    window_key=row.window_key,
                    headline=row.headline,
                    state_of_play=row.state_of_play,
                    key_clues=row.key_clues,
                    relationship_fault_lines=row.relationship_fault_lines,
                    active_pressures=row.active_pressures,
                    unresolved_questions=row.unresolved_questions,
                    protected_truths=row.protected_truths,
                    recap_hooks=row.recap_hooks,
                    metadata=row.metadata_json,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def list_recent_highlight_packages(self, *, limit: int = 8) -> list[HighlightPackageSnapshot]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.HighlightPackage)
                .order_by(desc(models.HighlightPackage.created_at))
                .limit(limit)
            ).all()
            return [
                HighlightPackageSnapshot(
                    message_id=row.message_id,
                    speaker_slug=row.speaker_slug,
                    title=row.title,
                    alternate_titles=row.alternate_titles,
                    hook_line=row.hook_line,
                    quote_line=row.quote_line,
                    summary_blurb=row.summary_blurb,
                    ship_angle=row.ship_angle,
                    theory_angle=row.theory_angle,
                    conflict_axis=row.conflict_axis,
                    recommended_clip_seconds=row.recommended_clip_seconds,
                    source_window_minutes=row.source_window_minutes,
                    score=row.score,
                    metadata=row.metadata_json,
                    created_at=row.created_at,
                )
                for row in rows
            ]

    def list_recent_clip_value_scores(self, *, limit: int = 8) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.ClipValueScore)
                .order_by(desc(models.ClipValueScore.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "clip_value": row.clip_value,
                    "quote_value": row.quote_value,
                    "betrayal_value": row.betrayal_value,
                    "romance_intensity": row.romance_intensity,
                    "mystery_progression": row.mystery_progression,
                    "novelty": row.novelty,
                    "daily_uniqueness": row.daily_uniqueness,
                    "metadata": row.metadata_json,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def list_recent_fandom_signals(self, *, limit: int = 8) -> list[dict[str, Any]]:
        with self.session_factory.session_scope() as session:
            rows = session.scalars(
                select(models.FandomSignalCandidate)
                .order_by(desc(models.FandomSignalCandidate.created_at))
                .limit(limit)
            ).all()
            return [
                {
                    "signal_type": row.signal_type,
                    "subject": row.subject,
                    "intensity": row.intensity,
                    "rationale": row.rationale,
                    "metadata": row.metadata_json,
                    "created_at": row.created_at,
                }
                for row in rows
            ]

    def record_public_turn_review(
        self,
        *,
        message_id: int | None,
        speaker_slug: str,
        report: TurnCriticReport,
        turn: CharacterTurn,
        repaired: bool,
        strategic_brief: StrategicBriefSnapshot | None = None,
        now=None,
    ) -> None:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            status = "repaired" if repaired else "accepted"
            session.add(
                models.PublicTurnReview(
                    message_id=message_id,
                    speaker_slug=speaker_slug,
                    review_status=status,
                    critic_score=report.score,
                    repair_applied=repaired,
                    reasons=report.reasons,
                    repair_actions=report.repair_actions,
                    quote_worthiness=report.quote_worthiness,
                    clip_value=report.clip_value,
                    fandom_discussion_value=report.fandom_discussion_value,
                    novelty=report.novelty,
                    created_at=now,
                )
            )
            brief_id = self._get_latest_strategic_brief_id(session)
            if report.clip_value >= 5 or report.quote_worthiness >= 6:
                session.add(
                    models.ClipValueScore(
                        message_id=message_id,
                        strategic_brief_id=brief_id,
                        source="public-turn-review",
                        clip_value=report.clip_value,
                        quote_value=report.quote_worthiness,
                        betrayal_value=_estimate_betrayal_value(turn),
                        romance_intensity=_estimate_romance_intensity(turn),
                        mystery_progression=_estimate_mystery_progression(turn),
                        novelty=report.novelty,
                        daily_uniqueness=_estimate_daily_uniqueness(turn, report),
                        metadata_json={
                            "speaker_slug": speaker_slug,
                            "message_excerpt": turn.public_message[:140],
                            "strategic_title": strategic_brief.title if strategic_brief else "",
                        },
                        created_at=now,
                    )
                )
            for signal in _build_fandom_signals(
                speaker_slug=speaker_slug,
                turn=turn,
                report=report,
            ):
                session.add(
                    models.FandomSignalCandidate(
                        message_id=message_id,
                        strategic_brief_id=brief_id,
                        signal_type=signal["signal_type"],
                        subject=signal["subject"],
                        intensity=signal["intensity"],
                        rationale=signal["rationale"],
                        metadata_json=signal["metadata"],
                        created_at=now,
                    )
                )

    def record_highlight_package(
        self,
        *,
        package: HighlightPackageSnapshot,
        now=None,
    ) -> HighlightPackageSnapshot:
        now = ensure_utc(now or utcnow())
        with self.session_factory.session_scope() as session:
            row = models.HighlightPackage(
                message_id=package.message_id,
                speaker_slug=package.speaker_slug,
                title=package.title,
                alternate_titles=package.alternate_titles,
                hook_line=package.hook_line,
                quote_line=package.quote_line,
                summary_blurb=package.summary_blurb,
                ship_angle=package.ship_angle,
                theory_angle=package.theory_angle,
                conflict_axis=package.conflict_axis,
                recommended_clip_seconds=package.recommended_clip_seconds,
                source_window_minutes=package.source_window_minutes,
                score=package.score,
                metadata_json=package.metadata,
                created_at=now,
            )
            session.add(row)
            session.flush()
            return package.model_copy(update={"created_at": now})

    def record_monetization_package(
        self,
        *,
        package: MonetizationPackageSnapshot,
        now=None,
    ) -> MonetizationPackageSnapshot:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                row = models.MonetizationPackage(
                    message_id=package.message_id,
                    highlight_message_id=package.highlight_message_id,
                    speaker_slug=package.speaker_slug,
                    primary_title=package.primary_title,
                    alternate_titles=package.alternate_titles,
                    short_title_options=package.short_title_options,
                    hook_line=package.hook_line,
                    quote_line=package.quote_line,
                    summary_blurb=package.summary_blurb,
                    recap_blurb=package.recap_blurb,
                    chapter_label=package.chapter_label,
                    comment_prompt=package.comment_prompt,
                    ship_angle=package.ship_angle,
                    theory_angle=package.theory_angle,
                    betrayal_angle=package.betrayal_angle,
                    faction_labels=package.faction_labels,
                    tags=package.tags,
                    recommended_clip_start_seconds=package.recommended_clip_start_seconds,
                    recommended_clip_end_seconds=package.recommended_clip_end_seconds,
                    score=package.score,
                    metadata_json=package.metadata,
                    created_at=now,
                )
                session.add(row)
                session.flush()
                return package.model_copy(update={"created_at": now})
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.record_monetization_package",
                exc,
                context={"speaker_slug": package.speaker_slug, "score": package.score},
                expected_inputs=["A migrated monetization_packages table."],
                retry_advice="Run migrations so monetization packaging persistence can resume.",
                fallback_used="return-unpersisted-monetization-package",
            )
            return package.model_copy(update={"created_at": now})

    def list_recent_monetization_packages(
        self,
        *,
        limit: int = 8,
    ) -> list[MonetizationPackageSnapshot]:
        try:
            with self.session_factory.session_scope() as session:
                rows = session.scalars(
                    select(models.MonetizationPackage)
                    .order_by(desc(models.MonetizationPackage.created_at))
                    .limit(limit)
                ).all()
                return [
                    MonetizationPackageSnapshot(
                        message_id=row.message_id,
                        highlight_message_id=row.highlight_message_id,
                        speaker_slug=row.speaker_slug,
                        primary_title=row.primary_title,
                        alternate_titles=row.alternate_titles,
                        short_title_options=row.short_title_options,
                        hook_line=row.hook_line,
                        quote_line=row.quote_line,
                        summary_blurb=row.summary_blurb,
                        recap_blurb=row.recap_blurb,
                        chapter_label=row.chapter_label,
                        comment_prompt=row.comment_prompt,
                        ship_angle=row.ship_angle,
                        theory_angle=row.theory_angle,
                        betrayal_angle=row.betrayal_angle,
                        faction_labels=row.faction_labels,
                        tags=row.tags,
                        recommended_clip_start_seconds=row.recommended_clip_start_seconds,
                        recommended_clip_end_seconds=row.recommended_clip_end_seconds,
                        score=row.score,
                        metadata=row.metadata_json,
                        created_at=row.created_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_recent_monetization_packages",
                exc,
                context={"limit": limit},
                expected_inputs=["A migrated monetization_packages table."],
                retry_advice="Run migrations so monetization package reads can resume.",
                fallback_used="empty-monetization-packages",
            )
            return []

    def record_broadcast_asset(
        self,
        *,
        package: BroadcastAssetSnapshot,
        now=None,
    ) -> BroadcastAssetSnapshot:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                row = models.BroadcastAssetPackage(
                    message_id=package.message_id,
                    monetization_message_id=package.monetization_message_id,
                    speaker_slug=package.speaker_slug,
                    asset_title=package.asset_title,
                    hook_line=package.hook_line,
                    short_description=package.short_description,
                    long_description=package.long_description,
                    chapter_markers=package.chapter_markers,
                    clip_manifest=package.clip_manifest,
                    ship_labels=package.ship_labels,
                    theory_labels=package.theory_labels,
                    faction_labels=package.faction_labels,
                    tags=package.tags,
                    why_it_matters=package.why_it_matters,
                    comment_seed=package.comment_seed,
                    asset_score=package.asset_score,
                    metadata_json=package.metadata,
                    created_at=now,
                )
                session.add(row)
                session.flush()
                return package.model_copy(update={"created_at": now})
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.record_broadcast_asset",
                exc,
                context={"speaker_slug": package.speaker_slug, "asset_score": package.asset_score},
                expected_inputs=["A migrated broadcast_asset_packages table."],
                retry_advice="Run migrations so broadcast-asset persistence can resume.",
                fallback_used="return-unpersisted-broadcast-asset",
            )
            return package.model_copy(update={"created_at": now})

    def list_recent_broadcast_assets(
        self,
        *,
        limit: int = 8,
    ) -> list[BroadcastAssetSnapshot]:
        try:
            with self.session_factory.session_scope() as session:
                rows = session.scalars(
                    select(models.BroadcastAssetPackage)
                    .order_by(desc(models.BroadcastAssetPackage.created_at))
                    .limit(limit)
                ).all()
                return [
                    BroadcastAssetSnapshot(
                        message_id=row.message_id,
                        monetization_message_id=row.monetization_message_id,
                        speaker_slug=row.speaker_slug,
                        asset_title=row.asset_title,
                        hook_line=row.hook_line,
                        short_description=row.short_description,
                        long_description=row.long_description,
                        chapter_markers=row.chapter_markers,
                        clip_manifest=row.clip_manifest,
                        ship_labels=row.ship_labels,
                        theory_labels=row.theory_labels,
                        faction_labels=row.faction_labels,
                        tags=row.tags,
                        why_it_matters=row.why_it_matters,
                        comment_seed=row.comment_seed,
                        asset_score=row.asset_score,
                        metadata=row.metadata_json,
                        created_at=row.created_at,
                    )
                    for row in rows
                ]
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.list_recent_broadcast_assets",
                exc,
                context={"limit": limit},
                expected_inputs=["A migrated broadcast_asset_packages table."],
                retry_advice="Run migrations so broadcast-asset reads can resume.",
                fallback_used="empty-broadcast-assets",
            )
            return []

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
            return (
                session.scalar(
                    select(func.count(models.ThoughtPulse.id)).where(
                        models.ThoughtPulse.created_at >= threshold
                    )
                )
                or 0
            )

    def write_checkpoint(
        self, *, reason: str, phase: str | None = None, now=None
    ) -> dict[str, Any]:
        now = now or utcnow()
        with self.session_factory.session_scope() as session:
            run_state = self._get_run_state_model(session)
            world = session.scalar(select(models.WorldState).order_by(desc(models.WorldState.id)))
            scene = session.scalar(
                select(models.SceneState)
                .where(models.SceneState.status == "active")
                .order_by(desc(models.SceneState.started_at))
            )
            latest_directive = session.scalar(
                select(models.ManagerDirective).order_by(desc(models.ManagerDirective.created_at))
            )
            latest_message = session.scalar(
                select(models.Message).order_by(desc(models.Message.created_at))
            )

            checkpoint = {
                "checkpoint_at": isoformat(now),
                "reason": reason,
                "phase": phase or dict(run_state.metadata_json).get("runtime_phase", "unknown"),
                "status": run_state.status,
                "last_tick_no": run_state.last_tick_no,
                "last_public_message_at": isoformat(run_state.last_public_message_at)
                if run_state.last_public_message_at
                else None,
                "scene": {
                    "scene_key": scene.scene_key if scene else None,
                    "objective": scene.objective[:200] if scene else None,
                    "active_character_slugs": scene.active_character_slugs if scene else [],
                    "emotional_temperature": scene.emotional_temperature if scene else None,
                },
                "world": {
                    "title": world.title if world else None,
                    "active_scene_key": world.active_scene_key if world else None,
                    "current_story_day": world.current_story_day if world else None,
                    "unresolved_questions": world.unresolved_questions[:8] if world else [],
                },
                "latest_directive": {
                    "id": latest_directive.id if latest_directive else None,
                    "tick_no": latest_directive.tick_no if latest_directive else None,
                    "objective": latest_directive.objective[:200] if latest_directive else None,
                    "active_character_slugs": latest_directive.active_character_slugs
                    if latest_directive
                    else [],
                },
                "latest_message": {
                    "id": latest_message.id if latest_message else None,
                    "tick_no": latest_message.tick_no if latest_message else None,
                    "speaker_slug": latest_message.speaker_slug if latest_message else None,
                    "created_at": isoformat(latest_message.created_at) if latest_message else None,
                },
            }
            metadata = dict(run_state.metadata_json)
            metadata["checkpoint"] = checkpoint
            metadata["last_checkpoint_reason"] = reason
            if phase is not None:
                metadata["runtime_phase"] = phase
            run_state.metadata_json = metadata
            run_state.last_checkpoint_at = now
            return checkpoint

    def record_ops_telemetry(
        self,
        *,
        snapshot: OpsTelemetrySnapshot,
        now=None,
    ) -> OpsTelemetrySnapshot:
        now = ensure_utc(now or utcnow())
        try:
            with self.session_factory.session_scope() as session:
                row = models.OpsTelemetry(
                    runtime_status=snapshot.runtime_status,
                    phase=snapshot.phase,
                    degraded_mode=snapshot.degraded_mode,
                    load_tier=snapshot.load_tier,
                    average_latency_ms=snapshot.average_latency_ms,
                    checkpoint_age_seconds=snapshot.checkpoint_age_seconds,
                    recap_age_minutes=snapshot.recap_age_minutes,
                    strategy_age_minutes=snapshot.strategy_age_minutes,
                    drift_risk=snapshot.drift_risk,
                    progression_contract_open=snapshot.progression_contract_open,
                    restart_count=snapshot.restart_count,
                    active_strategy=snapshot.active_strategy,
                    auto_remediations=snapshot.auto_remediations,
                    metadata_json=snapshot.metadata,
                    created_at=now,
                )
                session.add(row)
                session.flush()
                return snapshot.model_copy(update={"created_at": now})
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.record_ops_telemetry",
                exc,
                context={"load_tier": snapshot.load_tier, "phase": snapshot.phase},
                expected_inputs=["A migrated ops_telemetry table."],
                retry_advice="Run migrations so ops telemetry persistence can resume.",
                fallback_used="return-unpersisted-ops-snapshot",
            )
            return snapshot.model_copy(update={"created_at": now})

    def get_latest_ops_telemetry(self) -> OpsTelemetrySnapshot | None:
        try:
            with self.session_factory.session_scope() as session:
                row = session.scalar(
                    select(models.OpsTelemetry).order_by(desc(models.OpsTelemetry.created_at))
                )
                if row is None:
                    return None
                return OpsTelemetrySnapshot(
                    runtime_status=row.runtime_status,
                    phase=row.phase,
                    degraded_mode=row.degraded_mode,
                    load_tier=row.load_tier,
                    average_latency_ms=row.average_latency_ms,
                    checkpoint_age_seconds=row.checkpoint_age_seconds,
                    recap_age_minutes=row.recap_age_minutes,
                    strategy_age_minutes=row.strategy_age_minutes,
                    drift_risk=row.drift_risk,
                    progression_contract_open=row.progression_contract_open,
                    restart_count=row.restart_count,
                    active_strategy=row.active_strategy,
                    auto_remediations=row.auto_remediations,
                    metadata=row.metadata_json,
                    created_at=row.created_at,
                )
        except SQLAlchemyError as exc:
            _log_recovered_db_failure(
                "repository.get_latest_ops_telemetry",
                exc,
                context={},
                expected_inputs=["A migrated ops_telemetry table."],
                retry_advice="Run migrations so ops telemetry reads can resume.",
                fallback_used="no-ops-telemetry",
            )
            return None

    def _get_run_state_model(self, session) -> models.RunState:
        run_state = session.scalar(
            select(models.RunState).where(models.RunState.runtime_key == "primary")
        )
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
        *,
        archived_threads: list[str] | None = None,
    ) -> None:
        if not new_questions and not answered_questions and not archived_threads:
            return
        world = session.scalar(select(models.WorldState).order_by(desc(models.WorldState.id)))
        if world is None:
            return
        existing = list(world.unresolved_questions or [])
        archive = list(world.archived_threads or [])
        existing_index = {_normalize_memory_item(item): item for item in existing}

        for question in new_questions:
            normalized = _normalize_memory_item(question)
            if not normalized or normalized in existing_index:
                continue
            existing.append(question)
            existing_index[normalized] = question

        answered = {_normalize_memory_item(item) for item in answered_questions}
        if answered:
            existing = [
                question
                for question in existing
                if _normalize_memory_item(question) not in answered
            ]

        if len(existing) > _MAX_UNRESOLVED_QUESTIONS:
            overflow = existing[:-_MAX_UNRESOLVED_QUESTIONS]
            archive = _merge_memory_lists(archive, overflow, limit=_MAX_ARCHIVED_THREADS)
            existing = existing[-_MAX_UNRESOLVED_QUESTIONS:]

        archive = _merge_memory_lists(
            archive,
            archived_threads or [],
            limit=_MAX_ARCHIVED_THREADS,
        )
        world.unresolved_questions = existing
        world.archived_threads = archive

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
            "last_checkpoint_at": row.last_checkpoint_at,
            "last_public_message_at": row.last_public_message_at,
            "last_manager_run_at": row.last_manager_run_at,
            "last_recap_hour": row.last_recap_hour,
            "last_thought_pulse_at": row.last_thought_pulse_at,
            "degraded_mode": row.degraded_mode,
            "metadata": dict(row.metadata_json),
        }

    def _relationship_index(self, session) -> dict[tuple[int, int], models.Relationship]:
        lookup: dict[tuple[int, int], models.Relationship] = {}
        for relationship in session.scalars(select(models.Relationship)).all():
            key = tuple(sorted((relationship.character_a_id, relationship.character_b_id)))
            lookup[key] = relationship
        return lookup

    @staticmethod
    def _build_relationship(*, pair_key: tuple[int, int], summary: str, now) -> models.Relationship:
        return models.Relationship(
            character_a_id=pair_key[0],
            character_b_id=pair_key[1],
            trust_score=0,
            desire_score=0,
            suspicion_score=0,
            obligation_score=0,
            summary=summary,
            last_shift_at=now,
        )

    def _get_latest_strategic_brief_id(self, session) -> int | None:
        return session.scalar(
            select(models.StrategicBrief.id).order_by(desc(models.StrategicBrief.created_at))
        )


def _clamp(value: int, minimum: int = -10, maximum: int = 10) -> int:
    return max(minimum, min(maximum, value))


def _int_or_default(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_memory_item(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9 ]+", " ", value.lower())
    return " ".join(normalized.split())


def _merge_memory_lists(existing: list[str], additions: list[str], *, limit: int) -> list[str]:
    merged = list(existing)
    seen = {_normalize_memory_item(item) for item in merged}
    for item in additions:
        normalized = _normalize_memory_item(item)
        if not normalized or normalized in seen:
            continue
        merged.append(item)
        seen.add(normalized)
    if len(merged) > limit:
        merged = merged[-limit:]
    return merged


def _deep_merge_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
            continue
        merged[key] = value
    return merged


def _parse_optional_timestamp(value: str | None, *, default):
    if not value:
        return default
    try:
        return ensure_utc(datetime.fromisoformat(value))
    except ValueError:
        return default


def _stringy(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _compact_reason(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())[:180]


def _classify_rollout_request(text: str) -> str:
    lowered = text.lower()
    if " and " in lowered and any(
        marker in lowered for marker in ("love", "hate", "baby", "marry", "breakup", "jealous")
    ):
        return "relationship"
    if "location" in lowered or "room" in lowered or "wing" in lowered:
        return "location"
    if "character" in lowered or "resident" in lowered or "guest" in lowered:
        return "character"
    if any(marker in lowered for marker in ("mystery", "clue", "evidence", "ledger", "key")):
        return "mystery"
    return "story"


def _estimate_betrayal_value(turn: CharacterTurn) -> int:
    suspicion_weight = sum(max(0, delta.suspicion_delta) for delta in turn.relationship_updates)
    accusation = "?" in turn.public_message and any(
        marker in turn.public_message.lower() for marker in ("why", "who", "lied", "hiding")
    )
    return _clamp(4 + suspicion_weight + int(accusation), 0, 10)


def _estimate_romance_intensity(turn: CharacterTurn) -> int:
    desire_weight = sum(max(0, delta.desire_delta) for delta in turn.relationship_updates)
    marker_hit = any(
        marker in turn.public_message.lower()
        for marker in ("stay", "don't go", "look at me", "with me", "jealous")
    )
    return _clamp(3 + desire_weight + int(marker_hit), 0, 10)


def _estimate_mystery_progression(turn: CharacterTurn) -> int:
    clue_events = sum(
        1
        for event in turn.event_candidates
        if event.event_type.value in {"clue", "reveal", "question"}
    )
    return _clamp(3 + clue_events * 2 + len(turn.new_questions), 0, 10)


def _estimate_daily_uniqueness(turn: CharacterTurn, report: TurnCriticReport) -> int:
    specificity = int(any(char.isdigit() for char in turn.public_message)) + int(
        any(token in turn.public_message.lower() for token in ("ledger", "key", "boiler", "roof"))
    )
    return _clamp(report.novelty + specificity, 0, 10)


def _build_fandom_signals(
    *,
    speaker_slug: str,
    turn: CharacterTurn,
    report: TurnCriticReport,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    if turn.new_questions:
        signals.append(
            {
                "signal_type": "theory",
                "subject": speaker_slug,
                "intensity": _clamp(5 + len(turn.new_questions), 1, 10),
                "rationale": turn.new_questions[0][:180],
                "metadata": {"questions": turn.new_questions[:3]},
            }
        )
    ship_targets = [
        delta.character_slug for delta in turn.relationship_updates if delta.desire_delta > 0
    ]
    if ship_targets:
        signals.append(
            {
                "signal_type": "ship",
                "subject": f"{speaker_slug}<->{ship_targets[0]}",
                "intensity": _clamp(report.fandom_discussion_value, 1, 10),
                "rationale": "The turn moved romantic tension in a visible way.",
                "metadata": {"targets": ship_targets[:3]},
            }
        )
    if report.quote_worthiness >= 7:
        signals.append(
            {
                "signal_type": "quote",
                "subject": speaker_slug,
                "intensity": report.quote_worthiness,
                "rationale": turn.public_message[:180],
                "metadata": {"message": turn.public_message[:180]},
            }
        )
    if any(delta.suspicion_delta > 0 for delta in turn.relationship_updates):
        signals.append(
            {
                "signal_type": "betrayal-watch",
                "subject": speaker_slug,
                "intensity": _clamp(report.clip_value, 1, 10),
                "rationale": "Suspicion rose enough to trigger betrayal discussion.",
                "metadata": {
                    "counterparts": [
                        delta.character_slug
                        for delta in turn.relationship_updates
                        if delta.suspicion_delta > 0
                    ][:3]
                },
            }
        )
    return signals[:3]


def _effective_beat_status(status: str, *, due_by, now) -> str:
    if status == "planned" and (due_by is None or due_by <= now):
        return "ready"
    return status


def _beat_sort_key(beat: BeatSnapshot, *, now) -> tuple[int, datetime, int, int]:
    status = _effective_beat_status(beat.status, due_by=beat.due_by, now=now)
    status_priority = {"active": 0, "ready": 1, "planned": 2}.get(status, 3)
    due_by = ensure_utc(beat.due_by) if beat.due_by else datetime.max.replace(tzinfo=now.tzinfo)
    return (status_priority, due_by, -beat.significance, beat.id or 0)


def _log_recovered_db_failure(
    operation: str,
    error: Exception,
    *,
    context: dict[str, Any],
    expected_inputs: list[str],
    retry_advice: str,
    fallback_used: str,
) -> None:
    logger.error(
        "Recovered database-layer failure: %s",
        error,
        extra={
            "operation": operation,
            "recoverable": True,
            "expected_inputs": expected_inputs,
            "retry_advice": retry_advice,
            "context": context,
            "fallback_used": fallback_used,
            "exception_type": type(error).__name__,
        },
    )
