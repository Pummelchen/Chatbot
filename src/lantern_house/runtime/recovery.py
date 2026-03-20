from __future__ import annotations

from lantern_house.db.repository import StoryRepository
from lantern_house.utils.time import utcnow


class RecoveryService:
    def __init__(self, repository: StoryRepository) -> None:
        self.repository = repository

    def recover(self) -> dict:
        run_state = self.repository.ensure_run_state()
        missed_recap_hours = self.repository.list_missing_recap_hours(now=utcnow())
        return {
            "run_state": run_state,
            "missed_recap_hours": missed_recap_hours,
        }

