"""
Complete feeding cycle for Jetson + Pi arm server.

One bite:
  1. SECTION_PICK   — arm to plate section, dip/scoop/lift
  2. VIEW_MOUTH     — move to feeding pose
  3. Mouth tracking — align + ToF-guarded Y approach (With_Emergency_Stop logic)
  4. VIEW_SELECTION — return to plate area for next bite

Plate calibration (AprilTag + ToF) runs separately via calibrate_plate().
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

from pi_arm_client import PiArmClient, wait_after_move
from tof_subprocess import read_tof_cm_safe, start_tof_reader, stop_tof_reader, use_fake_tof

if TYPE_CHECKING:
    from gpio_buttons import ButtonManager

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent

CAMERA_ID = os.environ.get("CAMERA_ID", "/dev/video0")
CAMERA_WIDTH = int(os.environ.get("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "480"))
DEAD_ZONE_PX = int(os.environ.get("DEAD_ZONE_PX", "30"))
MAX_STEP_MM = float(os.environ.get("MAX_STEP_MM", "5.0"))
CENTER_HOLD_SECONDS = float(os.environ.get("CENTER_HOLD_SECONDS", "3.0"))
STOP_DISTANCE_CM = float(os.environ.get("STOP_DISTANCE_CM", "5.0"))
APPROACH_COMMAND_PERIOD = float(os.environ.get("APPROACH_COMMAND_PERIOD", "0.20"))
MAX_APPROACH_SECONDS = float(os.environ.get("MAX_APPROACH_SECONDS", "6.0"))
LOOP_DELAY = float(os.environ.get("LOOP_DELAY", "0.03"))
INVERT_X = os.environ.get("INVERT_X", "false").lower() in ("1", "true", "yes")
INVERT_Y = os.environ.get("INVERT_Y", "false").lower() in ("1", "true", "yes")


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() in ("1", "true", "yes")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def pixel_offset_to_mm(offset_px: float, dead_zone_px: float = DEAD_ZONE_PX, max_mm: float = MAX_STEP_MM) -> float:
    if dead_zone_px <= 0:
        return 0.0
    mm = (offset_px / dead_zone_px) * max_mm
    return clamp(mm, -max_mm, max_mm)


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
        logger.warning("[ESTOP] %s — sending STOP to Pi", reason)
        try:
            arm.stop()
        except Exception:
            logger.exception("Failed to send STOP during estop")
        return True
    return False


def _align_toward_mouth(arm: PiArmClient, error_x: int, error_y: int) -> None:
    ox, oy = error_x, error_y
    if INVERT_X:
        ox = -ox
    if INVERT_Y:
        oy = -oy
    dx_mm = pixel_offset_to_mm(ox)
    dz_mm = pixel_offset_to_mm(-oy)
    if abs(dx_mm) < 0.05 and abs(dz_mm) < 0.05:
        arm.feed_pause()
        return
    arm.xz_delta(dx_mm, dz_mm)


def calibrate_plate(*, preview: bool = False) -> dict:
    if _dry_run():
        logger.info("DRY_RUN calibrate_plate")
        time.sleep(1.0)
        return {"plate_center": (320, 240), "plate_z_cm": 25.0}

    script = ROOT_DIR / "run_apriltag_scan.py"
    cmd = [sys.executable, str(script)]
    if preview:
        cmd.append("--preview")
    logger.info("Starting plate calibration: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT_DIR), check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Plate calibration failed (exit {result.returncode})")

    plate = _load_plate_scan_module()
    if plate is None:
        raise RuntimeError("Plate calibration finished but latest_plate_scan.py is missing")
    return {
        "plate_center": getattr(plate, "PLATE_CENTER", None),
        "plate_z_cm": getattr(plate, "PLATE_Z_CM", None),
    }


def run_mouth_feed_session(arm: PiArmClient, buttons: ButtonManager | None = None) -> None:
    """
    MediaPipe mouth tracking + ToF-guarded approach.
    Ported from With_Emergency_Stop/main_controller_phase4.py.
    """
    if _dry_run():
        logger.info("DRY_RUN mouth_feed_session (center %.1fs, ToF stop %.1f cm)", CENTER_HOLD_SECONDS, STOP_DISTANCE_CM)
        time.sleep(2.0)
        return

    import cv2
    import mediapipe as mp

    if buttons is not None:
        buttons.clear_emergency_latch()
        if buttons.estop_raw_pressed():
            buttons.latch_emergency("EMERGENCY_BEFORE_MOUTH_TRACKING")
            arm.stop()
            return
        buttons.wait_for_feed_release()

    if not use_fake_tof():
        start_tof_reader()

    mp_face = mp.solutions.face_mesh
    face_mesh = mp_face.FaceMesh(
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
    deadline = time.time() + float(os.environ.get("MOUTH_SESSION_TIMEOUT", "90"))

    logger.info(
        "Mouth tracking started (hold=%.1fs, stop_dist=%.1fcm, fake_tof=%s)",
        CENTER_HOLD_SECONDS,
        STOP_DISTANCE_CM,
        use_fake_tof(),
    )

    try:
        while time.time() < deadline:
            now = time.time()

            if _estop_during_motion(buttons, arm, "EMERGENCY_BUTTON_MOUTH_TRACKING"):
                break

            if buttons is not None and buttons.feed_raw_pressed():
                logger.info("[FEED] Feed pressed again — exiting mouth tracking")
                arm.stop()
                time.sleep(0.5)
                break

            tof_reading = read_tof_cm_safe()
            if tof_reading is not None:
                last_valid_tof_cm = tof_reading

            ret, frame = cap.read()
            if not ret:
                time.sleep(LOOP_DELAY)
                continue

            frame = cv2.resize(frame, (CAMERA_WIDTH, CAMERA_HEIGHT))
            h, w, _ = frame.shape
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = face_mesh.process(rgb)

            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                mx, my = get_mouth_center(landmarks, w, h)
                cx, cy = w // 2, h // 2
                error_x = mx - cx
                error_y = my - cy
                is_centered = abs(error_x) < DEAD_ZONE_PX and abs(error_y) < DEAD_ZONE_PX

                if is_centered:
                    if center_start_time is None:
                        center_start_time = now
                    centered_duration = now - center_start_time
                    arm.feed_pause()

                    if centered_duration >= CENTER_HOLD_SECONDS and not approach_active:
                        logger.info("[MOUTH] Centered %.1fs — guarded Y approach allowed", centered_duration)
                        approach_active = True
                        approach_start_time = now
                        last_approach_command_time = 0.0
                else:
                    center_start_time = None
                    if approach_active:
                        logger.info("[APPROACH] Mouth left center — stopping approach")
                        arm.stop()
                    approach_active = False
                    approach_start_time = None

                    if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_ALIGN"):
                        break
                    _align_toward_mouth(arm, error_x, error_y)

                if approach_active:
                    if _estop_during_motion(buttons, arm, "EMERGENCY_DURING_APPROACH"):
                        approach_active = False
                        break

                    if approach_start_time is None:
                        approach_start_time = now

                    if now - approach_start_time > MAX_APPROACH_SECONDS:
                        logger.info("[APPROACH] Max approach time reached — stopping")
                        arm.stop()
                        approach_active = False

                    elif now - last_approach_command_time >= APPROACH_COMMAND_PERIOD:
                        tof_cm = last_valid_tof_cm

                        if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_APPROACH_COMMAND"):
                            approach_active = False
                            break

                        if tof_cm is None:
                            logger.info("[APPROACH] No valid ToF yet — holding")
                            arm.feed_pause()
                            last_approach_command_time = now

                        elif tof_cm <= STOP_DISTANCE_CM:
                            logger.info(
                                "[APPROACH] Stop distance reached: %.1f cm <= %.1f cm",
                                tof_cm,
                                STOP_DISTANCE_CM,
                            )
                            approach_active = False
                            arm.feed_pause()

                        else:
                            logger.info(
                                "[APPROACH] ToF=%.1f cm > %.1f cm — FEED step",
                                tof_cm,
                                STOP_DISTANCE_CM,
                            )
                            arm.feed()
                            last_approach_command_time = now
            else:
                if approach_active:
                    logger.info("[APPROACH] Face lost — stopping approach")
                    arm.stop()
                center_start_time = None
                approach_active = False
                approach_start_time = None

            time.sleep(LOOP_DELAY)

    finally:
        try:
            arm.stop()
        except Exception:
            pass
        cap.release()
        cv2.destroyAllWindows()
        face_mesh.close()
        stop_tof_reader()
        logger.info("Mouth tracking phase ended")


def execute_next_bite(section_num: int = 1, buttons: ButtonManager | None = None) -> None:
    section = int(section_num)
    if section < 1 or section > 4:
        raise ValueError(f"section must be 1-4, got {section}")

    if buttons is not None and buttons.is_emergency_latched():
        logger.warning("Skipping bite — emergency latched")
        return

    logger.info("=== BITE START section=%s ===", section)

    if _dry_run():
        logger.info("DRY_RUN next_bite: SECTION_PICK → VIEW_MOUTH → mouth track → VIEW_SELECTION")
        time.sleep(2.0)
        logger.info("=== BITE DONE (dry run) ===")
        return

    with PiArmClient() as arm:
        reply = arm.ping()
        logger.info("Pi ping: %s", reply)

        if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_SECTION_PICK"):
            return

        logger.info("Step 1/4: pick food from plate section %s", section)
        reply = arm.section_pick(section)
        logger.info("Pi: %s", reply)
        if reply.startswith("ERROR"):
            raise RuntimeError(reply)
        wait_after_move()

        if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_VIEW_MOUTH"):
            return

        logger.info("Step 2/4: move to mouth view")
        reply = arm.view_mouth()
        logger.info("Pi: %s", reply)
        wait_after_move(3.0)

        if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_MOUTH_SESSION"):
            return

        logger.info("Step 3/4: mouth tracking + ToF approach")
        run_mouth_feed_session(arm, buttons)

        if buttons is not None and buttons.is_emergency_latched():
            logger.warning("=== BITE ABORTED (emergency) section=%s ===", section)
            return

        logger.info("Step 4/4: return to plate view")
        reply = arm.view_selection()
        logger.info("Pi: %s", reply)
        wait_after_move()

    logger.info("=== BITE DONE section=%s ===", section)


def execute_stop() -> None:
    if _dry_run():
        logger.info("DRY_RUN stop")
        return
    with PiArmClient() as arm:
        arm.stop()


def execute_home() -> None:
    if _dry_run():
        logger.info("DRY_RUN home")
        return
    with PiArmClient() as arm:
        arm.view_selection()
