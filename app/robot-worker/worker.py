#!/usr/bin/env python3
"""
Listen for Firestore robot commands and run them on myCobot 320 (Jetson Orin Nano).

Setup:
  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env   # edit paths
  python3 worker.py      # loads .env automatically
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore

from gpio_buttons import ButtonManager, ButtonPoller
from feeding_cycle import execute_home
from robot_motion import execute_command
from robot_session import (
    advance_selected_section,
    end_feed_cycle,
    get_selected_section,
    is_apriltag_scan_done,
    is_feeding_active,
    mark_emergency_state,
)
from robot_stats import (
    after_successful_feed,
    mark_jetson_online,
    record_failed_feed,
    record_hardware_emergency,
    read_live_phase,
    reset_meal_session,
    set_live_state,
)
from emergency_notify import notify_app_backend_emergency
from estop_hooks import set_estop_callback
from lcd_gui import GUI_MESSAGES, start_gui_process, stop_gui_process, update_gui_state
from pi_arm_client import PiArmClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("care-robot-worker")

ALLOWED = frozenset({"home", "next_bite", "pause", "stop", "calibrate_plate"})

_ROOT = Path(__file__).resolve().parent
_ENV_LOADED = False
_active_buttons: ButtonManager | None = None
_emergency_recovery_deadline: float | None = None
EMERGENCY_RECOVERY_SECONDS = float(os.environ.get("EMERGENCY_RECOVERY_SECONDS", "10.0"))


def _load_dotenv() -> None:
    """Load app/robot-worker/.env (does not override existing shell env)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    env_file = _ROOT / ".env"
    if not env_file.is_file():
        _ENV_LOADED = True
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Allow trailing inline comments: VALUE=foo  # note
        if " #" in value:
            value = value.split(" #", 1)[0].strip()
        value = value.strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
    _ENV_LOADED = True


def _resolve_credentials_path(raw: str) -> str:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_ROOT / path).resolve()
    return str(path)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def robot_id() -> str:
    return os.environ.get("ROBOT_ID", "care-01").strip() or "care-01"


def commands_col(db: firestore.Client) -> firestore.CollectionReference:
    return db.collection("robots").document(robot_id()).collection("commands")


@firestore.transactional
def _claim_transaction(transaction: firestore.Transaction, ref: firestore.DocumentReference) -> bool:
    snap = ref.get(transaction=transaction)
    if not snap.exists:
        return False
    data = snap.to_dict() or {}
    if data.get("status") != "pending":
        return False
    transaction.update(ref, {"status": "running", "updatedAt": utc_now()})
    return True


def claim_command(db: firestore.Client, ref: firestore.DocumentReference) -> bool:
    return _claim_transaction(db.transaction(), ref)


def finish_command(
    ref: firestore.DocumentReference,
    *,
    ok: bool,
    error: str | None = None,
) -> None:
    ref.update(
        {
            "status": "done" if ok else "error",
            "error": error,
            "updatedAt": utc_now(),
        }
    )


def current_section(db: firestore.Client, rid: str) -> int:
    live = db.collection("robots").document(rid).collection("status").document("live").get()
    data = live.to_dict() or {}
    section = data.get("section", 1)
    if isinstance(section, int) and 1 <= section <= 4:
        return section
    return 1


def handle_gpio_feed(db: firestore.Client, rid: str, buttons: ButtonManager) -> None:
    if buttons.is_emergency_latched():
        logger.warning("GPIO feed ignored — emergency latched")
        return
    if is_feeding_active():
        logger.warning("GPIO feed ignored — feed cycle already active")
        return
    if not is_apriltag_scan_done():
        logger.warning("GPIO feed blocked — run plate scan first (press SELECT/plate once)")
        update_gui_state(
            "selection",
            GUI_MESSAGES["feed_blocked_no_scan"],
            connected=True,
            error="Plate scan required",
            force=True,
        )
        return

    section = get_selected_section()
    try:
        execute_command("next_bite", {"sectionNum": section}, buttons=buttons)
    except Exception:
        logger.exception("GPIO feed failed")
        record_failed_feed(db, rid)
        return
    if not buttons.is_emergency_latched() and not is_feeding_active():
        after_successful_feed(db, rid, section, pin=buttons.feed_pin)
        logger.info("GPIO feed button → bite section=%s", section)


