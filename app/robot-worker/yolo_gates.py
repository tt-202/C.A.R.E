"""YOLO plate/spoon gates (CARE_YOLO_Plate_RecheckAfterFeed_Jetson)."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Literal

from lcd_gui import GUI_MESSAGES, update_gui_state
from plate_notify import notify_app_backend_plate_empty
from robot_session import (
    advance_selected_section,
    get_plate_food_status,
    get_robot_view,
    get_selected_section,
    set_plate_food_status,
    set_robot_view,
    increment_spoon_failed,
    reset_spoon_failed,
)
from robot_stats import set_yolo_status

if TYPE_CHECKING:
    from firebase_admin import firestore

    from pi_arm_client import PiArmClient

logger = logging.getLogger(__name__)

YoloStatus = Literal["full", "empty", "unknown"]
ForceMode = Literal["auto", "full", "empty", "unknown"]

VALID_FORCE_VALUES: frozenset[str] = frozenset({"auto", "full", "empty", "unknown"})
FORCED_YOLO_STATUSES: frozenset[str] = frozenset({"full", "empty", "unknown"})

ENABLE_YOLO_CHECKS = os.environ.get("ENABLE_YOLO_CHECKS", "true").lower() in ("1", "true", "yes")
SHOW_YOLO_PREVIEW = os.environ.get("SHOW_YOLO_PREVIEW", "false").lower() in ("1", "true", "yes")
YOLO_FAIL_OPEN = os.environ.get("YOLO_FAIL_OPEN", "false").lower() in ("1", "true", "yes")
MAX_FAILED_SCOOPS_PER_SECTION = int(os.environ.get("MAX_FAILED_SCOOPS_PER_SECTION", "3"))
VIEW_SETTLE_SECONDS = float(os.environ.get("ARM_MOVE_SETTLE", "1.0"))
SCOOP_YOLO_SETTLE_SECONDS = float(os.environ.get("SCOOP_YOLO_SETTLE_SECONDS", "1.5"))


def parse_force_status(env_key: str) -> ForceMode:
    """Read FORCE_PLATE_STATUS / FORCE_SPOON_STATUS; invalid values fall back to auto."""
    raw = os.environ.get(env_key, "auto").strip().lower()
    if raw not in VALID_FORCE_VALUES:
        if raw:
            logger.warning(
                "[YOLO FORCE] Invalid %s=%r — treating as auto",
                env_key,
                os.environ.get(env_key),
            )
        return "auto"
    return raw  # type: ignore[return-value]


def get_force_plate_status() -> ForceMode:
    return parse_force_status("FORCE_PLATE_STATUS")


def get_force_spoon_status() -> ForceMode:
    return parse_force_status("FORCE_SPOON_STATUS")


def _publish_yolo(
    db: firestore.Client | None,
    robot_id: str | None,
    *,
    plate_status: str | None = None,
    spoon_status: str | None = None,
) -> None:
    if db is None or not robot_id:
        return
    set_yolo_status(db, robot_id, plate_status=plate_status, spoon_status=spoon_status)


def _resolve_plate_status() -> tuple[YoloStatus, str, dict | None]:
    """
    Resolve plate YOLO result.
    Returns (status, source, raw_result) where source is 'forced', 'yolo', or 'disabled'.
    """
    force = get_force_plate_status()
    if force in FORCED_YOLO_STATUSES:
        logger.info("[YOLO PLATE FORCE] FORCE_PLATE_STATUS=%s", force)
        return force, "forced", None  # type: ignore[return-value]

    if not ENABLE_YOLO_CHECKS:
        return "full", "disabled", None

    try:
        from yolo_detector import check_plate_state

        result = check_plate_state(preview=SHOW_YOLO_PREVIEW)
        status = str(result.get("status", "unknown")).strip().lower()
        if status not in FORCED_YOLO_STATUSES:
            status = "unknown"
        if status != "full":
            _log_yolo_diagnostic("PLATE", result, status)
        return status, "yolo", result  # type: ignore[return-value]
    except Exception:
        logger.exception("[YOLO PLATE] check failed")
        return "unknown", "yolo", None


def _log_yolo_diagnostic(label: str, result: dict | None, status: str) -> None:
    if not result:
        return
    logger.warning(
        "[YOLO %s] result=%s (not passing gate) votes=%s best_class=%r conf=%.2f detections=%s",
        label,
        status,
        result.get("votes"),
        result.get("best_class"),
        float(result.get("best_confidence") or 0),
        result.get("recent_detections"),
    )
    if result.get("best_class") and status == "unknown":
        logger.warning(
            "[YOLO %s] Class %r is not mapped to full/empty in yolo_detector.py — "
            "add it to SPOON_FULL_CLASSES or PLATE_FULL_CLASSES, or lower YOLO_MIN_VOTES.",
            label,
            result.get("best_class"),
        )


def _resolve_spoon_status() -> tuple[YoloStatus, str, dict | None]:
    """Resolve spoon YOLO result. Returns (status, source, raw_result)."""
    force = get_force_spoon_status()
    if force in FORCED_YOLO_STATUSES:
        logger.info("[YOLO SPOON FORCE] FORCE_SPOON_STATUS=%s", force)
        return force, "forced", None  # type: ignore[return-value]

    if not ENABLE_YOLO_CHECKS:
        return "full", "disabled", None

    try:
        from yolo_detector import check_spoon_state

        result = check_spoon_state(preview=SHOW_YOLO_PREVIEW)
        status = str(result.get("status", "unknown")).strip().lower()
        if status not in FORCED_YOLO_STATUSES:
            status = "unknown"
        if status != "full":
            _log_yolo_diagnostic("SPOON", result, status)
        return status, "yolo", result  # type: ignore[return-value]
    except Exception:
        logger.exception("[YOLO SPOON] check failed")
        return "unknown", "yolo", None


def _plate_gate_skipped() -> bool:
    """Legacy bypass: YOLO disabled and no manual plate override."""
    return not ENABLE_YOLO_CHECKS and get_force_plate_status() == "auto"


def _spoon_gate_skipped() -> bool:
    """Legacy bypass: YOLO disabled and no manual spoon override."""
    return not ENABLE_YOLO_CHECKS and get_force_spoon_status() == "auto"


def run_plate_yolo_check(
    arm: PiArmClient | None,
    db: firestore.Client | None,
    robot_id: str | None,
    *,
    already_in_selection_view: bool = False,
) -> bool:
    """Whole-plate YOLO at selection view. Returns True if feed may proceed."""
    section = get_selected_section()

    if _plate_gate_skipped():
        set_plate_food_status("full")
        _publish_yolo(db, robot_id, plate_status="full")
        logger.info("[YOLO PLATE] skipped (ENABLE_YOLO_CHECKS=false, FORCE_PLATE_STATUS=auto)")
        return True

    if arm is not None and not already_in_selection_view:
        arm.view_selection()
        set_robot_view("selection")
        time.sleep(VIEW_SETTLE_SECONDS)

    update_gui_state(
        "plate_checking",
        GUI_MESSAGES["plate_check_start"],
        selected_plate_section=section,
        connected=True,
        error="NONE",
        force=True,
    )

    status, source, _raw = _resolve_plate_status()
    set_plate_food_status(status)
    _publish_yolo(db, robot_id, plate_status=status)
    logger.info("[YOLO PLATE] status=%s section=%s source=%s", status, section, source)

    if status == "full":
        update_gui_state(
            "plate_full",
            GUI_MESSAGES["plate_full"],
            selected_plate_section=section,
            connected=True,
            error="NONE",
            force=True,
        )
        return True

    if status == "empty":
        update_gui_state(
            "plate_empty",
            GUI_MESSAGES["plate_empty"],
            selected_plate_section=section,
            connected=True,
            error="Plate empty",
            force=True,
        )
        if robot_id:
            notify_app_backend_plate_empty(robot_id=robot_id, section=section, status=status)
        return False

    update_gui_state(
        "plate_unknown",
        GUI_MESSAGES["plate_unknown"],
        selected_plate_section=section,
        connected=True,
        error="Plate check unknown",
        force=True,
    )
    return bool(YOLO_FAIL_OPEN)


def ensure_plate_has_food_before_feed(
    arm: PiArmClient,
    db: firestore.Client | None,
    robot_id: str | None,
) -> bool:
    """Recheck plate when not at selection view (after feed/home)."""
    if _plate_gate_skipped():
        set_plate_food_status("full")
        _publish_yolo(db, robot_id, plate_status="full")
        return True

    cached = str(get_plate_food_status()).strip().lower()
    view = get_robot_view()
    force = get_force_plate_status()

    if view != "selection":
        logger.info("[FEED_PLATE_GATE] view=%s — moving to selection and checking plate", view)
        arm.view_selection()
        set_robot_view("selection")
        time.sleep(VIEW_SETTLE_SECONDS)
        return run_plate_yolo_check(arm, db, robot_id, already_in_selection_view=True)

    if force != "auto":
        logger.info("[FEED_PLATE_GATE] FORCE_PLATE_STATUS=%s — rechecking plate", force)
        return run_plate_yolo_check(arm, db, robot_id, already_in_selection_view=True)

    if cached == "full":
        logger.info("[FEED_PLATE_GATE] cached plate status is full")
        return True

    logger.info("[FEED_PLATE_GATE] cached status=%s — rechecking plate", cached)
    return run_plate_yolo_check(arm, db, robot_id, already_in_selection_view=True)


def run_spoon_yolo_check_after_scoop(
    section: int,
    db: firestore.Client | None,
    robot_id: str | None,
) -> bool:
    """YOLO spoon check after SCOOP. Returns True to continue to mouth phase."""
    section = int(section)

    if _spoon_gate_skipped():
        reset_spoon_failed(section)
        _publish_yolo(db, robot_id, spoon_status="full")
        logger.info("[YOLO SPOON] skipped (ENABLE_YOLO_CHECKS=false, FORCE_SPOON_STATUS=auto)")
        return True

    update_gui_state(
        "spoon_checking",
        GUI_MESSAGES["spoon_check_start"],
        selected_plate_section=section,
        connected=True,
        error="NONE",
        force=True,
    )

    status, source, _raw = _resolve_spoon_status()
    _publish_yolo(db, robot_id, spoon_status=status)
    logger.info("[YOLO SPOON] section=%s status=%s source=%s", section, status, source)

    if status == "full":
        reset_spoon_failed(section)
        update_gui_state(
            "spoon_full",
            GUI_MESSAGES["spoon_full"],
            selected_plate_section=section,
            connected=True,
            error="NONE",
            force=True,
        )
        return True

    if status == "unknown":
        update_gui_state(
            "spoon_unknown",
            GUI_MESSAGES["spoon_unknown"],
            selected_plate_section=section,
            connected=True,
            error="Spoon check unknown",
            force=True,
        )
        return bool(YOLO_FAIL_OPEN)

    failed_count = increment_spoon_failed(section)
    if failed_count >= MAX_FAILED_SCOOPS_PER_SECTION:
        message = GUI_MESSAGES["spoon_failed_limit"]
        error = "Repeated empty spoon"
    else:
        message = GUI_MESSAGES["spoon_empty"]
        error = "Spoon empty"

    update_gui_state(
        "spoon_empty",
        f"{message} ({failed_count}/{MAX_FAILED_SCOOPS_PER_SECTION})",
        selected_plate_section=section,
        connected=True,
        error=error,
        force=True,
    )
    return bool(YOLO_FAIL_OPEN)


def handle_plate_button_after_scan(
    arm: PiArmClient,
    db: firestore.Client | None,
    robot_id: str | None,
) -> int:
    """
    SELECT after AprilTag: from home → selection view + plate YOLO;
    already at selection → cycle section only.
    Returns new selected section.
    """
    if get_robot_view() != "selection":
        arm.view_selection()
        set_robot_view("selection")
        time.sleep(VIEW_SETTLE_SECONDS)
        run_plate_yolo_check(arm, db, robot_id, already_in_selection_view=True)
        return get_selected_section()

    section = advance_selected_section()
    update_gui_state(
        "selection",
        GUI_MESSAGES["select_section"].format(section=section),
        selected_plate_section=section,
        connected=True,
        error="NONE",
        force=True,
    )
    return section
