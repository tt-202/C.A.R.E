"""
In-memory feed session state (New_Settings_June26 / README_FEED_STATE_UPDATE).

SELECT stays locked until a feed cycle completes HOME and end_feed_cycle() runs.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_lock = threading.Lock()
apriltag_scan_completed = False
selected_plate_section = 1

system_state = "IDLE"
feed_cycle_state = "END_FEED"
feeding_active = False


def set_system_state(new_state: str, reason: str | None = None) -> None:
    global system_state
    system_state = str(new_state)
    suffix = f" | {reason}" if reason else ""
    logger.info("[SYSTEM_STATE] %s%s", system_state, suffix)


def get_system_state() -> str:
    with _lock:
        return system_state


def get_feed_cycle_state() -> str:
    with _lock:
        return feed_cycle_state


def mark_apriltag_scan_done() -> None:
    global apriltag_scan_completed
    with _lock:
        apriltag_scan_completed = True


def is_apriltag_scan_done() -> bool:
    with _lock:
        return apriltag_scan_completed


def get_selected_section() -> int:
    with _lock:
        return selected_plate_section


def set_selected_section(section: int) -> int:
    global selected_plate_section
    with _lock:
        selected_plate_section = max(1, min(4, int(section)))
        return selected_plate_section


def advance_selected_section() -> int:
    global selected_plate_section
    with _lock:
        selected_plate_section = (selected_plate_section % 4) + 1
        return selected_plate_section


def start_feed_cycle(section: int | None = None) -> int:
    """Lock SELECT until end_feed_cycle() after confirmed HOME."""
    global feeding_active, feed_cycle_state, selected_plate_section
    with _lock:
        feeding_active = True
        feed_cycle_state = "START_FEED"
        if section is not None:
            selected_plate_section = max(1, min(4, int(section)))
        active_section = selected_plate_section
    set_system_state("FEEDING_STARTED", f"section={active_section}")
    logger.info("[FEED_CYCLE] START_FEED | section=%s", active_section)
    return active_section


def end_feed_cycle(reason: str = "FEED_COMPLETE") -> None:
    """Unlock SELECT/FEED only after arm has returned home."""
    global feeding_active, feed_cycle_state
    with _lock:
        feeding_active = False
        feed_cycle_state = "END_FEED"
    set_system_state("IDLE", reason)
    logger.info("[FEED_CYCLE] END_FEED | reason=%s", reason)


def mark_emergency_state(reason: str) -> None:
    global feeding_active, feed_cycle_state
    with _lock:
        feeding_active = False
        feed_cycle_state = "EMERGENCY"
    set_system_state("EMERGENCY", reason)
    logger.info("[FEED_CYCLE] EMERGENCY | reason=%s", reason)


def is_feeding_active() -> bool:
    with _lock:
        return feeding_active
