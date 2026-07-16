"""
robot_stats.py

Updates the robot's status and feeding statistics in Firestore so the
caregiver app can display live robot information.

Firestore:
  robots/{robot_id}/status/live          - Current robot status
  robots/{robot_id}/status/button_input  - FEED / E-Stop button status
  robots/{robot_id}/stats/feed_counts    - Feeding statistics
  robots/{robot_id}/events/...           - Robot event log

Uses merge=True so only updated fields are changed.

This file only updates Firestore. It does not control the robot arm.
"""

from __future__ import annotations

from typing import Any

from firebase_admin import firestore


# ---------------------------------------------------------------------------
# Path helpers — keep the Firestore document paths in one place
# ---------------------------------------------------------------------------

def _robot_root(db: firestore.Client, robot_id: str) -> firestore.DocumentReference:
     #Top-level doc for this robot: robots/{robot_id}.
    return db.collection("robots").document(robot_id)


def _live_ref(db: firestore.Client, robot_id: str) -> firestore.DocumentReference:
    #Live status the care-app watches: robots/{robot_id}/status/live.
    return _robot_root(db, robot_id).collection("status").document("live")


def _button_input_ref(db: firestore.Client, robot_id: str) -> firestore.DocumentReference:
    #Button flags: robots/{robot_id}/status/button_input.
    return _robot_root(db, robot_id).collection("status").document("button_input")


# ---------------------------------------------------------------------------
# Online / heartbeat
# ---------------------------------------------------------------------------

def mark_jetson_online(db: firestore.Client, robot_id: str) -> None:
    #Called once when worker.py starts.

    #Resets the live dashboard to a clean IDLE baseline so the app doesn't
    #still show an old FEEDING / EMERGENCY from a previous run.
    
    _live_ref(db, robot_id).set(
        {
            "state": "IDLE",
            "jetson_online": True,
            "emergency": False,
            "bite_count": 0,
            "section": 1,
            "updatedAt": firestore.SERVER_TIMESTAMP,  # Firestore fills in server time
        },
        merge=True,
    )


