"""
Feeding cycle for Jetson + Pi JSON arm server (New_Settings_June26).

One bite:
  1. SCOOP          — fixed trajectory for selected plate section (Pi)
  2. VIEW_MOUTH     — move to feeding pose (Pi)
  3. Mouth tracking — ALIGN / CENTERED / APPROACH_MOUTH + ToF (Jetson + Pi)
  4. BITE_HOLD      — hold still at mouth
  5. HOME           — return to startup joint angles (Pi)

Plate calibration: VIEW_SELECTION + AprilTag scan (SELECT button / calibrate_plate).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")

from pi_arm_client import PiArmClient, wait_after_move
from robot_session import (
    end_feed_cycle,
    get_selected_section,
    is_feeding_active,
    mark_apriltag_scan_done,
    start_feed_cycle,
)
from tof_subprocess import read_tof_cm_safe, start_tof_reader, stop_tof_reader, use_fake_tof

if TYPE_CHECKING:
    from gpio_buttons import ButtonManager

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent

CAMERA_ID = os.environ.get("CAMERA_ID", "/dev/video0")
CAMERA_WIDTH = int(os.environ.get("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "480"))
CENTER_TOLERANCE = int(
    os.environ.get("CENTER_TOLERANCE", os.environ.get("DEAD_ZONE_PX", "30"))
)
CENTER_HOLD_SECONDS = float(os.environ.get("CENTER_HOLD_SECONDS", "3.0"))
STOP_DISTANCE_CM = float(os.environ.get("STOP_DISTANCE_CM", "30.0"))
BITE_HOLD_SECONDS = float(os.environ.get("BITE_HOLD_SECONDS", "5.0"))
APPROACH_COMMAND_PERIOD = float(os.environ.get("APPROACH_COMMAND_PERIOD", "0.20"))
MAX_APPROACH_SECONDS = float(os.environ.get("MAX_APPROACH_SECONDS", "6.0"))
LOOP_DELAY = float(os.environ.get("LOOP_DELAY", "0.03"))
VIEW_SETTLE_SECONDS = float(os.environ.get("ARM_MOVE_SETTLE", "1.0"))
SHOW_APRILTAG_PREVIEW = os.environ.get("SHOW_APRILTAG_PREVIEW", "true").lower() in (
    "1",
    "true",
    "yes",
)
SHOW_MOUTH_PREVIEW = os.environ.get("SHOW_MOUTH_PREVIEW", "true").lower() in (
    "1",
    "true",
    "yes",
)
MOUTH_SESSION_TIMEOUT = float(os.environ.get("MOUTH_SESSION_TIMEOUT", "0"))


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() in ("1", "true", "yes")


def get_mouth_center(landmarks, w: int, h: int) -> tuple[int, int]:
    left = landmarks[61]
    right = landmarks[291]
    x = int(((left.x + right.x) / 2) * w)
    y = int(((left.y + right.y) / 2) * h)
    return x, y


def _load_plate_scan_module():
    scan_file = ROOT_DIR / "latest_plate_scan.py"
    if not scan_file.exists():
        return None
    spec = importlib.util.spec_from_file_location("latest_plate_scan", scan_file)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _estop_during_motion(buttons: ButtonManager | None, arm: PiArmClient, reason: str) -> bool:
    if buttons is None:
        return False
    if buttons.estop_raw_pressed():
        buttons.latch_emergency(reason)
    if buttons.is_emergency_latched():
        logger.warning("[ESTOP] %s — sending STOP", reason)
        try:
            arm.stop(reason)
        except Exception:
            logger.exception("Failed to send STOP during estop")
        return True
    return False


def run_apriltag_selection_phase(arm: PiArmClient, *, preview: bool = False) -> bool:
    """VIEW_SELECTION + AprilTag scan. Returns True on success."""
    if _dry_run():
        logger.info("DRY_RUN apriltag selection phase")
        time.sleep(1.0)
        mark_apriltag_scan_done()
        return True

    arm.view_selection()
    time.sleep(VIEW_SETTLE_SECONDS)

    script = ROOT_DIR / "run_apriltag_scan.py"
    if not script.exists():
        raise RuntimeError(f"Missing {script}")

    cmd = [sys.executable, str(script)]
    if preview or SHOW_APRILTAG_PREVIEW:
        cmd.append("--preview")

    logger.info("Starting AprilTag scan: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT_DIR), check=False)
    if result.returncode != 0:
        logger.error("AprilTag scan failed (exit %s)", result.returncode)
        return False

    mark_apriltag_scan_done()
    logger.info("AprilTag scan completed for this run")
    return True


def calibrate_plate(*, preview: bool = False) -> dict:
    if _dry_run():
        logger.info("DRY_RUN calibrate_plate")
        time.sleep(1.0)
        mark_apriltag_scan_done()
        return {"plate_center": (320, 240), "plate_z_cm": 25.0}

    with PiArmClient() as arm:
        arm.ping()
        ok = run_apriltag_selection_phase(arm, preview=preview)
    if not ok:
        raise RuntimeError("Plate calibration / AprilTag scan failed")

    plate = _load_plate_scan_module()
    if plate is None and not _dry_run():
        raise RuntimeError("Scan finished but latest_plate_scan.py is missing")
    return {
        "plate_center": getattr(plate, "PLATE_CENTER", (320, 240)) if plate else (320, 240),
        "plate_z_cm": getattr(plate, "PLATE_Z_CM", 25.0) if plate else 25.0,
    }


def run_mouth_feed_session(arm: PiArmClient, buttons: ButtonManager | None = None) -> bool:
    """
    Mouth tracking + ToF approach + bite hold + HOME.
    Returns True if bite completed and arm homed successfully.
    """
    if _dry_run():
        logger.info(
            "DRY_RUN mouth_feed_session (hold=%.1fs, stop=%.1fcm, bite_hold=%.1fs)",
            CENTER_HOLD_SECONDS,
            STOP_DISTANCE_CM,
            BITE_HOLD_SECONDS,
        )
        time.sleep(2.0)
        return True

    import cv2
    import mediapipe as mp

    if buttons is not None:
        buttons.clear_emergency_latch()
        if buttons.estop_raw_pressed():
            buttons.latch_emergency("EMERGENCY_BEFORE_MOUTH_TRACKING")
            arm.stop("EMERGENCY_BEFORE_MOUTH_TRACKING")
            return False

    arm.view_mouth()
    time.sleep(VIEW_SETTLE_SECONDS)

    if buttons is not None:
        buttons.wait_for_feed_release()

    if not use_fake_tof():
        start_tof_reader()

    face_mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    cap = cv2.VideoCapture(CAMERA_ID, cv2.CAP_V4L2)
    if not cap.isOpened():
        face_mesh.close()
        stop_tof_reader()
        raise RuntimeError(f"Could not open USB camera: {CAMERA_ID}")

    center_start_time: float | None = None
    approach_active = False
    approach_start_time: float | None = None
    last_approach_command_time = 0.0
    last_valid_tof_cm: float | None = None
    last_tof_print_time = 0.0
    feeding_completed_and_homed = False
    deadline = (
        time.time() + MOUTH_SESSION_TIMEOUT if MOUTH_SESSION_TIMEOUT > 0 else None
    )

    logger.info(
        "Mouth tracking (hold=%.1fs, stop=%.1fcm, bite_hold=%.1fs, fake_tof=%s)",
        CENTER_HOLD_SECONDS,
        STOP_DISTANCE_CM,
        BITE_HOLD_SECONDS,
        use_fake_tof(),
    )

    try:
        while True:
            if deadline is not None and time.time() > deadline:
                logger.warning("[MOUTH] Session timeout reached")
                break

            now = time.time()

            if _estop_during_motion(buttons, arm, "EMERGENCY_BUTTON_MOUTH_TRACKING"):
                break

            if buttons is not None and buttons.is_emergency_latched():
                arm.stop("EMERGENCY_LATCHED")
                break

            if buttons is not None and buttons.feed_raw_pressed():
                logger.info("[FEED] Ignored during active feed cycle")
                buttons.wait_for_feed_release(timeout=0.5)

            tof_reading = read_tof_cm_safe()
            if tof_reading is not None:
                last_valid_tof_cm = tof_reading
                if now - last_tof_print_time >= 0.5:
                    logger.info("[TOF] Latest distance: %.1f cm", last_valid_tof_cm)
                    last_tof_print_time = now

            ret, frame = cap.read()
            if not ret:
                time.sleep(LOOP_DELAY)
                continue

            frame = cv2.resize(frame, (CAMERA_WIDTH, CAMERA_HEIGHT))
            h, w, _ = frame.shape
            results = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                mx, my = get_mouth_center(landmarks, w, h)
                cx, cy = w // 2, h // 2
                error_x = mx - cx
                error_y = my - cy
                is_centered = (
                    abs(error_x) < CENTER_TOLERANCE and abs(error_y) < CENTER_TOLERANCE
                )

                if is_centered:
                    if center_start_time is None:
                        center_start_time = now
                    centered_duration = now - center_start_time
                    arm.centered()

                    if centered_duration >= CENTER_HOLD_SECONDS and not approach_active:
                        logger.info("[MOUTH] Centered %.1fs — approach allowed", centered_duration)
                        approach_active = True
                        approach_start_time = now
                        last_approach_command_time = 0.0
                else:
                    center_start_time = None
                    if approach_active:
                        logger.info("[APPROACH] Mouth left center — stopping")
                        arm.stop("MOUTH_NOT_CENTERED")
                    approach_active = False
                    approach_start_time = None

                    if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_ALIGN"):
                        break
                    arm.align(float(error_x), float(error_y))

                if approach_active:
                    if _estop_during_motion(buttons, arm, "EMERGENCY_DURING_APPROACH"):
                        approach_active = False
                        break

                    if approach_start_time is None:
                        approach_start_time = now

                    if now - approach_start_time > MAX_APPROACH_SECONDS:
                        logger.info("[APPROACH] Timeout — stopping")
                        arm.stop("APPROACH_TIMEOUT")
                        approach_active = False

                    elif now - last_approach_command_time >= APPROACH_COMMAND_PERIOD:
                        tof_cm = last_valid_tof_cm

                        if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_APPROACH_COMMAND"):
                            approach_active = False
                            break

                        if tof_cm is None:
                            arm.centered()
                            last_approach_command_time = now

                        elif tof_cm <= STOP_DISTANCE_CM:
                            logger.info(
                                "[APPROACH] Stop distance %.1f cm — holding %.1fs for bite",
                                tof_cm,
                                BITE_HOLD_SECONDS,
                            )
                            approach_active = False
                            arm.centered()

                            hold_start = time.time()
                            while time.time() - hold_start < BITE_HOLD_SECONDS:
                                if _estop_during_motion(buttons, arm, "EMERGENCY_DURING_BITE_HOLD"):
                                    break
                                arm.centered()
                                time.sleep(0.2)

                            if buttons is not None and buttons.is_emergency_latched():
                                break

                            arm.home("FEED_COMPLETE_RETURN_HOME")
                            feeding_completed_and_homed = True
                            break

                        else:
                            logger.info("[APPROACH] ToF=%.1f cm — APPROACH_MOUTH", tof_cm)
                            arm.approach_mouth(tof_cm)
                            last_approach_command_time = now
            else:
                if approach_active:
                    logger.info("[APPROACH] Face lost — stopping")
                    arm.stop("FACE_LOST")
                center_start_time = None
                approach_active = False
                approach_start_time = None

            if SHOW_MOUTH_PREVIEW:
                cv2.imshow("Jetson Mouth Tracking", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    logger.info("[MOUTH] Preview exit key pressed")
                    arm.stop("KEY_EXIT")
                    break

            time.sleep(LOOP_DELAY)

    finally:
        if not feeding_completed_and_homed:
            arm.stop("MOUTH_TRACKING_PHASE_ENDED")
            if buttons is None or not buttons.is_emergency_latched():
                try:
                    arm.home("FEED_PHASE_ENDED_RETURN_HOME")
                    feeding_completed_and_homed = True
                except Exception:
                    logger.exception("Home return failed after mouth phase ended")

        cap.release()
        cv2.destroyAllWindows()
        face_mesh.close()
        stop_tof_reader()
        logger.info("Mouth tracking phase ended (homed=%s)", feeding_completed_and_homed)

    return feeding_completed_and_homed


def execute_next_bite(section_num: int | None = None, buttons: ButtonManager | None = None) -> None:
    if buttons is not None and buttons.is_emergency_latched():
        logger.warning("Skipping bite — emergency latched")
        return

    section = int(section_num if section_num is not None else get_selected_section())
    if section < 1 or section > 4:
        raise ValueError(f"section must be 1-4, got {section}")

    start_feed_cycle(section)
    logger.info("=== BITE START section=%s ===", section)

    if _dry_run():
        logger.info("DRY_RUN next_bite: SCOOP → VIEW_MOUTH → mouth track → HOME")
        time.sleep(2.0)
        end_feed_cycle()
        logger.info("=== BITE DONE (dry run) ===")
        return

    homed = False
    try:
        with PiArmClient() as arm:
            logger.info("Pi ping: %s", arm.ping())

            if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_SCOOP"):
                return

            logger.info("Step 1/3: SCOOP section %s", section)
            arm.scoop(section)

            if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_MOUTH"):
                return

            logger.info("Step 2/3: mouth tracking + ToF approach")
            homed = run_mouth_feed_session(arm, buttons)

            if buttons is not None and buttons.is_emergency_latched():
                logger.warning("=== BITE ABORTED (emergency) section=%s ===", section)
                return

    except Exception:
        logger.exception("Bite failed for section %s", section)
        try:
            with PiArmClient() as arm:
                arm.stop("BITE_ERROR")
                if buttons is None or not buttons.is_emergency_latched():
                    arm.home("BITE_ERROR_RETURN_HOME")
                    homed = True
        except Exception:
            logger.exception("Error recovery failed")
        raise
    finally:
        if homed:
            end_feed_cycle()

    logger.info("=== BITE DONE section=%s ===", section)


def execute_stop(reason: str = "STOP") -> None:
    if _dry_run():
        logger.info("DRY_RUN stop")
        return
    with PiArmClient() as arm:
        arm.stop(reason)


def execute_home(reason: str = "HOME") -> None:
    if _dry_run():
        logger.info("DRY_RUN home")
        return
    with PiArmClient() as arm:
        arm.home(reason)
    end_feed_cycle()
