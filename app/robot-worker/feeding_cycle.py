"""
Complete feeding cycle for Jetson + Pi arm server.

One bite:
  1. SECTION_PICK   — arm to plate section, dip/scoop/lift
  2. VIEW_MOUTH     — move to feeding pose
  3. Mouth tracking — XZ_DELTA centering + FEED steps toward user
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

from pi_arm_client import PiArmClient, wait_after_move

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent

# ─── Camera / mouth tracking ─────────────────────────────────────────────────
CAMERA_ID = os.environ.get("CAMERA_ID", "/dev/video0")
CAMERA_WIDTH = int(os.environ.get("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "480"))
DEAD_ZONE_PX = int(os.environ.get("DEAD_ZONE_PX", "30"))
MAX_STEP_MM = float(os.environ.get("MAX_STEP_MM", "5.0"))
STABLE_SECONDS = float(os.environ.get("STABLE_SECONDS", "2.0"))
LOOP_DELAY = float(os.environ.get("LOOP_DELAY", "0.15"))
FEED_INTERVAL = float(os.environ.get("FEED_INTERVAL", "0.6"))
FEED_STEPS_PER_BITE = int(os.environ.get("FEED_STEPS_PER_BITE", "6"))
INVERT_X = os.environ.get("INVERT_X", "false").lower() in ("1", "true", "yes")
INVERT_Y = os.environ.get("INVERT_Y", "false").lower() in ("1", "true", "yes")

LIPS_OUTER = [
    61, 185, 40, 39, 37, 0, 267, 269, 270, 409,
    291, 375, 321, 405, 314, 17, 84, 181, 91, 146,
]

MODEL_PATH = ROOT_DIR / "face_landmarker.task"


def _dry_run() -> bool:
    return os.environ.get("DRY_RUN", "true").lower() in ("1", "true", "yes")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def pixel_offset_to_mm(offset_px: float, dead_zone_px: float = DEAD_ZONE_PX, max_mm: float = MAX_STEP_MM) -> float:
    if dead_zone_px <= 0:
        return 0.0
    mm = (offset_px / dead_zone_px) * max_mm
    return clamp(mm, -max_mm, max_mm)


def mouth_centroid(landmarks, w: int, h: int) -> tuple[int, int]:
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in LIPS_OUTER]
    cx = int(sum(p[0] for p in pts) / len(pts))
    cy = int(sum(p[1] for p in pts) / len(pts))
    return cx, cy


def _ensure_face_model() -> None:
    if MODEL_PATH.exists():
        return
    import urllib.request

    logger.info("Downloading face_landmarker.task ...")
    urllib.request.urlretrieve(
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task",
        MODEL_PATH,
    )


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


def calibrate_plate(*, preview: bool = False) -> dict:
    """Run AprilTag + ToF plate scan; writes latest_plate_scan.py."""
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


def _xz_delta_toward_mouth(arm: PiArmClient, offset_x: int, offset_y: int) -> None:
    ox, oy = offset_x, offset_y
    if INVERT_X:
        ox = -ox
    if INVERT_Y:
        oy = -oy
    dx_mm = pixel_offset_to_mm(ox)
    dz_mm = pixel_offset_to_mm(-oy)
    if abs(dx_mm) < 0.05 and abs(dz_mm) < 0.05:
        return
    arm.xz_delta(dx_mm, dz_mm)
    time.sleep(LOOP_DELAY)


def run_mouth_feed_session(arm: PiArmClient) -> None:
    """
    Center mouth with XZ_DELTA, then send FEED steps toward the user.
    Blocks until centered + FEED_STEPS_PER_BITE forward steps, or timeout.
    """
    if _dry_run():
        logger.info("DRY_RUN mouth_feed_session (%s FEED steps)", FEED_STEPS_PER_BITE)
        time.sleep(2.0)
        return

    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    _ensure_face_model()

    cap = cv2.VideoCapture(CAMERA_ID, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera {CAMERA_ID}")

    base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    detector = vision.FaceLandmarker.create_from_options(options)

    stable_since: float | None = None
    feed_steps = 0
    last_feed_at = 0.0
    feeding = False
    deadline = time.time() + float(os.environ.get("MOUTH_SESSION_TIMEOUT", "90"))

    logger.info("Mouth feed session started (target %s FEED steps)", FEED_STEPS_PER_BITE)

    try:
        while time.time() < deadline and feed_steps < FEED_STEPS_PER_BITE:
            ret, frame = cap.read()
            if not ret:
                time.sleep(LOOP_DELAY)
                continue

            h, w = frame.shape[:2]
            cam_cx, cam_cy = w // 2, h // 2
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = detector.detect(mp_image)
            faces = result.face_landmarks if result.face_landmarks else []

            if len(faces) != 1:
                stable_since = None
                if feeding:
                    arm.feed_pause()
                    feeding = False
                time.sleep(LOOP_DELAY)
                continue

            face = faces[0]
            mx, my = mouth_centroid(face, w, h)
            offset_x = mx - cam_cx
            offset_y = my - cam_cy
            distance = (offset_x ** 2 + offset_y ** 2) ** 0.5
            centered = distance <= DEAD_ZONE_PX

            if not centered:
                stable_since = None
                if feeding:
                    arm.feed_pause()
                    feeding = False
                _xz_delta_toward_mouth(arm, offset_x, offset_y)
                continue

            if stable_since is None:
                stable_since = time.time()
                logger.info("Mouth centered — starting stability timer")

            elapsed = time.time() - stable_since
            if not feeding and elapsed >= STABLE_SECONDS:
                arm.feed()
                feeding = True
                feed_steps += 1
                last_feed_at = time.time()
                logger.info("FEED step %s/%s", feed_steps, FEED_STEPS_PER_BITE)
            elif feeding and time.time() - last_feed_at >= FEED_INTERVAL:
                arm.feed()
                feed_steps += 1
                last_feed_at = time.time()
                logger.info("FEED step %s/%s", feed_steps, FEED_STEPS_PER_BITE)

            time.sleep(LOOP_DELAY)

        if feed_steps < FEED_STEPS_PER_BITE:
            logger.warning(
                "Mouth session ended early: %s/%s FEED steps",
                feed_steps,
                FEED_STEPS_PER_BITE,
            )
    finally:
        try:
            arm.feed_pause()
        except Exception:
            pass
        cap.release()
        cv2.destroyAllWindows()

    logger.info("Mouth feed session complete (%s FEED steps)", feed_steps)


def execute_next_bite(section_num: int = 1) -> None:
    """Run one full pick → mouth track → feed → return cycle."""
    section = int(section_num)
    if section < 1 or section > 4:
        raise ValueError(f"section must be 1-4, got {section}")

    logger.info("=== BITE START section=%s ===", section)

    if _dry_run():
        logger.info(
            "DRY_RUN next_bite: SECTION_PICK → VIEW_MOUTH → mouth feed → VIEW_SELECTION"
        )
        time.sleep(2.0)
        logger.info("=== BITE DONE (dry run) ===")
        return

    with PiArmClient() as arm:
        reply = arm.ping()
        logger.info("Pi ping: %s", reply)

        logger.info("Step 1/4: pick food from plate section %s", section)
        reply = arm.section_pick(section)
        logger.info("Pi: %s", reply)
        if reply.startswith("ERROR"):
            raise RuntimeError(reply)
        wait_after_move()

        logger.info("Step 2/4: move to mouth view")
        reply = arm.view_mouth()
        logger.info("Pi: %s", reply)
        wait_after_move(3.0)

        logger.info("Step 3/4: mouth tracking + feed")
        run_mouth_feed_session(arm)

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
