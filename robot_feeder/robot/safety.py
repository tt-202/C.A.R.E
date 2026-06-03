"""Safety limits and pre-motion checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SafetyLimits:
    min_tof_mm: int = 80
    max_tof_mm: int = 400
    max_joint_delta_deg: float = 45.0


class SafetyMonitor:
    def __init__(self, limits: SafetyLimits | None = None) -> None:
        self.limits = limits or SafetyLimits()

    def tof_ok(self, distance_mm: int | None) -> bool:
        if distance_mm is None:
            return False
        return self.limits.min_tof_mm <= distance_mm <= self.limits.max_tof_mm

    def mouth_alignment_ok(self, offset_x: float, offset_y: float, *, max_offset: float = 0.15) -> bool:
        return abs(offset_x) <= max_offset and abs(offset_y) <= max_offset