def handle_gpio_plate(db: firestore.Client, rid: str, buttons: ButtonManager) -> None:
    if buttons.is_emergency_latched():
        logger.warning("GPIO plate ignored — emergency latched")
        return
    if is_feeding_active():
        logger.warning("GPIO plate ignored — feed cycle active")
        update_gui_state(
            "feeding",
            GUI_MESSAGES["select_during_feed"],
            connected=True,
            force=True,
        )
        return

    try:
        if not is_apriltag_scan_done():
            set_live_state(db, rid, state="CALIBRATING", section=get_selected_section(), emergency=False)
            logger.info("GPIO plate button → AprilTag plate scan")
            execute_command("calibrate_plate", None, buttons=buttons)
            set_live_state(db, rid, state="IDLE", section=get_selected_section(), emergency=False)
            logger.info("Plate scan done — FEED is now enabled")
        else:
            section = advance_selected_section()
            set_live_state(db, rid, state="IDLE", section=section, emergency=False)
            update_gui_state(
                "selection",
                GUI_MESSAGES["select_section"].format(section=section),
                selected_plate_section=section,
                connected=True,
                error="NONE",
                force=True,
            )
            logger.info("GPIO plate button → selected section %s", section)
    except Exception:
        logger.exception("GPIO plate / selection failed")
        record_failed_feed(db, rid)
        set_live_state(db, rid, state="IDLE", section=get_selected_section(), emergency=False)


def handle_emergency_recovery(db: firestore.Client, rid: str, buttons: ButtonManager) -> None:
    """After e-stop: wait, then HOME and clear latch (New_Settings_June26)."""
    global _emergency_recovery_deadline

    if not buttons.is_emergency_latched():
        _emergency_recovery_deadline = None
        return

    now = time.time()
    if _emergency_recovery_deadline is None:
        _emergency_recovery_deadline = now + EMERGENCY_RECOVERY_SECONDS

    if now < _emergency_recovery_deadline:
        seconds_left = max(0, int(round(_emergency_recovery_deadline - now)))
        update_gui_state(
            "emergency",
            GUI_MESSAGES["emergency_wait"].format(seconds=seconds_left),
            emergency=True,
            connected=True,
        )
        return

    if buttons.estop_raw_pressed():
        update_gui_state(
            "emergency",
            GUI_MESSAGES["emergency_release"],
            emergency=True,
            connected=True,
            force=True,
        )
        return

    try:
        execute_home("EMERGENCY_AUTO_RECOVERY")
        end_feed_cycle("EMERGENCY_RECOVERED_HOME")
        buttons.clear_emergency_latch()
        buttons.estop_reported = False
        _emergency_recovery_deadline = None
        set_live_state(db, rid, state="IDLE", section=get_selected_section(), emergency=False)
        update_gui_state(
            "idle",
            GUI_MESSAGES["emergency_recovered"],
            connected=True,
            error="NONE",
            force=True,
        )
        logger.info("Emergency recovery complete — arm homed, system ready")
    except Exception:
        logger.exception("Emergency recovery (HOME) failed")


def handle_gpio_estop(db: firestore.Client, rid: str, buttons: ButtonManager) -> None:
    """Physical e-stop: STOP arm first, then Firestore, then caregiver push."""
    if buttons.estop_reported:
        return
    buttons.estop_reported = True
    buttons.latch_emergency("EMERGENCY_BUTTON_MAIN_LOOP")
    reason = "EMERGENCY_BUTTON"
    mark_emergency_state(reason)
    phase = read_live_phase(db, rid)

    logger.warning("GPIO e-stop pressed (pin %s, phase=%s)", buttons.estop_pin, phase)

    update_gui_state(
        "emergency",
        GUI_MESSAGES["emergency_active"].format(reason=reason),
        emergency=True,
        connected=True,
        force=True,
    )

    try:
        execute_command("stop", None)
    except Exception:
        logger.exception("GPIO e-stop: arm STOP failed")

    try:
        record_hardware_emergency(db, rid, reason=reason, phase=phase, pin=buttons.estop_pin)
    except Exception:
        logger.exception("GPIO e-stop: Firestore update failed")

    try:
        notify_app_backend_emergency(robot_id=rid, reason=reason, phase=phase)
    except Exception:
        logger.exception("GPIO e-stop: app backend notify failed")


def _change_is_added_or_modified(change: Any) -> bool:
    """Works across firebase-admin / google-cloud-firestore versions on Jetson."""
    t = getattr(change, "type", None)
    if t is None:
        return False
    name = getattr(t, "name", "")
    if name in ("ADDED", "MODIFIED"):
        return True
    if t in (1, 2):
        return True
    text = str(t)
    return text.endswith("ADDED") or text.endswith("MODIFIED")


