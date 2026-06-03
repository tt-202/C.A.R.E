"""Orchestrates feeding states and Firebase command injection."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app_bridge.firebase_client import FirebaseClient
from app_bridge.meal_scheduler import MealScheduler
from data.bite_counter import BiteCounter
from data.meal_log import MealLog
from perception.camera import Camera
from perception.mediapipe_face import FaceState, FaceTracker
from perception.tof_sensor import TOFSensor
from perception.april_tag_detector import AprilTagDetector
from perception.yolo_detector import YoloDetector
from robot.motion_planner import MotionPlanner
from robot.mycobot_controller import MyCobotController
from robot.safety import SafetyMonitor
from sensors.gpio_buttons import ButtonManager, ButtonPoller
from gui.display_bridge import sync_display
from states.base import FeederStateName
from states.detect_mouth import DetectMouthState
from states.select_plate import SelectPlateState
from states.emergency import EmergencyState
from states.feed import FeedState
from states.idle import IdleState
from states.retract import RetractState


@dataclass
class FeederContext:
    robot: MyCobotController
    camera: Camera
    yolo: YoloDetector
    face: FaceTracker
    tof: TOFSensor
    firebase: FirebaseClient
    planner: MotionPlanner
    safety: SafetyMonitor
    bites: BiteCounter
    meal_log: MealLog
    scheduler: MealScheduler
    buttons: ButtonManager | None = None
    display: Any = None  # gui.operator_panel.OperatorDisplay | None
    apriltag: AprilTagDetector | None = None
    last_tag_id: int | None = None
    section_source: str = "—"
    apriltag_select_failed: bool = False
    apriltag_enabled: bool = False
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("feeder.ctx"))
    pending_firebase_cmd: tuple[str, dict[str, Any] | None] | None = None
    firebase_payload: dict[str, Any] | None = None
    request_feed: bool = False
    emergency: bool = False
    food_detected: bool = False
    face_state: FaceState | None = None
    tof_mm: int | None = None
    selected_section: int = 1


class FeederStateMachine:
    def __init__(
        self,
        *,
        robot: MyCobotController,
        camera: Camera,
        yolo: YoloDetector,
        face: FaceTracker,
        tof: TOFSensor,
        firebase: FirebaseClient,
        buttons: ButtonManager | None = None,
        display: Any = None,
        apriltag: AprilTagDetector | None = None,
        apriltag_enabled: bool = False,
        loop_hz: float = 10.0,
    ) -> None:
        self.ctx = FeederContext(
            robot=robot,
            camera=camera,
            yolo=yolo,
            face=face,
            tof=tof,
            firebase=firebase,
            buttons=buttons,
            display=display,
            apriltag=apriltag,
            apriltag_enabled=apriltag_enabled,
            planner=MotionPlanner(robot),
            safety=SafetyMonitor(),
            bites=BiteCounter(),
            meal_log=MealLog(),
            scheduler=MealScheduler(),
        )
        self._states = {
            FeederStateName.IDLE: IdleState(),
            FeederStateName.SELECT_PLATE: SelectPlateState(),
            FeederStateName.DETECT_MOUTH: DetectMouthState(),
            FeederStateName.FEED: FeedState(),
            FeederStateName.RETRACT: RetractState(),
            FeederStateName.EMERGENCY: EmergencyState(),
        }
        self._current_name = FeederStateName.IDLE
        self._period = 1.0 / loop_hz
        self._button_poller: ButtonPoller | None = None

    def _handle_firebase_command(self, cmd: str, payload: dict[str, Any] | None) -> None:
        if cmd in ("pause", "stop"):
            self.ctx.emergency = True
            self.ctx.pending_firebase_cmd = ("stop", payload)
            return
        if cmd == "home":
            self.ctx.planner.go_home()
            return
        self.ctx.pending_firebase_cmd = (cmd, payload)

    def _check_gpio_estop(self) -> bool:
        buttons = self.ctx.buttons
        if buttons is None:
            return False
        if buttons.estop_pressed() or buttons.estop_held():
            self.ctx.emergency = True
            return True
        return False

    def run(self) -> None:
        self.ctx.robot.connect()
        self.ctx.camera.open()
        self.ctx.yolo.load()
        self.ctx.face.load()
        if self.ctx.apriltag is not None:
            self.ctx.apriltag.load()

        if self.ctx.buttons is not None:
            self.ctx.buttons.setup()
            self._button_poller = ButtonPoller(self.ctx.buttons)
            self._button_poller.start()

        slot = self.ctx.scheduler.active_slot()
        self.ctx.meal_log.start(slot.label)

        firebase_ok = self.ctx.firebase.connect()
        if self.ctx.display is not None:
            self.ctx.display.update(connected=firebase_ok, state="IDLE", error="NONE")
        if firebase_ok:
            self.ctx.firebase.listen(self._handle_firebase_command)

        state = self._states[self._current_name]
        sync_display(self.ctx, self._current_name)
        state.enter(self.ctx)

        try:
            while True:
                if self._check_gpio_estop() and self._current_name != FeederStateName.EMERGENCY:
                    next_name = FeederStateName.EMERGENCY
                else:
                    next_name = state.tick(self.ctx)

                if next_name is not None and next_name != self._current_name:
                    state.exit(self.ctx)
                    self._current_name = next_name
                    state = self._states[self._current_name]
                    sync_display(self.ctx, self._current_name)
                    state.enter(self.ctx)
                time.sleep(self._period)
        except KeyboardInterrupt:
            self.ctx.meal_log.end()
            raise
        finally:
            if self._button_poller is not None:
                self._button_poller.stop()
            if self.ctx.buttons is not None:
                self.ctx.buttons.cleanup()
