# Lantern House core instruction: stay fail-safe, never leak debug or
# error text into the live chat, log recovered failures to
# logs/error.txt with context, and preserve hot-patch compatibility
# for uninterrupted long-running operation.
from __future__ import annotations

from lantern_house.db.repository import StoryRepository
from lantern_house.domain.contracts import ContinuityFlagDraft
from lantern_house.domain.enums import FlagSeverity
from lantern_house.utils.time import utcnow


class RecoveryService:
    def __init__(self, repository: StoryRepository) -> None:
        self.repository = repository

    def recover(self) -> dict:
        now = utcnow()
        previous_run_state = self.repository.mark_runtime_starting(now=now)
        previous_metadata = previous_run_state.get("metadata") or {}
        checkpoint = previous_metadata.get("checkpoint")
        previous_status = previous_run_state.get("status")
        unclean_shutdown = previous_status in {"starting", "running"}

        if unclean_shutdown:
            checkpoint_at = (
                checkpoint.get("checkpoint_at") if isinstance(checkpoint, dict) else None
            )
            phase = previous_metadata.get("runtime_phase", "unknown")
            detail = f"Runtime resumed after an unexpected stop while phase '{phase}' was active."
            if checkpoint_at:
                detail += f" Last checkpoint was captured at {checkpoint_at}."
            self.repository.add_continuity_flags(
                [
                    ContinuityFlagDraft(
                        severity=FlagSeverity.WARNING,
                        flag_type="unclean-shutdown",
                        description=detail,
                        related_entity="runtime:primary",
                    )
                ]
            )

        missed_recap_hours = self.repository.list_missing_recap_hours(now=now)
        return {
            "previous_run_state": previous_run_state,
            "unclean_shutdown": unclean_shutdown,
            "checkpoint": checkpoint if isinstance(checkpoint, dict) else None,
            "missed_recap_hours": missed_recap_hours,
        }