def touch_jetson_online(
    db: firestore.Client,
    robot_id: str,
    *,
    state: str | None = None,
) -> None:
    #Heartbeat / keep-alive for care-app live status (merge only).
    payload: dict[str, Any] = {
        "jetson_online": True,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if state is not None:
        payload["state"] = state
    _live_ref(db, robot_id).set(payload, merge=True)


# ---------------------------------------------------------------------------
# Live state (what phase the feed cycle is in)
# ---------------------------------------------------------------------------

def set_live_state(
    db: firestore.Client,
    robot_id: str,
    *,
    state: str,
    emergency: bool = False,
    bite_count: int | None = None,
    section: int | None = None,
    plate_yolo_status: str | None = None,
    spoon_yolo_status: str | None = None,
) -> None:
    #Update the live dashboard with the current robot phase.
    #Examples of state: IDLE, FEEDING, SCOOPING, EMERGENCY, …
    #Optional fields (bite_count, section, YOLO results) are only written
    #when the caller passes them — so idle heartbeats don't zero out stats.
    
    payload: dict[str, Any] = {
        "state": state,
        "emergency": emergency,
        "jetson_online": True,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    # Only include these if the caller gave a value
    if bite_count is not None:
        payload["bite_count"] = bite_count
    if section is not None:
        payload["section"] = section
    if plate_yolo_status is not None:
        payload["plate_yolo_status"] = plate_yolo_status
    if spoon_yolo_status is not None:
        payload["spoon_yolo_status"] = spoon_yolo_status
    # stamp last feed time whenever we enter FEEDING
    if state == "FEEDING":
        payload["last_feed_time"] = firestore.SERVER_TIMESTAMP
    _live_ref(db, robot_id).set(payload, merge=True)


def set_yolo_status(
    db: firestore.Client,
    robot_id: str,
    *,
    plate_status: str | None = None,
    spoon_status: str | None = None,
) -> None:
    #Publish YOLO check results (plate full/empty, spoon full/empty).

    #Used so the care-app can show why a feed was blocked or retried.
    
    payload: dict[str, Any] = {
        "jetson_online": True,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if plate_status is not None:
        payload["plate_yolo_status"] = str(plate_status)
    if spoon_status is not None:
        payload["spoon_yolo_status"] = str(spoon_status)
    _live_ref(db, robot_id).set(payload, merge=True)


def reset_meal_session(db: firestore.Client, robot_id: str, *, emergency: bool = False) -> None:
    #Clear the current meal session back to IDLE.
    #bite_count goes to 0, section back to 1, eat button flag cleared.
    #If emergency=True we also mark stop_pressed (coming out of an e-stop).
    
    set_live_state(
        db,
        robot_id,
        state="IDLE",
        bite_count=0,
        section=1,
        emergency=emergency,
    )
    publish_button_input(
        db,
        robot_id,
        eat_pressed=False,
        stop_pressed=emergency,
    )


# ---------------------------------------------------------------------------
# Feed / bite counters
# ---------------------------------------------------------------------------

def record_feed_button_press(db: firestore.Client, robot_id: str, *, pin: int) -> int:
    #Increment eat_press_seq so the care-app can sync one DB bite per button press.
    ref = _button_input_ref(db, robot_id)
    snap = ref.get()
    # read old seq (or 0), then +1
    seq = int((snap.to_dict() or {}).get("eat_press_seq") or 0) + 1
    ref.set(
        {
            "eat_pressed": True,
            "eat_press_seq": seq,
            "last_pin": pin,  # which GPIO pin (useful for debugging)
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    return seq


def after_successful_feed(
    db: firestore.Client,
    robot_id: str,
    section_num: int,
    *,
    pin: int | None = None,
) -> None:
    record_successful_bite(db, robot_id, section_num)
    if pin is not None:
        record_feed_button_press(db, robot_id, pin=pin)


def record_successful_bite(db: firestore.Client, robot_id: str, section_num: int = 1) -> None:
    feed_ref = _robot_root(db, robot_id).collection("stats").document("feed_counts")
    snap = feed_ref.get()
    data = snap.to_dict() if snap.exists else {}

    # lifetime totals — fall back to older field names if they still exist
    lifetime_total = int(data.get("total_bites") or data.get("eat_press_count") or 0) + 1
    successful = int(data.get("successful_feeds") or 0) + 1
    attempts = int(data.get("total_feed_attempts") or successful)

    # session (this meal) count lives on the live doc
    live_data = _live_ref(db, robot_id).get().to_dict() or {}
    session_bites = int(live_data.get("bite_count") or 0) + 1

    feed_ref.set(
        {
            "total_bites": lifetime_total,
            "successful_feeds": successful,
            "failed_feeds": int(data.get("failed_feeds") or 0),
            "total_feed_attempts": max(attempts, successful),
            "eat_press_count": lifetime_total,  # kept for older care-app code
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    set_live_state(
        db,
        robot_id,
        state="FEEDING",
        bite_count=session_bites,
        section=section_num,
        emergency=False,
    )


def record_failed_feed(db: firestore.Client, robot_id: str) -> None:
    #Scoop / spoon check / tracking failed — bump failed + attempt counters.

    #Does NOT change bite_count (no successful bite happened).

    feed_ref = _robot_root(db, robot_id).collection("stats").document("feed_counts")
    snap = feed_ref.get()
    data = snap.to_dict() if snap.exists else {}
    failed = int(data.get("failed_feeds") or 0) + 1
    attempts = int(data.get("total_feed_attempts") or 0) + 1
    feed_ref.set(
        {
            "failed_feeds": failed,
            "total_feed_attempts": attempts,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def read_live_phase(db: firestore.Client, robot_id: str) -> str:
    #Read the current live state string (IDLE, FEEDING, …) or 'unknown'.
    live = _live_ref(db, robot_id).get().to_dict() or {}
    return str(live.get("state") or "unknown")


# ---------------------------------------------------------------------------
# Buttons + emergency (reporting only)
# ---------------------------------------------------------------------------

def publish_button_input(
    db: firestore.Client,
    robot_id: str,
    *,
    eat_pressed: bool | None = None,
    stop_pressed: bool | None = None,
    last_pin: int | None = None,
) -> None:
    payload: dict[str, Any] = {"updatedAt": firestore.SERVER_TIMESTAMP}
    if eat_pressed is not None:
        payload["eat_pressed"] = eat_pressed
    if stop_pressed is not None:
        payload["stop_pressed"] = stop_pressed
    if last_pin is not None:
        payload["last_pin"] = last_pin
    _button_input_ref(db, robot_id).set(payload, merge=True)


def record_hardware_emergency(
    db: firestore.Client,
    robot_id: str,
    *,
    reason: str,
    phase: str,
    pin: int,
) -> None:
    #Firestore status + event log after physical e-stop (reporting only — arm already stopped).
    _live_ref(db, robot_id).set(
        {
            "state": "EMERGENCY",
            "emergency": True,
            "jetson_online": True,
            "last_event_type": "emergency_stop",
            "last_event_reason": reason,
            "last_event_severity": "critical",
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    publish_button_input(db, robot_id, stop_pressed=True, last_pin=pin)
    # .add() creates a new auto-id document under events/
    _robot_root(db, robot_id).collection("events").add(
        {
            "event_type": "emergency_stop",
            "reason": reason,
            "phase": phase,  # what the robot was doing when e-stop hit
            "severity": "critical",
            "source": "jetson",
            "robot_id": robot_id,
            "acknowledged": False,
            "timestamp": firestore.SERVER_TIMESTAMP,
        }
    )
