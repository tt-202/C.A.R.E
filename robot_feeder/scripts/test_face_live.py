#!/usr/bin/env python3
"""Step 3: camera + MediaPipe face/mouth. Press Q to quit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import load_settings
from perception.camera import Camera
from perception.mediapipe_face import FaceTracker


def main() -> int:
    settings = load_settings()
    cam = Camera(device_id=settings.camera_device_id)
    if not cam.open():
        print("FAIL: camera")
        return 1

    face = FaceTracker()
    if not face.load():
        print("FAIL: mediapipe not installed — pip install mediapipe opencv-python")
        return 1

    import cv2

    print("OK: face tracker. Press Q to quit.")
    while True:
        ok, frame = cam.read()
        if not ok or frame is None:
            continue
        state = face.track(frame)
        text = (
            f"face={state.detected} mouth_open={state.is_open} "
            f"dx={state.offset_x:.2f} dy={state.offset_y:.2f}"
        )
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow("robot_feeder — test_face_live", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cam.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
