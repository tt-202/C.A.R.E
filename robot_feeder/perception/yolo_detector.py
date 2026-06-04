"""Food detection via YOLO (Ultralytics)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class YoloDetector:
    def __init__(self, model_path: str = "perception/best.pt") -> None:
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

    # Class names in perception/best.pt (custom train)
    FOOD_CLASS_NAMES = frozenset({"Plate with food", "Spoon with food"})

    def detect_food(self, frame: Any) -> bool:
        """True if model sees plate or spoon with food (not empty plate/spoon)."""
        if self._model is None or frame is None:
            return False
        results = self._model(frame, verbose=False)
        if not results:
            return False
        boxes = results[0].boxes
        if boxes is None or len(boxes) == 0:
            return False
        names = self._model.names or {}
        for cls_id in boxes.cls.tolist():
            label = names.get(int(cls_id), "")
            if label in self.FOOD_CLASS_NAMES:
                return True
        return False
