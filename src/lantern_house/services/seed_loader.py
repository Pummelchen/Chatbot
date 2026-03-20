from __future__ import annotations

from sqlalchemy import select

from lantern_house.db import models
from lantern_house.db.session import SessionFactory
from lantern_house.utils.resources import load_yaml
from lantern_house.utils.time import floor_to_hour, utcnow


class StorySeedLoader:
    def __init__(self, session_factory: SessionFactory) -> None:
        self.session_factory = session_factory

    def load_seed_payload(self) -> dict:
        return load_yaml("lantern_house.seeds", "story_bible.yaml")

    def seed_database(self, *, force: bool = False) -> None:
        payload = self.load_seed_payload()
        with self.session_factory.session_scope() as session:
            existing = session.scalar(select(models.Character.id).limit(1))
            if existing is not None and not force:
                self._validate_existing_seed(session, payload)
                return
            if existing is not None and force:
                raise RuntimeError(
                    "Force reseed is not implemented to avoid accidental canon loss."
                )

            location_map: dict[str, models.Location] = {}
            for item in payload["locations"]:
                row = models.Location(
                    slug=item["slug"],
                    name=item["name"],
                    description=item["description"],
                    public_facts=item.get("public_facts", []),
                )
                session.add(row)
                session.flush()
                location_map[item["slug"]] = row

            character_map: dict[str, models.Character] = {}
            for item in payload["characters"]:
                row = models.Character(
                    slug=item["slug"],
                    full_name=item["full_name"],
                    cultural_background=item["background"],
                    public_persona=item["public_persona"],
                    hidden_wound=item["hidden_wound"],
                    long_term_desire=item["long_term_desire"],
                    private_fear=item["private_fear"],
                    family_expectations=item["family_expectations"],
                    conflict_style=item["conflict_style"],
                    privacy_boundaries=item["privacy_boundaries"],
                    value_instincts=item["value_instincts"],
                    emotional_expression=item["emotional_expression"],
                    message_style=item["message_style"],
                    ensemble_role=item["ensemble_role"],
                    secrets_summary=item["secrets_summary"],
                    humor_style=item["humor_style"],
                    color=item["color"],
                )
                session.add(row)
                session.flush()
                character_map[item["slug"]] = row
                session.add(
                    models.CharacterState(
                        character_id=row.id,
                        current_location_id=location_map[item["current_location_slug"]].id,
                        emotional_state=item["emotional_state"],
                        active_goals=item["active_goals"],
                        stress_level=4,
                        romance_heat=4,
                    )
                )

            for item in payload["objects"]:
                session.add(
                    models.StoryObject(
                        slug=item["slug"],
                        name=item["name"],
                        description=item["description"],
                        location_id=location_map[item["location_slug"]].id,
                        significance=item["significance"],
                    )
                )

            for item in payload["canon_facts"]:
                session.add(
                    models.CanonFact(
                        fact_key=item["key"],
                        fact_type=item["type"],
                        content=item["content"],
                        visibility=item["visibility"],
                        source="story-bible",
                    )
                )

            for item in payload["relationships"]:
                a = character_map[item["a"]]
                b = character_map[item["b"]]
                ordered = sorted((a.id, b.id))
                session.add(
                    models.Relationship(
                        character_a_id=ordered[0],
                        character_b_id=ordered[1],
                        trust_score=item["trust"],
                        desire_score=item["desire"],
                        suspicion_score=item["suspicion"],
                        obligation_score=item["obligation"],
                        summary=item["summary"],
                    )
                )

            for item in payload["secrets"]:
                holder = character_map.get(item.get("holder")) if item.get("holder") else None
                session.add(
                    models.Secret(
                        slug=item["slug"],
                        title=item["title"],
                        holder_character_id=holder.id if holder else None,
                        secret_type=item["type"],
                        description=item["description"],
                        exposure_stage=item["exposure_stage"],
                        reveal_guardrail=item["reveal_guardrail"],
                        is_public=False,
                    )
                )

            for item in payload["story_arcs"]:
                session.add(
                    models.StoryArc(
                        slug=item["slug"],
                        title=item["title"],
                        status=item["status"],
                        arc_type=item["arc_type"],
                        summary=item["summary"],
                        stage_index=item["stage_index"],
                        reveal_ladder=item["reveal_ladder"],
                        unresolved_questions=item["unresolved_questions"],
                        payoff_window=item["payoff_window"],
                        pressure_score=item["pressure_score"],
                    )
                )

            hour_bucket = floor_to_hour(utcnow())
            session.add(
                models.WorldState(
                    title=payload["title"],
                    active_scene_key=payload["initial_scene"]["scene_key"],
                    current_story_day=1,
                    emotional_temperature=payload["initial_scene"]["emotional_temperature"],
                    reveal_pressure=1,
                    unresolved_questions=[
                        payload["story_arcs"][0]["unresolved_questions"][0],
                        payload["story_arcs"][1]["unresolved_questions"][0],
                        payload["story_arcs"][2]["unresolved_questions"][0],
                    ],
                    archived_threads=payload["future_plot_hooks"][:6],
                    metadata_json={
                        "setting": payload["setting"],
                        "initial_trust_map": payload["initial_trust_map"],
                        "initial_romantic_tensions": payload["initial_romantic_tensions"],
                        "first_week_arc_plan": payload["first_week_arc_plan"],
                        "first_24h_drama_plan": payload["first_24h_drama_plan"],
                        "future_plot_hooks": payload["future_plot_hooks"],
                        "story_engine": payload.get("story_engine", {}),
                        "future_recurring_character": payload.get("future_recurring_character"),
                        "recap_examples": payload["recap_examples"],
                    },
                )
            )

            scene = payload["initial_scene"]
            session.add(
                models.SceneState(
                    scene_key=scene["scene_key"],
                    objective=scene["objective"],
                    emotional_temperature=scene["emotional_temperature"],
                    mystery_pressure=scene["mystery_pressure"],
                    romance_pressure=scene["romance_pressure"],
                    comedic_pressure=scene["comedic_pressure"],
                    location_id=location_map[scene["location_slug"]].id,
                    active_character_slugs=scene.get(
                        "active_character_slugs", ["amelia", "rafael", "ayu"]
                    ),
                    current_hour_bucket=hour_bucket,
                )
            )

            run_state = session.scalar(
                select(models.RunState).where(models.RunState.runtime_key == "primary")
            )
            if run_state is None:
                session.add(
                    models.RunState(
                        runtime_key="primary",
                        status="idle",
                        metadata_json={"seed_title": payload["title"]},
                    )
                )
            else:
                run_state.status = "idle"
                run_state.last_tick_no = 0
                run_state.last_checkpoint_at = None
                run_state.last_public_message_at = None
                run_state.last_manager_run_at = None
                run_state.last_recap_hour = None
                run_state.last_thought_pulse_at = None
                run_state.degraded_mode = False
                metadata = dict(run_state.metadata_json)
                metadata["seed_title"] = payload["title"]
                metadata.pop("checkpoint", None)
                metadata.pop("last_checkpoint_reason", None)
                metadata.pop("last_start_at", None)
                metadata["runtime_phase"] = "seeded"
                run_state.metadata_json = metadata

    def _validate_existing_seed(self, session, payload: dict) -> None:
        required_models = {
            "world_state": models.WorldState,
            "scene_state": models.SceneState,
            "run_state": models.RunState,
        }
        missing = [
            name
            for name, model in required_models.items()
            if session.scalar(select(model.id).limit(1)) is None
        ]
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(
                f"Existing character seed is incomplete; missing required state tables: {joined}. "
                "Reset the database or repair the seed before continuing."
            )
        run_state = session.scalar(
            select(models.RunState).where(models.RunState.runtime_key == "primary")
        )
        metadata = dict(run_state.metadata_json) if run_state is not None else {}
        existing_title = metadata.get("seed_title")
        if existing_title and existing_title != payload["title"]:
            raise RuntimeError(
                "Existing database is seeded with a different story bible title. "
                "Reset the database and reseed to load the current ensemble and canon."
            )
