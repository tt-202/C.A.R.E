"""Environment-driven settings for the Jetson feeder process."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    robot_id: str
    mycobot_port: str
    mycobot_baud: int
    dry_run: bool
    camera_device_id: int
    yolo_model_path: str
    firebase_credentials: str | None
    loop_hz: float
    buttons_enabled: bool
    gui_enabled: bool
    gui_fullscreen: bool
    gui_image_dir: str | None
    apriltag_enabled: bool
    apriltag_family: str
    apriltag_section_map: str


def load_settings() -> Settings:
    return Settings(
        robot_id=os.environ.get("ROBOT_ID", "care-01").strip() or "care-01",
        mycobot_port=os.environ.get("MYCOBOT_PORT", "/dev/ttyUSB0"),
        mycobot_baud=int(os.environ.get("MYCOBOT_BAUD", "115200")),
        dry_run=_env_bool("DRY_RUN", default=True),
        camera_device_id=int(os.environ.get("CAMERA_DEVICE_ID", "0")),
        yolo_model_path=os.environ.get("YOLO_MODEL_PATH", "models/food.pt"),
        firebase_credentials=os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        loop_hz=float(os.environ.get("FEEDER_LOOP_HZ", "10")),
        buttons_enabled=_env_bool("BUTTONS_ENABLED", default=False),
        gui_enabled=_env_bool("GUI_ENABLED", default=False),
        gui_fullscreen=_env_bool("GUI_FULLSCREEN", default=False),
        gui_image_dir=os.environ.get("GUI_IMAGE_DIR") or None,
        apriltag_enabled=_env_bool("APRILTAG_ENABLED", default=True),
        apriltag_family=os.environ.get("APRILTAG_FAMILY", "tag36h11"),
        apriltag_section_map=os.environ.get(
            "APRILTAG_SECTION_MAP",
            "1:1,2:2,3:3,4:4",
        ),
    )
