#!/usr/bin/env python3
"""Step 4: arm motion (DRY_RUN logs poses; set DRY_RUN=false on Jetson with arm connected)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import load_settings
from robot.motion_planner import MotionPlanner
from robot.mycobot_controller import MyCobotController


def main() -> int:
    settings = load_settings()
    print(f"DRY_RUN={settings.dry_run} port={settings.mycobot_port}")
    if settings.dry_run:
        print("  Arm will NOT move while DRY_RUN is true.")
        print("  Fix: in robot_feeder/.env set DRY_RUN=false")
        print("  Or run: DRY_RUN=false python scripts/test_arm_motion.py")
        print("  If .env is correct but this stays true: unset DRY_RUN  # shell override")
    if not settings.dry_run:
        confirm = input("Arm will move. Type YES to continue: ")
        if confirm.strip() != "YES":
            print("Aborted.")
            return 0

    robot = MyCobotController(
        port=settings.mycobot_port,
        baud=settings.mycobot_baud,
        dry_run=settings.dry_run,
    )
    robot.connect()
    planner = MotionPlanner(robot)

    for section in (1, 2, 3, 4):
        print(f"\n--- execute_bite(section={section}) ---")
        planner.execute_bite(section)

    print("\n--- go_home ---")
    planner.go_home()
    robot.stop()
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
