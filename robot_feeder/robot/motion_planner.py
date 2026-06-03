"""Feeding motion: plate → scoop → user → home (jetson_controller sequence)."""

from __future__ import annotations

import copy
import logging
from typing import TYPE_CHECKING

from robot.coordinates import (
    HOME_COORDS,
    SCOOP_Z_DELTA_MM,
    SECTION_PLATE,
    USER_FEED,
)

if TYPE_CHECKING:
    from robot.mycobot_controller import MyCobotController

logger = logging.getLogger(__name__)


class MotionPlanner:
    def __init__(self, robot: "MyCobotController") -> None:
        self.robot = robot

    @staticmethod
    def _scoop_pose(plate_coords: list[float]) -> list[float]:
        pose = copy.deepcopy(plate_coords)
        pose[2] += SCOOP_Z_DELTA_MM
        return pose

    def execute_bite(self, section: int) -> None:
        plate = SECTION_PLATE.get(section, SECTION_PLATE[1])
        speed = 30

        logger.info("bite section=%s plate=%s", section, plate)
        self.robot.move_coords(plate, speed=speed)
        self.robot.wait_until_done(2.0)

        scoop = self._scoop_pose(plate)
        self.robot.move_coords(scoop, speed=speed)
        self.robot.wait_until_done(1.5)
        self.robot.move_coords(plate, speed=speed)
        self.robot.wait_until_done(1.0)

        self.robot.move_coords(USER_FEED, speed=speed)
        self.robot.wait_until_done(2.0)
        self.robot.wait(1.0)

        self.robot.move_coords(HOME_COORDS, speed=speed)
        self.robot.wait_until_done(2.0)

    def go_home(self) -> None:
        self.robot.go_home()
        self.robot.wait_until_done(2.0)
