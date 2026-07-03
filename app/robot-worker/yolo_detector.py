#!/usr/bin/env python3
"""
C.A.R.E plate + spoon YOLO helper using the same USB camera + V4L2 style as
usb_camera_food_spoon_detection.py.

This patch keeps the spoon check after SCOOP and now adds plate empty/full
checking when the arm is in the selection/plate-view angle.

Expected files/location:
  - Plate: best.engine (or YOLO_PLATE_MODEL_PATH)
  - Spoon: bestest.pt (or YOLO_SPOON_MODEL_PATH)
  - Plug in the USB camera before running.

Standalone tests:
  python3 yolo_detector.py --target plate --preview
  python3 yolo_detector.py --target spoon --preview
  python3 yolo_detector.py --target all --preview
"""

from pathlib import Path
import argparse
import os
import time

from ultralytics import YOLO
import cv2

BASE_DIR = Path(__file__).resolve().parent
WINDOW_NAME = "USB YOLO Check"

# Plate and spoon can use different weights (e.g. best.engine + bestest.pt).
_PLATE_MODEL_CANDIDATES = ("best.engine")
_SPOON_MODEL_CANDIDATES = ("bestest.pt", "best.engine")


def _resolve_path_from_env(env_key: str, candidates: tuple[str, ...]) -> str:
    """Resolve one model file: per-target env, then YOLO_MODEL_PATH, then first existing candidate."""
    for key in (env_key, "YOLO_MODEL_PATH"):
        override = os.environ.get(key, "").strip()
        if not override:
            continue
        path = Path(override)
        if not path.is_absolute():
            path = BASE_DIR / path
        if path.is_file():
            return str(path)
        raise FileNotFoundError(f"{key} not found: {path}")

    for name in candidates:
        path = BASE_DIR / name
        if path.is_file():
            return str(path)

    raise FileNotFoundError(
        f"No YOLO model for {env_key} in {BASE_DIR}. "
        f"Tried {candidates}; set {env_key} or YOLO_MODEL_PATH in .env"
    )


def resolve_plate_model_path() -> str:
    return _resolve_path_from_env("YOLO_PLATE_MODEL_PATH", _PLATE_MODEL_CANDIDATES)


def resolve_spoon_model_path() -> str:
    return _resolve_path_from_env("YOLO_SPOON_MODEL_PATH", _SPOON_MODEL_CANDIDATES)


def default_model_path(target: str = "plate") -> str:
    target = str(target).strip().lower()
    if target == "spoon":
        return resolve_spoon_model_path()
    return resolve_plate_model_path()


CAMERA_ID = "/dev/video0"
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 30
CAMERA_FORMAT = "MJPG"

CONFIDENCE = float(os.environ.get("YOLO_CONFIDENCE", "0.50"))
SCAN_SECONDS = float(os.environ.get("YOLO_SCAN_SECONDS", "1.0"))
PLATE_SCAN_SECONDS = float(os.environ.get("YOLO_PLATE_SCAN_SECONDS", os.environ.get("YOLO_SCAN_SECONDS", "1.0")))
SPOON_SCAN_SECONDS = float(os.environ.get("YOLO_SPOON_SCAN_SECONDS", os.environ.get("YOLO_SCAN_SECONDS", "1.0")))
MIN_VOTES = int(os.environ.get("YOLO_MIN_VOTES", "2"))

# Update these names after checking the printed model.names on the Jetson.
# These aliases are intentionally broad so common naming variations still work.
PLATE_EMPTY_CLASSES = {
    "empty_plate", "plate_empty", "empty plate", "plate-empty",
    "emptyplate", "plate no food", "no_food_plate", "plate_without_food",
    "empty plate", "plate without food",
}
PLATE_FULL_CLASSES = {
    "full_plate", "plate_full", "plate with food", "plate-food",
    "food_plate", "plate_food", "fullplate", "food_on_plate",
    "plate_with_food",
}
SPOON_EMPTY_CLASSES = {
    "empty_spoon", "spoon_empty", "empty spoon", "spoon-empty",
    "emptyspoon", "spoon no food", "no_food_spoon", "spoon_without_food",
    "empty spoon", "spoon without food",
}
SPOON_FULL_CLASSES = {
    "full_spoon", "spoon_full", "spoon with food", "spoon-food",
    "food_spoon", "spoon_food", "fullspoon", "food_on_spoon",
    "spoon_with_food",
}


def _norm(name):
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _alias_set(values):
    return {_norm(v) for v in values}


def open_usb_camera():
    """Open USB camera exactly like the working standalone YOLO script."""
    print(f"Opening USB camera: {CAMERA_ID}", flush=True)
    cap = cv2.VideoCapture(CAMERA_ID, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*CAMERA_FORMAT))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open USB camera at {CAMERA_ID}. "
            "Try /dev/video1 or /dev/video2."
        )
    return cap


