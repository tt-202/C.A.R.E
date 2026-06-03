#!/usr/bin/env python3
"""Step 1: verify camera opens and shows a live preview. Press Q to quit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import load_settings
from perception.camera import Camera


def main() -> int:
    settings = load_settings()
    cam = Camera(device_id=settings.camera_device_id)
    if not cam.open():
        print("FAIL: could not open camera. On Jetson, try CAMERA_DEVICE_ID=0 and install opencv.")
        return 1

    import cv2

    print("OK: camera open. Press Q in the window to exit.")
    while True:
        ok, frame = cam.read()
        if not ok or frame is None:
            print("WARN: empty frame")
            continue
        cv2.imshow("robot_feeder — test_camera", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cam.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
