# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from lantern_house.config import ChronologyGraphConfig
from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import ChronologyEdgeSnapshot, ChronologyNodeSnapshot
from lantern_house.utils.time import ensure_utc, utcnow


class ChronologyGraphService:
    def __init__(self, repository: StoryRepository, config: ChronologyGraphConfig) -> None:
        self.repository = repository
        self.config = config

    def refresh(self, *, now=None, force: bool = False) -> list[ChronologyEdgeSnapshot]:
        now = ensure_utc(now or utcnow())
        existing = self.repository.list_recent_chronology_edges(limit=1)
        if (
            not force
            and not self.config.enabled
            and existing
        ):
            return self.repository.list_recent_chronology_edges(
                limit=self.config.max_digest_edges
            )
        if (
            not force
            and existing
            and existing[0].updated_at
            and now - ensure_utc(existing[0].updated_at)
            < timedelta(minutes=max(1, self.config.refresh_interval_minutes))
        ):
            return self.repository.list_recent_chronology_edges(
                limit=self.config.max_digest_edges
            )

        positions = self.repository.list_character_positions()
        possessions = self.repository.list_object_possessions(limit=12)
        facts = self.repository.list_recent_timeline_facts(
            hours=self.config.recent_fact_hours,
            limit=36,
        )
        house_state = self.repository.get_house_state_snapshot()

        nodes: dict[str, ChronologyNodeSnapshot] = {}
        edges: list[ChronologyEdgeSnapshot] = []

        def upsert_node(node_key: str, node_type: str, label: str, **metadata) -> None:
            nodes[node_key] = ChronologyNodeSnapshot(
                node_key=node_key,
                node_type=node_type,
                label=label[:180],
                metadata=metadata,
                updated_at=now,
            )

        for item in positions:
            character_key = f"character:{item['slug']}"
            location_key = _location_key(item.get("location_slug"), item.get("location_name"))
            upsert_node(character_key, "character", item["full_name"], slug=item["slug"])
            if item.get("location_name"):
                upsert_node(
                    location_key,
                    "location",
                    item["location_name"],
                    location_slug=item.get("location_slug"),
                )
                edges.append(
                    ChronologyEdgeSnapshot(
                        subject_key=character_key,
                        predicate="currently-in",
                        object_key=location_key,
                        confidence=9,
                        supporting_text=(
                            f"{item['full_name']} is currently grounded in "
                            f"{item['location_name']}."
                        ),
                        source="world-tracking",
                        metadata={"kind": "position"},
                        created_at=now,
                        updated_at=now,
                    )
                )

        for item in possessions:
            object_key = f"object:{item.object_slug}"
            upsert_node(object_key, "object", item.object_name, object_slug=item.object_slug)
            if item.holder_character_slug:
                holder_key = f"character:{item.holder_character_slug}"
                upsert_node(holder_key, "character", item.holder_character_slug)
                edges.append(
                    ChronologyEdgeSnapshot(
                        subject_key=object_key,
                        predicate="held-by",
                        object_key=holder_key,
                        confidence=item.confidence,
                        supporting_text=item.summary,
                        source="world-tracking",
                        metadata={"status": item.possession_status},
                        created_at=now,
                        updated_at=now,
                    )
                )
            elif item.location_name:
                location_key = _location_key(item.location_slug, item.location_name)
                upsert_node(
                    location_key,
                    "location",
                    item.location_name,
                    location_slug=item.location_slug,
                )
                edges.append(
                    ChronologyEdgeSnapshot(
                        subject_key=object_key,
                        predicate="stored-in",
                        object_key=location_key,
                        confidence=item.confidence,
                        supporting_text=item.summary,
                        source="world-tracking",
                        metadata={"status": item.possession_status},
                        created_at=now,
                        updated_at=now,
                    )
                )

        for fact in facts:
            subject_key = _subject_key(fact.subject_slug)
            if fact.subject_slug:
                upsert_node(subject_key, "subject", fact.subject_slug, fact_type=fact.fact_type)
            if fact.location_name:
                location_key = _location_key(fact.location_slug, fact.location_name)
                upsert_node(
                    location_key,
                    "location",
                    fact.location_name,
                    location_slug=fact.location_slug,
                )
            else:
                location_key = ""
            if fact.object_name:
                object_key = f"object:{fact.object_slug or _slugify(fact.object_name)}"
                upsert_node(
                    object_key,
                    "object",
                    fact.object_name,
                    object_slug=fact.object_slug,
                )
            else:
                object_key = ""
            predicate = _predicate_for_fact(fact.fact_type)
            target_key = object_key or location_key or _note_key(fact.summary)
            if target_key.startswith("note:"):
                upsert_node(target_key, "note", fact.summary[:180], fact_type=fact.fact_type)
            edges.append(
                ChronologyEdgeSnapshot(
                    subject_key=subject_key,
                    predicate=predicate,
                    object_key=target_key,
                    confidence=fact.confidence,
                    supporting_text=fact.summary,
                    source=fact.source,
                    metadata={"fact_type": fact.fact_type},
                    created_at=now,
                    updated_at=now,
                )
            )

        if 0 < house_state.payroll_due_in_hours <= 72:
            deadline_key = f"deadline:payroll-{house_state.payroll_due_in_hours}h"
            upsert_node(deadline_key, "deadline", f"Payroll in {house_state.payroll_due_in_hours}h")
            edges.append(
                ChronologyEdgeSnapshot(
                    subject_key="house:primary",
                    predicate="deadline",
                    object_key=deadline_key,
                    confidence=9,
                    supporting_text=(
                        f"Payroll is due in {house_state.payroll_due_in_hours} hours."
                    ),
                    source="house-state",
                    metadata={"cash_on_hand": house_state.cash_on_hand},
                    created_at=now,
                    updated_at=now,
                )
            )

        edges = _apply_contradiction_markers(
            edges=edges,
            window_minutes=self.config.contradiction_window_minutes,
        )
        _persisted_nodes, persisted_edges = self.repository.sync_chronology_graph(
            nodes=list(nodes.values()),
            edges=edges,
            now=now,
        )
        return persisted_edges[: self.config.max_digest_edges]


