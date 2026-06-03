"""Time-of-flight distance sensor (stub — wire to your I2C/GPIO driver)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class TOFSensor:
    def __init__(self) -> None:
        self._mock_mm = int(os.environ.get("TOF_MOCK_MM", "200"))

    def read_distance_mm(self) -> int | None:
        # Replace with VL53L0X / similar driver on Jetson.
        return self._mock_mm
