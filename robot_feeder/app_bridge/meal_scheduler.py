"""Optional local meal-time hints (breakfast/lunch/dinner) for on-device logging."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time


@dataclass
class MealSlot:
    label: str
    at: time


def parse_hhmm(value: str, default: time) -> time:
    try:
        h, m = value.strip().split(":", 1)
        return time(hour=int(h), minute=int(m))
    except (ValueError, AttributeError):
        return default


class MealScheduler:
    def __init__(
        self,
        *,
        breakfast: str = "08:00",
        lunch: str = "12:30",
        dinner: str = "18:00",
    ) -> None:
        self.slots = [
            MealSlot("Breakfast", parse_hhmm(breakfast, time(8, 0))),
            MealSlot("Lunch", parse_hhmm(lunch, time(12, 30))),
            MealSlot("Dinner", parse_hhmm(dinner, time(18, 0))),
        ]

    def active_slot(self, now: datetime | None = None) -> MealSlot:
        now = now or datetime.now()
        current = now.time()
        best = self.slots[0]
        for slot in self.slots:
            if current >= slot.at:
                best = slot
        return best