def process_change(db: firestore.Client, col: firestore.CollectionReference, change: Any) -> None:
    if not _change_is_added_or_modified(change):
        return
    snap = change.document
    data = snap.to_dict() or {}
    if data.get("status") != "pending":
        return
    cmd = data.get("cmd")
    if cmd not in ALLOWED:
        logger.warning("skip invalid cmd on %s", snap.id)
        return
    ref = col.document(snap.id)
    if not claim_command(db, ref):
        return
    payload = data.get("payload")
    rid = robot_id()
    try:
        execute_command(
            str(cmd),
            payload if isinstance(payload, dict) else None,
            buttons=_active_buttons,
        )
        finish_command(ref, ok=True)
        if cmd == "next_bite":
            section = get_selected_section()
            if isinstance(payload, dict) and isinstance(payload.get("sectionNum"), int):
                section = payload["sectionNum"]
            if not is_feeding_active():
                feed_pin = int(os.environ.get("GPIO_FEED_PIN", "37"))
                after_successful_feed(db, rid, section, pin=feed_pin)
        elif cmd == "stop":
            emergency = isinstance(payload, dict) and payload.get("emergency") is True
            reset_meal_session(db, rid, emergency=emergency)
        elif cmd in ("home", "pause"):
            reset_meal_session(db, rid, emergency=False)
        logger.info("done %s cmd=%s", snap.id, cmd)
    except Exception as e:
        logger.exception("command %s failed", snap.id)
        record_failed_feed(db, rid)
        reset_meal_session(db, rid, emergency=False)
        finish_command(ref, ok=False, error=str(e))


def main() -> int:
    os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")
    _load_dotenv()
    raw_cred = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not raw_cred:
        logger.error("GOOGLE_APPLICATION_CREDENTIALS is not set. Add it to %s/.env", _ROOT)
        return 1
    cred_path = _resolve_credentials_path(raw_cred)
    if not os.path.isfile(cred_path):
        logger.error("Firebase credentials file not found: %s", cred_path)
        logger.error("Put firebase-service-account.json in %s and set:", _ROOT)
        logger.error("  GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json")
        logger.error("Or use the full path to the JSON file.")
        return 1
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path

    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception:
        logger.exception("Firebase init failed — check GOOGLE_APPLICATION_CREDENTIALS JSON")
        return 1
    rid = robot_id()
    mark_jetson_online(db, rid)

    start_gui_process()
    update_gui_state(
        "startup",
        GUI_MESSAGES["startup"],
        selected_plate_section=get_selected_section(),
        connected=False,
        force=True,
    )

    pi_connected = False
    try:
        with PiArmClient() as arm:
            arm.ping()
        pi_connected = True
    except Exception:
        logger.warning("Pi arm server not reachable at startup (will retry on feed)")

    update_gui_state(
        "idle",
        GUI_MESSAGES["ready_needs_scan"],
        selected_plate_section=get_selected_section(),
        connected=pi_connected,
        error="NONE",
        force=True,
    )

    buttons = ButtonManager()
    global _active_buttons
    _active_buttons = buttons
    buttons.setup()
    set_estop_callback(lambda: handle_gpio_estop(db, rid, buttons))
    poller = ButtonPoller(buttons)
    poller.start()
    col = commands_col(db)
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = col.where(filter=FieldFilter("status", "==", "pending"))
    except ImportError:
        query = col.where("status", "==", "pending")

    def on_snapshot(doc_snapshots: list[Any], changes: list[Any], read_time: Any) -> None:
        for change in changes:
            process_change(db, col, change)

    logger.info(
        "listening robot_id=%s dry_run=%s buttons=%s",
        robot_id(),
        os.environ.get("DRY_RUN", "true"),
        buttons.enabled,
    )
    query.on_snapshot(on_snapshot)

    try:
        while True:
            if buttons.enabled:
                if not buttons.estop_reported and (
                    buttons.estop_pressed() or buttons.estop_raw_pressed()
                ):
                    handle_gpio_estop(db, rid, buttons)
                elif buttons.is_emergency_latched():
                    handle_emergency_recovery(db, rid, buttons)
                    time.sleep(0.05)
                elif buttons.feed_pressed():
                    handle_gpio_feed(db, rid, buttons)
                elif buttons.plate_pressed():
                    handle_gpio_plate(db, rid, buttons)
            time.sleep(0.05)
    except KeyboardInterrupt:
        logger.info("stopped")
    finally:
        poller.stop()
        buttons.cleanup()
        set_estop_callback(None)
        stop_gui_process()
    return 0


if __name__ == "__main__":
    sys.exit(main())
