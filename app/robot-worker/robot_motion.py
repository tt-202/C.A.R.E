"""Execute allowlisted commands via the full feeding cycle (Jetson → Pi TCP)."""

from __future__ import annotations

import logging
from typing import Any

from feeding_cycle import (
    calibrate_plate,
    execute_home,
    execute_next_bite,
    execute_stop,
)

logger = logging.getLogger(__name__)

ALLOWED = frozenset({"home", "next_bite", "pause", "stop", "calibrate_plate"})


def execute_command(cmd: str, payload: dict[str, Any] | None) -> None:
    if cmd not in ALLOWED:
        raise ValueError(f"unsupported cmd: {cmd}")

    if cmd == "home":
        execute_home()
        return

    if cmd in ("pause", "stop"):
        execute_stop()
        return

    if cmd == "calibrate_plate":
        calibrate_plate(preview=False)
        return

    if cmd == "next_bite":
        section = 1
        if isinstance(payload, dict) and isinstance(payload.get("sectionNum"), int):
            section = payload["sectionNum"]
        execute_next_bite(section)
        return

    raise ValueError(f"unhandled cmd: {cmd}")
