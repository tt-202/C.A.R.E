"""ToF subprocess reader — keeps Blinka/I2C out of the Jetson.GPIO process."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent
TOF_PROCESS_FILE = ROOT_DIR / "tof_stream_process.py"


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def use_fake_tof() -> bool:
    return _env_bool("USE_FAKE_TOF", False)


def fake_tof_cm() -> float:
    return float(os.environ.get("FAKE_TOF_CM", "60.0"))


class ToFSubprocessReader:
    def __init__(self, script_path: Path | None = None) -> None:
        self.script_path = script_path or TOF_PROCESS_FILE
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.running = False
        self.latest_distance_cm: float | None = None
        self.latest_time = 0.0

    def start(self) -> None:
        if use_fake_tof():
            logger.info("[TOF] Fake ToF enabled — subprocess not started")
            return
        if self.process is not None:
            return
        if not self.script_path.exists():
            raise FileNotFoundError(f"Missing ToF subprocess file: {self.script_path}")

        logger.info("[TOF] Starting subprocess: %s", self.script_path)
        self.process = subprocess.Popen(
            [sys.executable, str(self.script_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(ROOT_DIR),
        )
        self.running = True
        self.thread = threading.Thread(target=self._reader_loop, daemon=True, name="tof-reader")
        self.thread.start()

    def _reader_loop(self) -> None:
        while self.running and self.process is not None and self.process.stdout is not None:
            line = self.process.stdout.readline()
            if not line:
                if self.process.poll() is not None:
                    logger.warning("[TOF] Subprocess exited")
                    break
                continue
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("[TOF RAW] %s", line)
                continue
            msg_type = msg.get("type")
            if msg_type == "distance":
                distance_cm = msg.get("distance_cm")
                if distance_cm is not None:
                    distance_cm = float(distance_cm)
                    if 0 < distance_cm <= 400:
                        self.latest_distance_cm = distance_cm
                        self.latest_time = time.time()
            elif msg_type == "status":
                logger.info("[TOF] %s", msg.get("message"))
            elif msg_type == "error":
                logger.error("[TOF ERROR] %s", msg.get("message"))

    def get_latest(self, max_age_seconds: float = 1.0) -> float | None:
        if use_fake_tof():
            return fake_tof_cm()
        if self.latest_distance_cm is None:
            return None
        age = time.time() - self.latest_time
        if age > max_age_seconds:
            logger.warning("[TOF] Latest reading stale (%.2fs old)", age)
            return None
        return self.latest_distance_cm

    def stop(self) -> None:
        self.running = False
        if self.process is not None:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
        self.process = None
        logger.info("[TOF] Subprocess stopped")


_tof_reader: ToFSubprocessReader | None = None


def get_tof_reader() -> ToFSubprocessReader:
    global _tof_reader
    if _tof_reader is None:
        _tof_reader = ToFSubprocessReader()
    return _tof_reader


def start_tof_reader() -> None:
    get_tof_reader().start()


def stop_tof_reader() -> None:
    global _tof_reader
    if _tof_reader is not None:
        _tof_reader.stop()
        _tof_reader = None


def read_tof_cm_safe() -> float | None:
    if use_fake_tof():
        return fake_tof_cm()
    return get_tof_reader().get_latest(max_age_seconds=1.0)
