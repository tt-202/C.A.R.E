#!/usr/bin/env python3
"""Ping Pi arm server (myCobot 320 Pi). Run pi_arm_server_xz_delta.py on the Pi first."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import load_settings
from robot.mycobot_controller import create_robot_controller


def main() -> int:
    settings = load_settings()
    print(f"ARM_BACKEND={settings.arm_backend} host={settings.arm_server_host}:{settings.arm_server_port}")
    print(f"DRY_RUN={settings.dry_run}")

    if settings.arm_backend not in ("pi_socket", "socket", "pi"):
        print("Set ARM_BACKEND=pi_socket in .env for this test.")
        return 1

    if settings.dry_run:
        print("DRY_RUN=true — commands will be logged only. Set DRY_RUN=false to hit the Pi.")

    robot = create_robot_controller(settings)
    robot.connect()
    print("PING OK")

    if not settings.dry_run:
        confirm = input("Send MOVE_COORDS to HOME? Type YES: ")
        if confirm.strip() != "YES":
            print("Skipped motion.")
            return 0
        robot.go_home()
        print("HOME sent.")

    if hasattr(robot, "close"):
        robot.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
