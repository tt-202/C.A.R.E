"""In-memory bite counter for the current feeding session."""

from __future__ import annotations


class BiteCounter:
    def __init__(self) -> None:
        self.total = 0
        self.by_section: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0}

    def increment(self, section: int = 1) -> int:
        self.total += 1
        self.by_section[section] = self.by_section.get(section, 0) + 1
        return self.total

    def reset(self) -> None:
        self.total = 0
        self.by_section = {1: 0, 2: 0, 3: 0, 4: 0}
