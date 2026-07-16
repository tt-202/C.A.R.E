#!/usr/bin/env python3


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
    end_feed_cycle, #release feed cycle after emergency recovery
    get_selected_section, #determines which plate selection FEED should use 
    is_apriltag_scan_done, #to make first phase of feed view april tag
    is_feeding_active, #prevents feed or select from interrupting on existing feeding cycle
    mark_emergency_state, #flag to mark emergency is interrupting something
)

#updates the firestore documents
from robot_stats import (
    after_successful_feed,
    mark_jetson_online,
    record_failed_feed,
    record_hardware_emergency,
    read_live_phase,
    reset_meal_session,
    set_live_state,
    touch_jetson_online,
)
from emergency_notify import notify_app_backend_emergency
from estop_hooks import set_estop_callback
from lcd_gui import GUI_MESSAGES, start_gui_process, stop_gui_process, update_gui_state
from pi_arm_client import PiArmClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s") #sets logging format
logger = logging.getLogger("care-robot-worker")

ALLOWED = frozenset({"home", "next_bite", "pause", "stop", "calibrate_plate"}) #allowed firestore commands, nothing else is rendered

_ROOT = Path(__file__).resolve().parent
_ENV_LOADED = False
_active_buttons: ButtonManager | None = None
_emergency_recovery_deadline: float | None = None
_emergency_home_in_progress = False

#loads all our env values
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

#converts firestore credential paths from env
def _resolve_credentials_path(raw: str) -> str:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (_ROOT / path).resolve()
    return str(path)

# def _resolve_credentials_path(raw: str) -> str:
#     path = Path(raw).expanduser()
#     return str(path)

#pull more important information from env
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def robot_id() -> str:
    return os.environ.get("ROBOT_ID", "care-01").strip() or "care-01"


def commands_col(db: firestore.Client) -> firestore.CollectionReference:
    return db.collection("robots").document(robot_id()).collection("commands")

#returns firestore command to robot
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

#function claims pending firestore command
def claim_command(db: firestore.Client, ref: firestore.DocumentReference) -> bool:
    return _claim_transaction(db.transaction(), ref)

#tells app that and ack end of done
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

#app update od section
def current_section(db: firestore.Client, rid: str) -> int:
    live = db.collection("robots").document(rid).collection("status").document("live").get()
    data = live.to_dict() or {}
    section = data.get("section", 1)
    if isinstance(section, int) and 1 <= section <= 4:
        return section
    return 1

#gpio read of feed
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
        completed = execute_command(
            "next_bite",
            {"sectionNum": section},
            buttons=buttons,
            db=db,
            robot_id=rid,
        )
    except Exception:
        logger.exception("GPIO feed failed")
        record_failed_feed(db, rid)
        return
    if completed and not buttons.is_emergency_latched() and not is_feeding_active():
        after_successful_feed(db, rid, section, pin=buttons.feed_pin)
        logger.info("GPIO feed button → bite section=%s", section)

#gpio for selectino, first checks if other states are set
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
            execute_command("calibrate_plate", None, buttons=buttons, db=db, robot_id=rid)
            set_live_state(db, rid, state="IDLE", section=get_selected_section(), emergency=False)
            logger.info("Plate scan done — FEED is now enabled")
        else:
            from feeding_cycle import handle_plate_select_after_scan
            from pi_arm_client import PiArmClient

            with PiArmClient() as arm:
                arm.ping()
                section = handle_plate_select_after_scan(arm, db, rid)
            set_live_state(db, rid, state="IDLE", section=section, emergency=False)
            logger.info("GPIO plate button → selected section %s", section)
    except Exception:
        logger.exception("GPIO plate / selection failed")
        record_failed_feed(db, rid)
        set_live_state(db, rid, state="IDLE", section=get_selected_section(), emergency=False)

#gets the seconds for emergency recovery seoconds
def _get_emergency_recovery_seconds() -> float:
    """Return the emergency hold time before automatic HOME recovery."""
    raw = os.environ.get("EMERGENCY_RECOVERY_SECONDS", "0")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        logger.warning("Invalid EMERGENCY_RECOVERY_SECONDS=%r; using 0", raw)
        return 0.0

