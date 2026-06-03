"""Camera capture (USB or Jetson CSI via GStreamer when available)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self, device_id: int = 0) -> None:
        self.device_id = device_id
        self._cap: Any = None

    @staticmethod
    def gstreamer_pipeline(
        sensor_id: int = 0,
        *,
        capture_width: int = 1280,
        capture_height: int = 720,
        display_width: int = 1280,
        display_height: int = 720,
        framerate: int = 30,
        flip_method: int = 0,
    ) -> str:
        return (
            "nvarguscamerasrc sensor-id=%d ! "
            "video/x-raw(memory:NVMM), width=(int)%d, height=(int)%d, "
            "framerate=(fraction)%d/1 ! "
            "nvvidconv flip-method=%d ! "
            "video/x-raw, width=(int)%d, height=(int)%d, format=(string)BGRx ! "
            "videoconvert ! video/x-raw, format=(string)BGR ! appsink"
            % (
                sensor_id,
                capture_width,
                capture_height,
                framerate,
                flip_method,
                display_width,
                display_height,
            )
        )

    def open(self) -> bool:
        try:
            import cv2
        except ImportError:
            logger.warning("opencv not installed; camera disabled")
            return False

        pipeline = self.gstreamer_pipeline(self.device_id)
        cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if cap.isOpened():
            self._cap = cap
            logger.info("Opened Jetson CSI camera sensor-id=%s", self.device_id)
            return True

        cap = cv2.VideoCapture(self.device_id)
        if cap.isOpened():
            self._cap = cap
            logger.info("Opened USB camera device_id=%s", self.device_id)
            return True

        logger.error("Unable to open camera")
        return False

    def read(self) -> tuple[bool, Any]:
        if self._cap is None:
            return False, None
        return self._cap.read()

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None
