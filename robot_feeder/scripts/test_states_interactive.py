#!/usr/bin/env python3
"""
Step 7: full state machine in DRY_RUN — press Enter to trigger one feed cycle, or type commands.

Commands: feed | stop | home | plate | q
"""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import load_settings
from utils.logger import setup_logging
from robot.mycobot_controller import MyCobotController
from perception.camera import Camera
from perception.yolo_detector import YoloDetector
from perception.mediapipe_face import FaceTracker
from perception.tof_sensor import TOFSensor
from app_bridge.firebase_client import FirebaseClient
from sensors.gpio_buttons import ButtonManager
from states.state_machine import FeederStateMachine


def main() -> int:
    setup_logging()
    logging.getLogger().setLevel(logging.DEBUG)
    settings = load_settings()

    import os

    os.environ["DRY_RUN"] = "true"

    robot = MyCobotController(
        port=settings.mycobot_port,
        baud=settings.mycobot_baud,
        dry_run=True,
    )
    machine = FeederStateMachine(
        robot=robot,
        camera=Camera(settings.camera_device_id),
        yolo=YoloDetector(settings.yolo_model_path),
        face=FaceTracker(),
        tof=TOFSensor(),
        firebase=FirebaseClient(settings.robot_id, settings.firebase_credentials),
        buttons=ButtonManager(enabled=settings.buttons_enabled),
        loop_hz=2.0,
    )

    def stdin_loop() -> None:
        print("Commands: feed | stop | home | plate | q")
        while True:
            line = sys.stdin.readline()
            if not line:
                break
            cmd = line.strip().lower()
            ctx = machine.ctx
            if cmd == "q":
                os._exit(0)
            if cmd == "feed":
                ctx.request_feed = True
                print("→ request_feed")
            elif cmd == "stop":
                ctx.emergency = True
                ctx.pending_firebase_cmd = ("stop", None)
                print("→ emergency/stop")
            elif cmd == "home":
                ctx.planner.go_home()
                print("→ home")
            elif cmd == "plate":
                ctx.selected_section = (ctx.selected_section % 4) + 1
                print(f"→ section {ctx.selected_section}")
            else:
                print("Unknown. Use: feed | stop | home | plate | q")

    threading.Thread(target=stdin_loop, daemon=True).start()

    print("Starting state machine (DRY_RUN). Watch logs for IDLE → DETECT_MOUTH → FEED → RETRACT")
    try:
        machine.run()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
