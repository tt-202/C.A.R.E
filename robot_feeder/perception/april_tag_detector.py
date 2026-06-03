"""
AprilTag detection for 4 plate sections.

Put one printed tag per quadrant on the plate (default family tag36h11).
Map physical tag IDs → section 1–4 via APRILTAG_SECTION_MAP in .env
  e.g. APRILTAG_SECTION_MAP=10:1,11:2,12:3,13:4

Selection rule: among visible mapped tags, pick the one closest to the
camera image center (plate center in view).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AprilTagDetection:
    tag_id: int
    section: int
    center_x: float
    center_y: float
    distance_to_center: float


@dataclass
class PlateSelection:
    section: int
    tag_id: int
    all_detections: list[AprilTagDetection]


def parse_section_map(raw: str) -> dict[int, int]:
    """Parse '10:1,11:2,12:3,13:4' → {10: 1, 11: 2, ...}."""
    mapping: dict[int, int] = {}
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        tag_s, sec_s = part.split(":", 1)
        try:
            tag_id = int(tag_s.strip())
            section = int(sec_s.strip())
            if 1 <= section <= 4:
                mapping[tag_id] = section
        except ValueError:
            continue
    if not mapping:
        mapping = {1: 1, 2: 2, 3: 3, 4: 4}
    return mapping


class AprilTagDetector:
    def __init__(
        self,
        *,
        tag_to_section: dict[int, int] | None = None,
        family: str = "tag36h11",
    ) -> None:
        self.tag_to_section = tag_to_section or {1: 1, 2: 2, 3: 3, 4: 4}
        self.family = family
        self._detector: Any = None

    def load(self) -> bool:
        try:
            from pupil_apriltags import Detector  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("pupil-apriltags not installed — pip install pupil-apriltags")
            return False
        self._detector = Detector(families=self.family)
        logger.info("AprilTag detector ready family=%s map=%s", self.family, self.tag_to_section)
        return True

    def detect(self, frame: Any) -> list[AprilTagDetection]:
        if self._detector is None or frame is None:
            return []
        import cv2

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        cx, cy = w / 2.0, h / 2.0

        out: list[AprilTagDetection] = []
        for tag in self._detector.detect(gray):
            section = self.tag_to_section.get(tag.tag_id)
            if section is None:
                continue
            tx = float(tag.center[0])
            ty = float(tag.center[1])
            dist = ((tx - cx) ** 2 + (ty - cy) ** 2) ** 0.5
            out.append(
                AprilTagDetection(
                    tag_id=tag.tag_id,
                    section=section,
                    center_x=tx,
                    center_y=ty,
                    distance_to_center=dist,
                )
            )
        return out

    def pick_section(self, frame: Any) -> PlateSelection | None:
        detections = self.detect(frame)
        if not detections:
            return None
        best = min(detections, key=lambda d: d.distance_to_center)
        return PlateSelection(section=best.section, tag_id=best.tag_id, all_detections=detections)

    def draw_overlay(self, frame: Any) -> Any:
        """Draw tag outlines and section labels (for test_apriltag_live)."""
        if frame is None:
            return frame
        import cv2

        for det in self.detect(frame):
            cv2.circle(frame, (int(det.center_x), int(det.center_y)), 8, (0, 255, 0), 2)
            cv2.putText(
                frame,
                f"S{det.section} id={det.tag_id}",
                (int(det.center_x) + 10, int(det.center_y)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
            )
        return frame
