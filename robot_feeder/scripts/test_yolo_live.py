#!/usr/bin/env python3
"""Step 2: camera + YOLO — live boxes and food-detected flag. Press Q to quit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import load_settings
from perception.camera import Camera
from perception.yolo_detector import YoloDetector


def main() -> int:
    settings = load_settings()
    cam = Camera(device_id=settings.camera_device_id)
    if not cam.open():
        print("FAIL: camera")
        return 1

    yolo = YoloDetector(model_path=settings.yolo_model_path)
    if not yolo.load():
        print(f"FAIL: YOLO model at {settings.yolo_model_path}")
        print("  Set YOLO_MODEL_PATH=perception/best.pt in robot_feeder/.env")
        return 1

    import cv2

    print("OK: YOLO loaded. Green text = food detected. Press Q to quit.")
    while True:
        ok, frame = cam.read()
        if not ok or frame is None:
            continue
        food = yolo.detect_food(frame)
        if yolo._model is not None:
            results = yolo._model(frame, verbose=False)
            frame = results[0].plot()
        label = "FOOD: YES" if food else "FOOD: no"
        color = (0, 255, 0) if food else (0, 0, 255)
        cv2.putText(frame, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, color, 2)
        cv2.imshow("robot_feeder — test_yolo_live", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cam.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
