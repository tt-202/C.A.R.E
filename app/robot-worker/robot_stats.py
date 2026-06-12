"""Publish live robot status and feed counts to Firestore for the care-app."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from firebase_admin import firestore


def _robot_root(db: firestore.Client, robot_id: str) -> firestore.DocumentReference:
    return db.collection("robots").document(robot_id)


def mark_jetson_online(db: firestore.Client, robot_id: str) -> None:
    _robot_root(db, robot_id).collection("status").document("live").set(
        {
            "state": "IDLE",
            "jetson_online": True,
            "emergency": False,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )


def set_live_state(
    db: firestore.Client,
    robot_id: str,
    *,
    state: str,
    emergency: bool = False,
    bite_count: int | None = None,
    section: int | None = None,
) -> None:
    payload: dict[str, Any] = {
        "state": state,
        "emergency": emergency,
        "jetson_online": True,
        "updatedAt": firestore.SERVER_TIMESTAMP,
    }
    if bite_count is not None:
        payload["bite_count"] = bite_count
    if section is not None:
        payload["section"] = section
    if state == "FEEDING":
        payload["last_feed_time"] = firestore.SERVER_TIMESTAMP
    _robot_root(db, robot_id).collection("status").document("live").set(payload, merge=True)


def record_successful_bite(db: firestore.Client, robot_id: str, section_num: int = 1) -> None:
    feed_ref = _robot_root(db, robot_id).collection("stats").document("feed_counts")
    snap = feed_ref.get()
    data = snap.to_dict() if snap.exists else {}
    total = int(data.get("total_bites") or data.get("eat_press_count") or 0) + 1
    successful = int(data.get("successful_feeds") or 0) + 1
    attempts = int(data.get("total_feed_attempts") or successful)

    feed_ref.set(
        {
            "total_bites": total,
            "successful_feeds": successful,
            "failed_feeds": int(data.get("failed_feeds") or 0),
            "total_feed_attempts": max(attempts, successful),
            "eat_press_count": total,
            "updatedAt": firestore.SERVER_TIMESTAMP,
        },
        merge=True,
    )
    set_live_state(
        db,
        robot_id,
        state="FEEDING",
        bite_count=total,
        section=section_num,
        emergency=False,
    )


def record_failed_feed(db: firestore.Client, robot_id: str) -> None:
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
    _robot_root(db, robot_id).collection("status").document("button_input").set(payload, merge=True)
