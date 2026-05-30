"""Execute allowlisted commands on myCobot 320. Replace stubs with real pymycobot motion."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

ALLOWED = frozenset({"home", "next_bite", "pause", "stop"})


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() in ("1", "true", "yes")


def _get_arm():
    """Return pymycobot instance when available."""
    port = os.environ.get("MYCOBOT_PORT", "/dev/ttyUSB0")
    baud = int(os.environ.get("MYCOBOT_BAUD", "115200"))
    try:
        from pymycobot.mycobot320 import MyCobot320  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("pymycobot not installed; pip install pymycobot or set DRY_RUN=true") from e
    return MyCobot320(port, baud)


def execute_command(cmd: str, payload: dict[str, Any] | None) -> None:
    if cmd not in ALLOWED:
        raise ValueError(f"unsupported cmd: {cmd}")

    if _dry_run():
        logger.info("DRY_RUN cmd=%s payload=%s", cmd, payload)
        time.sleep(0.3)
        return

    arm = _get_arm()
    if cmd == "home":
        arm.send_angles([0, 0, 0, 0, 0, 0], 40)
    elif cmd == "pause" or cmd == "stop":
        arm.stop()
    elif cmd == "next_bite":
        # TODO: replace with your feeding trajectory (joint angles / coords).
        section = (payload or {}).get("sectionNum", 1)
        logger.info("next_bite section=%s — using placeholder motion", section)
        arm.send_angles([0, -20, 40, 0, 0, 0], 35)
        time.sleep(1.0)
        arm.send_angles([0, 0, 0, 0, 0, 0], 35)
    else:
        raise ValueError(f"unhandled cmd: {cmd}")
