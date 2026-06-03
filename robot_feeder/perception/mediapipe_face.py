"""Face / mouth tracking for alignment (MediaPipe when available)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class FaceState:
    detected: bool
    is_open: bool
    offset_x: float
    offset_y: float


class FaceTracker:
    def __init__(self) -> None:
        self._face_mesh: Any = None

    def load(self) -> bool:
        try:
            import mediapipe as mp  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("mediapipe not installed — face tracking disabled")
            return False
        self._face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        return True

    def track(self, frame: Any) -> FaceState:
        if self._face_mesh is None or frame is None:
            return FaceState(False, False, 0.0, 0.0)

        import cv2

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._face_mesh.process(rgb)
        if not result.multi_face_landmarks:
            return FaceState(False, False, 0.0, 0.0)

        lm = result.multi_face_landmarks[0].landmark
        # Approximate mouth openness from upper/lower lip landmarks.
        upper = lm[13]
        lower = lm[14]
        mouth_open = abs(upper.y - lower.y) > 0.02
        nose = lm[1]
        offset_x = nose.x - 0.5
        offset_y = nose.y - 0.5
        return FaceState(True, mouth_open, offset_x, offset_y)
