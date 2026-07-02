#!/usr/bin/env python3
"""
C.A.R.E plate + spoon YOLO helper using the same USB camera + V4L2 style as
usb_camera_food_spoon_detection.py.

This patch keeps the spoon check after SCOOP and now adds plate empty/full
checking when the arm is in the selection/plate-view angle.

Expected files/location:
  - Plate: best.engine (or YOLO_PLATE_MODEL_PATH)
  - Spoon: bestest.engine (or YOLO_SPOON_MODEL_PATH)
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

# Plate and spoon use separate TensorRT engines on Jetson.
_PLATE_MODEL_CANDIDATES = ("best.engine", "bestest.engine", "bestest.pt", "best.pt")
_SPOON_MODEL_CANDIDATES = ("bestest.engine", "best.engine", "bestest.pt", "best.pt")


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
PLATE_SCAN_SECONDS = float(
    os.environ.get("YOLO_PLATE_SCAN_SECONDS", os.environ.get("YOLO_SCAN_SECONDS", "0.5"))
)
SPOON_SCAN_SECONDS = float(
    os.environ.get("YOLO_SPOON_SCAN_SECONDS", os.environ.get("YOLO_SCAN_SECONDS", "1.0"))
)
MIN_VOTES = int(os.environ.get("YOLO_MIN_VOTES", "1"))
PLATE_MIN_VOTES = int(os.environ.get("YOLO_PLATE_MIN_VOTES", os.environ.get("YOLO_MIN_VOTES", "1")))
SPOON_MIN_VOTES = int(os.environ.get("YOLO_SPOON_MIN_VOTES", os.environ.get("YOLO_MIN_VOTES", "1")))
PLATE_IMGSZ = int(os.environ.get("YOLO_PLATE_IMGSZ", "416"))
SPOON_IMGSZ = int(os.environ.get("YOLO_SPOON_IMGSZ", "640"))
CAMERA_WARMUP_FRAMES = int(os.environ.get("YOLO_CAMERA_WARMUP_FRAMES", "2"))
PLATE_SINGLE_SHOT_CONF = float(os.environ.get("YOLO_PLATE_SINGLE_SHOT_CONF", "0.72"))

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


def _decide_yolo_status(
    votes: dict[str, int],
    *,
    min_votes: int,
    empty_aliases: set[str],
    full_aliases: set[str],
    best_class: str | None,
    best_confidence: float,
    single_shot_conf: float = 0.0,
) -> str:
    if votes["full"] >= min_votes and votes["full"] >= votes["empty"]:
        return "full"
    if votes["empty"] >= min_votes and votes["empty"] > votes["full"]:
        return "empty"
    if single_shot_conf > 0 and best_class and best_confidence >= single_shot_conf:
        norm_name = _norm(best_class)
        if norm_name in full_aliases:
            return "full"
        if norm_name in empty_aliases:
            return "empty"
    return "unknown"


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

    def scan_target(
        self,
        target,
        scan_seconds=SCAN_SECONDS,
        preview=False,
        *,
        min_votes: int | None = None,
        imgsz: int | None = None,
        single_shot_conf: float = 0.0,
    ):
        """
        Returns a dictionary with status: 'full', 'empty', or 'unknown'.
        target must be 'plate' or 'spoon'.
        Exits early as soon as min_votes or single-shot confidence is satisfied.
        """
        target = str(target).strip().lower()
        if target == "plate":
            empty_aliases = _alias_set(PLATE_EMPTY_CLASSES)
            full_aliases = _alias_set(PLATE_FULL_CLASSES)
            log_label = "PLATE"
            if min_votes is None:
                min_votes = PLATE_MIN_VOTES
            if imgsz is None:
                imgsz = PLATE_IMGSZ
            if single_shot_conf == 0.0:
                single_shot_conf = PLATE_SINGLE_SHOT_CONF
        elif target == "spoon":
            empty_aliases = _alias_set(SPOON_EMPTY_CLASSES)
            full_aliases = _alias_set(SPOON_FULL_CLASSES)
            log_label = "SPOON"
            if min_votes is None:
                min_votes = SPOON_MIN_VOTES
            if imgsz is None:
                imgsz = SPOON_IMGSZ
        else:
            raise ValueError(f"Unsupported YOLO target: {target}")

        self.load()
        cap = open_usb_camera()
        started = time.time()
        deadline = started + float(scan_seconds)
        votes = {"empty": 0, "full": 0}
        frames = 0
        best = {"class_name": None, "confidence": 0.0}
        last_seen = []
        status = "unknown"
        early_exit = False

        if preview:
            cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)

        print(f"--- USB Camera + YOLO {target.title()} Check Active ---", flush=True)
        print(
            f"scan={scan_seconds}s min_votes={min_votes} imgsz={imgsz} warmup={CAMERA_WARMUP_FRAMES}",
            flush=True,
        )

        try:
            for _ in range(max(0, CAMERA_WARMUP_FRAMES)):
                cap.read()

            while time.time() < deadline:
                success, frame = cap.read()
                if not success or frame is None:
                    print("Failed to read frame.", flush=True)
                    continue

                frames += 1
                results = self.model(frame, conf=self.confidence, verbose=False, imgsz=imgsz)
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

                status = _decide_yolo_status(
                    votes,
                    min_votes=min_votes,
                    empty_aliases=empty_aliases,
                    full_aliases=full_aliases,
                    best_class=best["class_name"],
                    best_confidence=best["confidence"],
                    single_shot_conf=single_shot_conf,
                )
                if status != "unknown":
                    early_exit = True
                    break

                if preview:
                    if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_AUTOSIZE) >= 0:
                        cv2.imshow(WINDOW_NAME, annotated_frame)
                    key_code = cv2.waitKey(1) & 0xFF
                    if key_code == 27 or key_code == ord("q"):
                        break

            if status == "unknown":
                status = _decide_yolo_status(
                    votes,
                    min_votes=min_votes,
                    empty_aliases=empty_aliases,
                    full_aliases=full_aliases,
                    best_class=best["class_name"],
                    best_confidence=best["confidence"],
                    single_shot_conf=single_shot_conf,
                )

            elapsed = time.time() - started
            result = {
                "target": target,
                "status": status,
                "votes": votes,
                "frames": frames,
                "best_class": best["class_name"],
                "best_confidence": best["confidence"],
                "recent_detections": last_seen[-10:],
                "model_path": self.model_path,
                "elapsed_sec": round(elapsed, 3),
                "early_exit": early_exit,
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


def preload_yolo_models() -> None:
    """Load plate/spoon TensorRT weights at worker startup (avoids delay on first SELECT)."""
    if os.environ.get("ENABLE_YOLO_CHECKS", "true").lower() not in ("1", "true", "yes"):
        return
    if os.environ.get("YOLO_PRELOAD", "true").lower() not in ("1", "true", "yes"):
        return
    try:
        get_plate_detector().load()
        get_spoon_detector().load()
        print("[YOLO] Plate and spoon models preloaded", flush=True)
    except Exception as exc:
        print(f"[YOLO] Preload skipped: {exc}", flush=True)


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
