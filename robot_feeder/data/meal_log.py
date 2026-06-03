"""Simple session log (extend to sync with care-app Postgres if needed)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class MealLogEntry:
    started_at: str
    ended_at: str | None
    bites_total: int
    planned_slot: str


class MealLog:
    def __init__(self, path: str = "data/meal_sessions.jsonl") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._current: MealLogEntry | None = None

    def start(self, planned_slot: str) -> None:
        self._current = MealLogEntry(
            started_at=datetime.now(timezone.utc).isoformat(),
            ended_at=None,
            bites_total=0,
            planned_slot=planned_slot,
        )

    def add_bite(self, total: int) -> None:
        if self._current:
            self._current.bites_total = total

    def end(self) -> None:
        if not self._current:
            return
        self._current.ended_at = datetime.now(timezone.utc).isoformat()
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(self._current)) + "\n")
        logger.info("Meal logged: %s bites", self._current.bites_total)
        self._current = None