def _predicate_for_fact(fact_type: str) -> str:
    mapping = {
        "presence": "was-in",
        "alibi": "claimed-in",
        "alibi-claim": "placed-in",
        "timeline-question": "questioned",
        "money-deadline": "deadline",
        "repair-state": "repair-pressure",
    }
    return mapping.get(fact_type, fact_type.replace("_", "-"))


def _subject_key(subject_slug: str) -> str:
    if not subject_slug:
        return "house:primary"
    if ":" in subject_slug:
        return subject_slug
    if subject_slug == "house":
        return "house:primary"
    return f"character:{subject_slug}"


def _location_key(location_slug: str | None, location_name: str | None) -> str:
    if location_slug:
        return f"location:{location_slug}"
    return f"location:{_slugify(location_name or 'unknown-location')}"


def _note_key(text: str) -> str:
    return f"note:{_slugify(text)[:40]}"


def _slugify(text: str) -> str:
    compact = "-".join(part for part in "".join(
        char.lower() if char.isalnum() else "-"
        for char in text
    ).split("-") if part)
    return compact or "unknown"


def _apply_contradiction_markers(
    *,
    edges: list[ChronologyEdgeSnapshot],
    window_minutes: int,
) -> list[ChronologyEdgeSnapshot]:
    del window_minutes
    location_targets: dict[str, set[str]] = defaultdict(set)
    possession_targets: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        if edge.predicate in {"currently-in", "was-in", "claimed-in", "placed-in"}:
            location_targets[edge.subject_key].add(edge.object_key)
        if edge.predicate in {"held-by", "stored-in"}:
            possession_targets[edge.subject_key].add(edge.object_key)

    updated: list[ChronologyEdgeSnapshot] = []
    for edge in edges:
        contradiction_status = edge.contradiction_status
        if edge.predicate in {"currently-in", "was-in", "claimed-in", "placed-in"} and (
            len(location_targets[edge.subject_key]) > 1
        ):
            contradiction_status = "contested"
        if edge.predicate in {"held-by", "stored-in"} and (
            len(possession_targets[edge.subject_key]) > 1
        ):
            contradiction_status = "contested"
        updated.append(edge.model_copy(update={"contradiction_status": contradiction_status}))
    return updated