class CAREYoloDetector:
    def __init__(self, model_path=None, confidence=CONFIDENCE, target: str = "plate"):
        self.target = str(target).strip().lower()
        self.model_path = str(model_path or default_model_path(self.target))
        self.confidence = float(confidence)
        self.model = None

    def load(self):
        if self.model is not None:
            return
        if not Path(self.model_path).exists():
            raise FileNotFoundError(
                f"YOLO model not found: {self.model_path}. "
                "Set YOLO_PLATE_MODEL_PATH / YOLO_SPOON_MODEL_PATH in .env"
            )
        print(f"Loading YOLO model ({self.target}): {self.model_path}", flush=True)
        self.model = YOLO(self.model_path, task="detect")
        print("Model class names:", flush=True)
        print(self.model.names, flush=True)
        print(flush=True)

    def scan_target(self, target, scan_seconds=SCAN_SECONDS, preview=False):
        """
        Returns a dictionary with status: 'full', 'empty', or 'unknown'.
        target must be 'plate' or 'spoon'.
        """
        target = str(target).strip().lower()
        if target == "plate":
            empty_aliases = _alias_set(PLATE_EMPTY_CLASSES)
            full_aliases = _alias_set(PLATE_FULL_CLASSES)
            log_label = "PLATE"
        elif target == "spoon":
            empty_aliases = _alias_set(SPOON_EMPTY_CLASSES)
            full_aliases = _alias_set(SPOON_FULL_CLASSES)
            log_label = "SPOON"
        else:
            raise ValueError(f"Unsupported YOLO target: {target}")

        self.load()
        cap = open_usb_camera()
        deadline = time.time() + float(scan_seconds)
        votes = {"empty": 0, "full": 0}
        frames = 0
        best = {"class_name": None, "confidence": 0.0}
        last_seen = []

        if preview:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)

        print(f"--- USB Camera + YOLO {target.title()} Check Active ---", flush=True)
        print(f"Camera device: {CAMERA_ID}", flush=True)
        print(f"Resolution: {CAMERA_WIDTH}x{CAMERA_HEIGHT}", flush=True)
        print(f"FPS target: {CAMERA_FPS}", flush=True)
        print(f"Format: {CAMERA_FORMAT}", flush=True)

        try:
            while time.time() < deadline:
                success, frame = cap.read()
                if not success or frame is None:
                    print("Failed to read frame.", flush=True)
                    continue

                frames += 1
                results = self.model(frame, conf=self.confidence, verbose=False)
                annotated_frame = frame

                if results:
                    result0 = results[0]
                    annotated_frame = result0.plot()
                    names = result0.names
                    for box in result0.boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        raw_name = str(names.get(cls_id, cls_id))
                        norm_name = _norm(raw_name)
                        last_seen.append((raw_name, conf))

                        if conf > best["confidence"]:
                            best = {"class_name": raw_name, "confidence": conf}

                        if norm_name in empty_aliases:
                            votes["empty"] += 1
                        elif norm_name in full_aliases:
                            votes["full"] += 1

                if preview:
                    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_AUTOSIZE) >= 0:
                        cv2.imshow(WINDOW_NAME, annotated_frame)
                    key_code = cv2.waitKey(10) & 0xFF
                    if key_code == 27 or key_code == ord("q"):
                        break

            if votes["full"] >= MIN_VOTES and votes["full"] >= votes["empty"]:
                status = "full"
            elif votes["empty"] >= MIN_VOTES and votes["empty"] > votes["full"]:
                status = "empty"
            else:
                status = "unknown"

            result = {
                "target": target,
                "status": status,
                "votes": votes,
                "frames": frames,
                "best_class": best["class_name"],
                "best_confidence": best["confidence"],
                "recent_detections": last_seen[-10:],
                "model_path": self.model_path,
            }
            print(f"[YOLO_{log_label}_RESULT] {result}", flush=True)
            return result

        finally:
            cap.release()
            if preview:
                cv2.destroyWindow(WINDOW_NAME)

    def scan_spoon(self, scan_seconds=None, preview=False):
        seconds = SPOON_SCAN_SECONDS if scan_seconds is None else scan_seconds
        return self.scan_target("spoon", scan_seconds=seconds, preview=preview)

    def scan_plate(self, scan_seconds=None, preview=False):
        seconds = PLATE_SCAN_SECONDS if scan_seconds is None else scan_seconds
        return self.scan_target("plate", scan_seconds=seconds, preview=preview)

    def preview_all_detections(self):
        """Standalone visual/debug mode matching the original uploaded YOLO script."""
        self.load()
        cap = open_usb_camera()
        cv2.namedWindow("USB YOLO Detection", cv2.WINDOW_AUTOSIZE)
        print("Press q or ESC to quit.", flush=True)
        try:
            while True:
                success, frame = cap.read()
                if not success or frame is None:
                    print("Failed to read frame.", flush=True)
                    break
                results = self.model(frame, conf=self.confidence, verbose=False)
                annotated_frame = results[0].plot() if results else frame
                cv2.imshow("USB YOLO Detection", annotated_frame)
                key_code = cv2.waitKey(10) & 0xFF
                if key_code == 27 or key_code == ord("q"):
                    break
        finally:
            cap.release()
            cv2.destroyAllWindows()


_plate_detector = None
_spoon_detector = None


def get_plate_detector() -> CAREYoloDetector:
    global _plate_detector
    if _plate_detector is None:
        _plate_detector = CAREYoloDetector(target="plate")
    return _plate_detector


def get_spoon_detector() -> CAREYoloDetector:
    global _spoon_detector
    if _spoon_detector is None:
        _spoon_detector = CAREYoloDetector(target="spoon")
    return _spoon_detector


def get_detector():
    """Legacy alias — returns plate detector."""
    return get_plate_detector()


def check_spoon_state(preview=False):
    return get_spoon_detector().scan_spoon(preview=preview)


def check_plate_state(preview=False):
    return get_plate_detector().scan_plate(preview=preview)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["plate", "spoon", "all"], default="spoon")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    if args.target == "all":
        CAREYoloDetector(target="spoon").preview_all_detections()
    elif args.target == "plate":
        get_plate_detector().scan_plate(preview=args.preview)
    else:
        get_spoon_detector().scan_spoon(preview=args.preview)


if __name__ == "__main__":
    raise SystemExit(main())