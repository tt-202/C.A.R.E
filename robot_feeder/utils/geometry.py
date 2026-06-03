"""Small geometry helpers for alignment and safety checks."""

from __future__ import annotations

import math
from typing import Sequence


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def distance_2d(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def within_box(
    point: Sequence[float],
    *,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
) -> bool:
    x, y = point[0], point[1]
    return xmin <= x <= xmax and ymin <= y <= ymax
