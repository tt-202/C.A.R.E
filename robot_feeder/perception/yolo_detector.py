"""Food detection via YOLO (Ultralytics)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class YoloDetector:
    def __init__(self, model_path: str = "models/food.pt") -> None:
        self.model_path = model_path
        self._model: Any = None

    def load(self) -> bool:
        path = Path(self.model_path)
        if not path.is_file():
            logger.warning("YOLO model not found at %s — detection disabled", path)
            return False
        try:
            from ultralytics import YOLO  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("ultralytics not installed — detection disabled")
            return False
        self._model = YOLO(str(path))
        logger.info("Loaded YOLO model %s", path)
        return True

    def detect_food(self, frame: Any) -> bool:
        """Return True if at least one food-class detection is present."""
        if self._model is None or frame is None:
            return False
        results = self._model(frame, verbose=False)
        if not results:
            return False
        boxes = results[0].boxes
        return boxes is not None and len(boxes) > 0
