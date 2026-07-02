"""
LCD GUI subprocess bridge (New_Settings_June26/main_controller_phase4.py).

Starts lcd_display.py with --stdin and sends JSON state updates.
The GUI does not read GPIO; worker.py owns buttons and motion.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from robot_session import get_selected_section

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
GUI_PROCESS_FILE = ROOT_DIR / "lcd_display.py"

GUI_MESSAGES = {
    "startup": "Jetson controller starting",
    "ready_needs_scan": "Press SELECT once to scan plate position",
    "ready": "System ready. Press SELECT or FEED.",
    "apriltag_scan_start": "Scanning AprilTags for plate position",
    "apriltag_scan_success": "Plate position saved. SELECT now changes food section.",
    "apriltag_scan_failed": "AprilTag scan failed. Press SELECT to retry.",
    "select_section": "Selected plate section {section}",
    "feed_blocked_no_scan": "Press SELECT once before FEED to scan plate position",
    "feed_start": "Feed pressed. Using selected section {section}",
    "scoop_start": "Scooping from plate section {section}",
    "scoop_success": "Scoop complete. Checking spoon before feeding.",
    "scoop_failed": "Scoop failed for section {section}",
    "plate_check_start": "Checking whole plate for food",
    "plate_full": "Food detected on plate. Feed is allowed.",
    "plate_empty": "Plate looks empty. Refill, then press FEED to recheck.",
    "plate_unknown": "Plate check unclear. Press FEED to recheck.",
    "spoon_check_start": "Checking spoon after scoop",
    "spoon_full": "Food detected on spoon. Starting mouth detection.",
    "spoon_empty": "Spoon appears empty. Press FEED again to retry scoop.",
    "spoon_unknown": "Spoon check unclear. Press FEED to retry or check camera view.",
    "spoon_failed_limit": "Three failed scoops. Check food position or select another section.",
    "select_during_feed": "SELECT ignored during feeding. Finish bite or press emergency.",
    "feed_hold_at_mouth": "Bite ready. Holding still for {seconds} sec",
    "feed_return_home": "Bite complete. Returning to default position.",
    "feed_end": "Feeding phase ended. SELECT available again.",
    "emergency_active": "Emergency stop active: {reason}",
    "emergency_wait": "Emergency stop. Arm holding still for {seconds} sec",
    "emergency_returning_home": "Emergency hold complete. Returning arm to home",
    "emergency_release": "Release emergency button when safe",
    "emergency_recovered": "Emergency recovered. System ready.",
}

_gui_process: subprocess.Popen[str] | None = None
_gui_send_lock = threading.Lock()
_last_gui_payload: dict | None = None
_last_gui_update_time = 0.0
GUI_MIN_UPDATE_PERIOD = 0.50


def _gui_enabled() -> bool:
    raw = os.environ.get("LCD_GUI_ENABLED")
    if raw is None:
        return bool(os.environ.get("DISPLAY"))
    return raw.strip().lower() in ("1", "true", "yes", "on")


def start_gui_process() -> None:
    global _gui_process

    if not _gui_enabled():
        logger.info("[GUI] LCD GUI disabled (LCD_GUI_ENABLED=false or no DISPLAY)")
        return

    if _gui_process is not None:
        return

    if not GUI_PROCESS_FILE.exists():
        logger.warning("[GUI] Missing %s — running without LCD GUI", GUI_PROCESS_FILE)
        return

    try:
        _gui_process = subprocess.Popen(
            [sys.executable, str(GUI_PROCESS_FILE), "--stdin"],
            stdin=subprocess.PIPE,
            stdout=None,
            stderr=None,
            text=True,
            bufsize=1,
            cwd=str(ROOT_DIR),
        )
        logger.info("[GUI] Started LCD GUI: %s", GUI_PROCESS_FILE)
    except Exception as e:
        _gui_process = None
        logger.warning("[GUI] Could not start LCD GUI: %s", e)


def _send_gui_payload(payload: dict) -> None:
    global _gui_process

    if _gui_process is None:
        return

    if _gui_process.poll() is not None:
        logger.warning("[GUI] GUI process exited — disabling GUI updates")
        _gui_process = None
        return

    if _gui_process.stdin is None:
        return

    try:
        with _gui_send_lock:
            _gui_process.stdin.write(json.dumps(payload) + "\n")
            _gui_process.stdin.flush()
    except Exception as e:
        logger.warning("[GUI] Could not send GUI update: %s", e)
        _gui_process = None


def update_gui_state(
    state: str,
    message: str | None = None,
    *,
    emergency: bool = False,
    selected_plate_section: int | None = None,
    connected: bool | None = None,
    error: str | None = None,
    force: bool = False,
) -> None:
    global _last_gui_payload, _last_gui_update_time

    if not _gui_enabled() and _gui_process is None:
        return

    section = (
        int(selected_plate_section)
        if selected_plate_section is not None
        else get_selected_section()
    )

    payload: dict = {
        "state": state,
        "message": message if message is not None else state,
        "emergency": bool(emergency),
        "selected_section": section,
    }

    if connected is not None:
        payload["connected"] = bool(connected)

    if error is not None:
        payload["error"] = error

    now = time.time()
    if (
        not force
        and payload == _last_gui_payload
        and (now - _last_gui_update_time) < GUI_MIN_UPDATE_PERIOD
    ):
        return

    _last_gui_payload = payload
    _last_gui_update_time = now
    logger.debug("[GUI_STATE] %s", payload)
    _send_gui_payload(payload)


def stop_gui_process() -> None:
    global _gui_process

    if _gui_process is None:
        return

    try:
        update_gui_state(
            "shutdown",
            "Jetson controller shutting down",
            selected_plate_section=get_selected_section(),
            connected=False,
            force=True,
        )
        time.sleep(0.2)
    except Exception:
        pass

    try:
        _gui_process.terminate()
        _gui_process.wait(timeout=2.0)
    except Exception:
        try:
            _gui_process.kill()
        except Exception:
            pass

    _gui_process = None