#reads delay before e-stop can retrogger, helps stop doubling up on the estop
def _get_estop_rearm_cooldown_seconds() -> float:
    """Return the cooldown after emergency recovery before e-stop can retrigger."""
    raw = os.environ.get("ESTOP_REARM_COOLDOWN_SECONDS", "2.0")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        logger.warning("Invalid ESTOP_REARM_COOLDOWN_SECONDS=%r; using 2.0", raw)
        return 2.0


def handle_emergency_recovery(db: firestore.Client, rid: str, buttons: ButtonManager) -> None:
    """After e-stop: optionally hold stopped, then HOME exactly once."""
    global _emergency_recovery_deadline, _emergency_home_in_progress

    if not buttons.is_emergency_latched():
        _emergency_recovery_deadline = None
        _emergency_home_in_progress = False
        return

    if _emergency_home_in_progress:
        return

    now = time.time()
    emergency_recovery_seconds = _get_emergency_recovery_seconds()

    # If the requested emergency hold is zero, do not show/enter timed
    # emergency_wait state at all. This avoids second 10-second wait

    if emergency_recovery_seconds > 0:
        if _emergency_recovery_deadline is None:
            _emergency_recovery_deadline = now + emergency_recovery_seconds

        if now < _emergency_recovery_deadline:
            seconds_left = max(0, int(round(_emergency_recovery_deadline - now)))
            update_gui_state(
                "emergency",
                GUI_MESSAGES["emergency_wait"].format(seconds=seconds_left),
                emergency=True,
                connected=True,
            )
            return
    else:
        _emergency_recovery_deadline = now

    _emergency_home_in_progress = True
    try:
        update_gui_state(
            "recovery",
            GUI_MESSAGES["emergency_returning_home"],
            emergency=True,
            connected=True,
            force=True,
        )
        execute_home("EMERGENCY_AUTO_RECOVERY")
        end_feed_cycle("EMERGENCY_RECOVERED_HOME")
        buttons.clear_emergency_latch()
        _emergency_recovery_deadline = None

        # Keep the physical e-stop disarmed until it has been released and a short cooldown has passed. This prevents bouncing e-stop pin
        # from starting a second GUI 10-second countdown after HOME begins
        buttons.estop_reported = True
        buttons.disarm_estop_until_release(_get_estop_rearm_cooldown_seconds())

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
    finally:
        _emergency_home_in_progress = False


    #physical button estop
def handle_gpio_estop(db: firestore.Client, rid: str, buttons: ButtonManager) -> None:
   
    if buttons.estop_reported:
        return
    buttons.estop_reported = True
    #logs to statistics system, update
    _run_emergency_stop(
        db,
        rid,
        buttons,
        reason="EMERGENCY_BUTTON",
        pin=buttons.estop_pin,
    )

#app estop
def handle_app_estop(db: firestore.Client, rid: str, buttons: ButtonManager) -> None:
    if buttons.is_emergency_latched():
        logger.warning("App e-stop while emergency already latched — re-sending STOP")
        try:
            from feeding_cycle import execute_stop

            execute_stop("APP_EMERGENCY_STOP")
        except Exception:
            logger.exception("App e-stop: arm STOP retry failed")
        return
    _run_emergency_stop(
        db,
        rid,
        buttons,
        reason="APP_EMERGENCY_STOP",
        pin=None,
    )

#emergency routine for both app and physical button
def _run_emergency_stop(
    db: firestore.Client,
    rid: str,
    buttons: ButtonManager,
    *,
    reason: str,
    pin: int | None,
) -> None:
    buttons.latch_emergency(reason, notify=False)
    mark_emergency_state(reason)
    phase = read_live_phase(db, rid)

    logger.warning("Emergency stop (%s, phase=%s)", reason, phase)

    update_gui_state(
        "emergency",
        GUI_MESSAGES["emergency_active"].format(reason=reason),
        emergency=True,
        connected=True,
        force=True,
    )

    try:
        # Send the actual emergency reason to the Pi instead of the generic STOP reason.
        from feeding_cycle import execute_stop

        execute_stop(reason)
    except Exception:
        logger.exception("Emergency stop: arm STOP failed")

    try:
        record_hardware_emergency(db, rid, reason=reason, phase=phase, pin=pin)
    except Exception:
        logger.exception("Emergency stop: Firestore update failed")

    if reason != "APP_EMERGENCY_STOP":
        try:
            notify_app_backend_emergency(robot_id=rid, reason=reason, phase=phase)
        except Exception:
            logger.exception("Emergency stop: app backend notify failed")

