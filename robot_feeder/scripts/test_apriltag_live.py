#!/usr/bin/env python3
"""Live AprilTag → section 1–4 overlay (same as plate selection in main.py). Press Q to quit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import load_settings
from perception.april_tag_detector import AprilTagDetector, parse_section_map
from perception.camera import Camera


def main() -> int:
    settings = load_settings()
    cam = Camera(device_id=settings.camera_device_id)
    if not cam.open():
        print("FAIL: camera")
        return 1

    tags = AprilTagDetector(
        tag_to_section=parse_section_map(settings.apriltag_section_map),
        family=settings.apriltag_family,
    )
    if not tags.load():
        print("FAIL: pip install pupil-apriltags opencv-python")
        return 1

    import cv2

    print("Point camera at plate tags. Map:", tags.tag_to_section)
    print("Press Q to quit.")
    while True:
        ok, frame = cam.read()
        if not ok or frame is None:
            continue
        pick = tags.pick_section(frame)
        frame = tags.draw_overlay(frame)
        if pick:
            label = f"SELECTED: Section {pick.section} (tag {pick.tag_id})"
            color = (0, 255, 0)
        else:
            label = "No mapped AprilTag in view"
            color = (0, 0, 255)
        cv2.putText(frame, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
        cv2.imshow("robot_feeder — test_apriltag_live", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cam.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
