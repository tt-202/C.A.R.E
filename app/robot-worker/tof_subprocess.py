# ToF subprocess reader.
#
# The physical sensor is handled by tof_stream_process.py in a separate
# process. This keeps Blinka/I2C code out of the main Jetson.GPIO process.

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

# Resolve the worker directory and the path to the ToF streaming program.
ROOT_DIR = Path(__file__).resolve().parent
TOF_PROCESS_FILE = ROOT_DIR / "tof_stream_process.py"


# Reads a boolean environment variable while accepting common true values.
def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)

    if raw is None:
        return default

    return raw.strip().lower() in ("1", "true", "yes", "on")


# Indicates whether the robot should use a simulated distance instead
# of starting the physical ToF sensor.
def use_fake_tof() -> bool:
    return _env_bool("USE_FAKE_TOF", False)


# Returns the simulated distance used during testing without hardware.
def fake_tof_cm() -> float:
    return float(os.environ.get("FAKE_TOF_CM", "60.0"))


# Manages the ToF child process and remembers its newest valid measurement.
class ToFSubprocessReader:
    def __init__(self, script_path: Path | None = None) -> None:
        self.script_path = script_path or TOF_PROCESS_FILE
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None
        self.running = False

        # Store both the value and its arrival time so stale sensor
        # measurements can be rejected.
        self.latest_distance_cm: float | None = None
        self.latest_time = 0.0

    # Starts the ToF child process and a background thread that reads its output.
    def start(self) -> None:
        if use_fake_tof():
            logger.info("[TOF] Fake ToF enabled — subprocess not started")
            return

        # Avoid starting a second child if this reader is already running.
        if self.process is not None:
            return

        if not self.script_path.exists():
            raise FileNotFoundError(f"Missing ToF subprocess file: {self.script_path}")

        logger.info("[TOF] Starting subprocess: %s", self.script_path)

        self.process = subprocess.Popen(
            [sys.executable, str(self.script_path)],

            # The child sends JSON messages through standard output.
            stdout=subprocess.PIPE,

            # Combine error output with normal output so one reader handles both.
            stderr=subprocess.STDOUT,

            # Return strings instead of raw bytes.
            text=True,

            # Request line-buffered communication.
            bufsize=1,

            # Run from the robot-worker directory.
            cwd=str(ROOT_DIR),
        )

        self.running = True

        # The background thread prevents sensor output from blocking
        # the main feeding loop.
        self.thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name="tof-reader",
        )
        self.thread.start()

    # Continuously reads and interprets JSON lines from the sensor process.
    def _reader_loop(self) -> None:
        while self.running and self.process is not None and self.process.stdout is not None:
            line = self.process.stdout.readline()

            if not line:
                # poll() returns a value after the child process has exited.
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
                # Unexpected non-JSON output is logged for debugging but does
                # not stop the reader.
                logger.debug("[TOF RAW] %s", line)
                continue

            msg_type = msg.get("type")

            if msg_type == "distance":
                distance_cm = msg.get("distance_cm")

                if distance_cm is not None:
                    distance_cm = float(distance_cm)

                    # The VL53L1X is expected to report a positive value no
                    # greater than 400 cm. Values outside that range are ignored.
                    if 0 < distance_cm <= 400:
                        self.latest_distance_cm = distance_cm
                        self.latest_time = time.time()

            elif msg_type == "status":
                logger.info("[TOF] %s", msg.get("message"))

            elif msg_type == "error":
                logger.error("[TOF ERROR] %s", msg.get("message"))

    # Returns the newest sensor reading only if it is recent enough.
    # None tells the feeding cycle that it should not move forward using
    # an unavailable or outdated distance.
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

    # Stops the sensor child process.
    def stop(self) -> None:
        self.running = False

        if self.process is not None:
            try:
                # First give the process a chance to shut down normally.
                self.process.terminate()
                self.process.wait(timeout=2.0)

            except Exception:
                try:
                    # Force it to stop if normal termination did not work.
                    self.process.kill()
                except Exception:
                    pass

        self.process = None
        logger.info("[TOF] Subprocess stopped")


# The worker uses one shared reader so multiple parts of the program
# do not start competing sensor processes on the same I2C bus.
_tof_reader: ToFSubprocessReader | None = None


# Returns the shared reader, creating it the first time it is requested.
def get_tof_reader() -> ToFSubprocessReader:
    global _tof_reader

    if _tof_reader is None:
        _tof_reader = ToFSubprocessReader()

    return _tof_reader


# Starts the shared ToF reader.
def start_tof_reader() -> None:
    get_tof_reader().start()


# Stops the shared reader and clears it so a new one can be created later.
def stop_tof_reader() -> None:
    global _tof_reader

    if _tof_reader is not None:
        _tof_reader.stop()
        _tof_reader = None


# Returns the latest trustworthy distance for feeding_cycle.py.
#
# The reading is rejected if it is more than one second old.
def read_tof_cm_safe() -> float | None:
    if use_fake_tof():
        return fake_tof_cm()

    return get_tof_reader().get_latest(max_age_seconds=1.0)