#sees if firestore changed any command or added anything
def _change_is_added_or_modified(change: Any) -> bool:
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


#handles a firestore command from mobile app backend
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
        if cmd == "stop" and isinstance(payload, dict) and payload.get("emergency") is True:
            if _active_buttons is not None:
                handle_app_estop(db, rid, _active_buttons)
            else:
                execute_command("stop", payload, db=db, robot_id=rid)
            completed = False
        else:
            #normal command routing
            completed = execute_command(
                str(cmd),
                payload if isinstance(payload, dict) else None,
                buttons=_active_buttons,
                db=db,
                robot_id=rid,
            )
        #mark command as done
        finish_command(ref, ok=True)
        #command statstics , only update if bite is actually done
        if cmd == "next_bite" and completed:
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
    #failure handling
    except Exception as e:
        logger.exception("command %s failed", snap.id)
        record_failed_feed(db, rid)
        reset_meal_session(db, rid, emergency=False)
        finish_command(ref, ok=False, error=str(e))


def main() -> int:
    #sets up the important information of connection and environemnt
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
        #fireabase initialization
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
    except Exception:
        logger.exception("Firebase init failed — check GOOGLE_APPLICATION_CREDENTIALS JSON")
        return 1
    rid = robot_id()
    mark_jetson_online(db, rid)

    #start the gui process updates where we are
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
        #try the rasbperry pi connection
        with PiArmClient() as arm:
            arm.ping()
        pi_connected = True
    except Exception:
        logger.warning("Pi arm server not reachable at startup (will retry on feed)")

    try:
        from yolo_detector import preload_yolo_models

        preload_yolo_models() #preloads models so we dont have to wait for first feed (helps with latency)
    except Exception:
        logger.warning("YOLO preload skipped", exc_info=True)

    #gui update for the april tag
    update_gui_state(
        "idle",
        GUI_MESSAGES["ready_needs_scan"],
        selected_plate_section=get_selected_section(),
        connected=pi_connected,
        error="NONE",
        force=True,
    )

    buttons = ButtonManager()
    #publishes manager to the FireStore command handler, both point to ButtonManager object
    global _active_buttons
    _active_buttons = buttons
    buttons.setup() #buttonmanager sets up all the gpio pin
    set_estop_callback(lambda: handle_gpio_estop(db, rid, buttons)) #immediate ESTOP callback, it doesn't have to read everything about GUI, movement and such
    poller = ButtonPoller(buttons)
    poller.start()
    #firestore listener setup   
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

    #heartbeat setup
    heartbeat_seconds = float(os.environ.get("FIRESTORE_HEARTBEAT_SECONDS", "45"))
    last_heartbeat = time.monotonic()

    try:
        #keeps worker loop going
        while True:
            #ESTOP trop priority, then feed, then select
            if buttons.enabled:
                if (    #all three must be correct, this makes sure that estop is newly pressed
                    buttons.estop_can_trigger() #is estop already triggered/armed
                    and not buttons.estop_reported
                    and (buttons.estop_pressed() or buttons.estop_raw_pressed())
                ):
                    handle_gpio_estop(db, rid, buttons) #call estop handler
                elif ( #rearms only if all are true
                    buttons.estop_reported
                    and buttons.estop_can_trigger()
                    and not buttons.is_emergency_latched()
                    and not buttons.estop_raw_pressed()
                ):
                    buttons.estop_reported = False
                elif buttons.is_emergency_latched(): #if emergency button is latched, nothing else gets checked
                    handle_emergency_recovery(db, rid, buttons)
                    time.sleep(0.05)
                elif buttons.feed_pressed():
                    handle_gpio_feed(db, rid, buttons)
                elif buttons.plate_pressed():
                    handle_gpio_plate(db, rid, buttons)
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_seconds:
                touch_jetson_online(db, rid)
                last_heartbeat = now
            time.sleep(0.05)
    except KeyboardInterrupt:
        logger.info("stopped")
    #always release GPIO stop polling
    finally:
        poller.stop()
        buttons.cleanup()
        set_estop_callback(None)
        stop_gui_process()
    return 0


if __name__ == "__main__":
    sys.exit(main())