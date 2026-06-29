"""YOLO plate/spoon gates (CARE_YOLO_Plate_RecheckAfterFeed_Jetson)."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

from lcd_gui import GUI_MESSAGES, update_gui_state
from plate_notify import notify_app_backend_plate_empty
from robot_session import (
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

    from gpio_buttons import ButtonManager
    from pi_arm_client import PiArmClient

logger = logging.getLogger(__name__)

ENABLE_YOLO_CHECKS = os.environ.get("ENABLE_YOLO_CHECKS", "true").lower() in ("1", "true", "yes")
SHOW_YOLO_PREVIEW = os.environ.get("SHOW_YOLO_PREVIEW", "false").lower() in ("1", "true", "yes")
YOLO_FAIL_OPEN = os.environ.get("YOLO_FAIL_OPEN", "false").lower() in ("1", "true", "yes")
MAX_FAILED_SCOOPS_PER_SECTION = int(os.environ.get("MAX_FAILED_SCOOPS_PER_SECTION", "3"))
VIEW_SETTLE_SECONDS = float(os.environ.get("ARM_MOVE_SETTLE", "1.0"))


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() in ("1", "true", "yes")


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


def run_plate_yolo_check(
    arm: PiArmClient | None,
    db: firestore.Client | None,
    robot_id: str | None,
    *,
    already_in_selection_view: bool = False,
) -> bool:
    """Whole-plate YOLO at selection view. Returns True if feed may proceed."""
    section = get_selected_section()

    if _dry_run() or not ENABLE_YOLO_CHECKS:
        set_plate_food_status("full")
        _publish_yolo(db, robot_id, plate_status="full")
        return True

    if arm is not None and not already_in_selection_view:
        arm.view_selection()
        set_robot_view("selection")
        import time

        time.sleep(VIEW_SETTLE_SECONDS)

    update_gui_state(
        "plate_checking",
        GUI_MESSAGES["plate_check_start"],
        selected_plate_section=section,
        connected=True,
        error="NONE",
        force=True,
    )

    status = "unknown"
    try:
        from yolo_detector import check_plate_state

        result = check_plate_state(preview=SHOW_YOLO_PREVIEW)
        status = str(result.get("status", "unknown")).strip().lower()
    except Exception as exc:
        logger.exception("[YOLO PLATE] check failed")
        status = "unknown"

    set_plate_food_status(status)
    _publish_yolo(db, robot_id, plate_status=status)
    logger.info("[YOLO PLATE] status=%s section=%s", status, section)

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
    cached = str(get_plate_food_status()).strip().lower()
    view = get_robot_view()

    if view != "selection":
        logger.info("[FEED_PLATE_GATE] view=%s — moving to selection and checking plate", view)
        arm.view_selection()
        set_robot_view("selection")
        import time

        time.sleep(VIEW_SETTLE_SECONDS)
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

    if _dry_run() or not ENABLE_YOLO_CHECKS:
        reset_spoon_failed(section)
        _publish_yolo(db, robot_id, spoon_status="full")
        return True

    update_gui_state(
        "spoon_checking",
        GUI_MESSAGES["spoon_check_start"],
        selected_plate_section=section,
        connected=True,
        error="NONE",
        force=True,
    )

    status = "unknown"
    try:
        from yolo_detector import check_spoon_state

        result = check_spoon_state(preview=SHOW_YOLO_PREVIEW)
        status = str(result.get("status", "unknown")).strip().lower()
    except Exception as exc:
        logger.exception("[YOLO SPOON] check failed")
        status = "unknown"

    _publish_yolo(db, robot_id, spoon_status=status)
    logger.info("[YOLO SPOON] section=%s status=%s", section, status)

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
    from robot_session import advance_selected_section

    if get_robot_view() != "selection":
        arm.view_selection()
        set_robot_view("selection")
        import time

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
