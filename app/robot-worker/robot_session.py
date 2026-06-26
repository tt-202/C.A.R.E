"""In-memory feed session state (mirrors New_Settings_June26 controller)."""

from __future__ import annotations

import threading

_lock = threading.Lock()
apriltag_scan_completed = False
selected_plate_section = 1
feeding_active = False


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
    global feeding_active, selected_plate_section
    with _lock:
        feeding_active = True
        if section is not None:
            selected_plate_section = max(1, min(4, int(section)))
        return selected_plate_section


def end_feed_cycle() -> None:
    global feeding_active
    with _lock:
        feeding_active = False


def is_feeding_active() -> bool:
    with _lock:
        return feeding_active
