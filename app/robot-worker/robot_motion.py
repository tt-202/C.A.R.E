"""Execute allowlisted commands via the full feeding cycle (Jetson → Pi TCP)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from feeding_cycle import (
    calibrate_plate,
    execute_home,
    execute_next_bite,
    execute_stop,
)
from robot_session import is_feeding_active

if TYPE_CHECKING:
    from firebase_admin import firestore

    from gpio_buttons import ButtonManager

logger = logging.getLogger(__name__)

ALLOWED = frozenset({"home", "next_bite", "pause", "stop", "calibrate_plate"})


def execute_command(
    cmd: str,
    payload: dict[str, Any] | None,
    buttons: ButtonManager | None = None,
    *,
    db: firestore.Client | None = None,
    robot_id: str | None = None,
) -> bool:
    if cmd not in ALLOWED:
        raise ValueError(f"unsupported cmd: {cmd}")

    if cmd == "home":
        execute_home()
        return True

    if cmd in ("pause", "stop"):
        execute_stop()
        return False

    if cmd == "calibrate_plate":
        if is_feeding_active():
            logger.warning("calibrate_plate ignored — feed cycle active")
            return False
        calibrate_plate(preview=False, db=db, robot_id=robot_id)
        return True

    if cmd == "next_bite":
        if is_feeding_active():
            logger.warning("next_bite ignored — feed cycle already active")
            return False
        section = 1
        if isinstance(payload, dict) and isinstance(payload.get("sectionNum"), int):
            section = payload["sectionNum"]
        return execute_next_bite(section, buttons=buttons, db=db, robot_id=robot_id)

    raise ValueError(f"unhandled cmd: {cmd}")
