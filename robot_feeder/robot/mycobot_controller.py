"""Thin wrapper around pymycobot for myCobot 320 (direct serial on Jetson)."""

from __future__ import annotations

import logging
import time
from typing import Any, TYPE_CHECKING

from robot.coordinates import HOME_COORDS

if TYPE_CHECKING:
    from config import Settings

logger = logging.getLogger(__name__)

ArmController = Any  # MyCobotController | PiArmSocketController


class MyCobotController:
    def __init__(self, port: str = "/dev/ttyAMA0", baud: int = 115200, *, dry_run: bool = True) -> None:
        self.port = port
        self.baud = baud
        self.dry_run = dry_run
        self._arm: Any = None

    def connect(self) -> None:
        if self.dry_run:
            logger.info("DRY_RUN: skipping pymycobot connect on %s", self.port)
            return
        try:
            from pymycobot.mycobot320 import MyCobot320  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("pymycobot not installed; pip install pymycobot or set DRY_RUN=true") from e
        self._arm = MyCobot320(self.port, self.baud)
        logger.info("Connected to myCobot on %s", self.port)

    def stop(self) -> None:
        if self.dry_run or self._arm is None:
            logger.info("DRY_RUN stop")
            return
        self._arm.stop()

    def go_home(self) -> None:
        self.move_coords(HOME_COORDS, speed=30)

    def move_coords(self, coords: list[float], *, speed: int = 30, mode: int = 0) -> None:
        if self.dry_run or self._arm is None:
            logger.info("DRY_RUN move_coords %s speed=%s", coords, speed)
            time.sleep(0.3)
            return
        self._arm.send_coords(coords, speed, mode)

    def move_angles(self, angles: list[float], *, speed: int = 35) -> None:
        if self.dry_run or self._arm is None:
            logger.info("DRY_RUN move_angles %s speed=%s", angles, speed)
            time.sleep(0.2)
            return
        self._arm.send_angles(angles, speed)

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def wait_until_done(self, seconds: float = 2.0) -> None:
        """Fixed wait after coord moves (replace with encoder feedback if available)."""
        self.wait(seconds)


def create_robot_controller(settings: "Settings") -> ArmController:
    """Serial on Jetson, or TCP to pi_arm_server on myCobot 320 Pi."""
    backend = settings.arm_backend.strip().lower()
    if backend in ("pi_socket", "socket", "pi"):
        from robot.arm_socket_client import PiArmSocketController

        return PiArmSocketController(
            host=settings.arm_server_host,
            port=settings.arm_server_port,
            dry_run=settings.dry_run,
        )
    return MyCobotController(
        port=settings.mycobot_port,
        baud=settings.mycobot_baud,
        dry_run=settings.dry_run,
    )
