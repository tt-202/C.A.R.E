#!/usr/bin/env python3
"""C.A.R.E on-robot feeder: perception, state machine, Firestore command bridge."""

from __future__ import annotations

import threading

from config import load_settings
from states.state_machine import FeederStateMachine
from robot.mycobot_controller import create_robot_controller
from perception.camera import Camera
from perception.yolo_detector import YoloDetector
from perception.mediapipe_face import FaceTracker
from perception.tof_sensor import TOFSensor
from perception.april_tag_detector import AprilTagDetector, parse_section_map
from app_bridge.firebase_client import FirebaseClient
from sensors.gpio_buttons import ButtonManager
from utils.logger import setup_logging


def main() -> None:
    setup_logging()
    settings = load_settings()
    import logging

    log = logging.getLogger("robot_feeder")
    if settings.arm_backend in ("pi_socket", "socket", "pi"):
        log.info(
            "Arm backend=pi_socket target=%s:%s dry_run=%s",
            settings.arm_server_host,
            settings.arm_server_port,
            settings.dry_run,
        )
    else:
        log.info("Arm backend=serial port=%s dry_run=%s", settings.mycobot_port, settings.dry_run)

    display = None
    machine_holder: list[FeederStateMachine] = []

    def on_manual_section(section: int) -> None:
        if not machine_holder:
            return
        ctx = machine_holder[0].ctx
        ctx.selected_section = section
        ctx.section_source = f"Manual (LCD) → Section {section}"
        ctx.last_tag_id = None
        if ctx.display is not None:
            ctx.display.update(section=section, section_source=ctx.section_source)

    apriltag = None
    if settings.apriltag_enabled:
        apriltag = AprilTagDetector(
            tag_to_section=parse_section_map(settings.apriltag_section_map),
            family=settings.apriltag_family,
        )

    robot = create_robot_controller(settings)
    camera = Camera(device_id=settings.camera_device_id)
    yolo = YoloDetector(model_path=settings.yolo_model_path)
    face = FaceTracker()
    tof = TOFSensor()
    firebase = FirebaseClient(
        robot_id=settings.robot_id,
        credentials_path=settings.firebase_credentials,
    )
    buttons = ButtonManager(enabled=settings.buttons_enabled)

    machine = FeederStateMachine(
        robot=robot,
        camera=camera,
        yolo=yolo,
        face=face,
        tof=tof,
        firebase=firebase,
        buttons=buttons,
        display=None,
        apriltag=apriltag,
        apriltag_enabled=settings.apriltag_enabled,
        loop_hz=settings.loop_hz,
    )
    machine_holder.append(machine)

    if settings.gui_enabled:
        try:
            from gui.operator_panel import OperatorDisplay

            display = OperatorDisplay(
                image_dir=settings.gui_image_dir,
                fullscreen=settings.gui_fullscreen,
                on_manual_section=on_manual_section,
            )
            display.setup()
            machine.ctx.display = display
        except Exception as e:
            import logging

            logging.getLogger("robot_feeder").warning("GUI disabled: %s", e)
            display = None

    feeder = threading.Thread(target=machine.run, name="feeder", daemon=True)

    try:
        if display is not None:
            feeder.start()
            display.run_mainloop()
        else:
            machine.run()
    except KeyboardInterrupt:
        pass
    finally:
        if display is not None:
            display.stop()
        robot.stop()
        robot.go_home()
        if hasattr(robot, "close"):
            robot.close()


if __name__ == "__main__":
    main()
