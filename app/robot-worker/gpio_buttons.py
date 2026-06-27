"""
Physical feed / plate / e-stop buttons on Jetson Orin Nano.

Matches `New_Settings_June26/main_controller_phase4.py` wiring:
  BOARD pin 35 — plate / selection (calibrate)
  BOARD pin 37 — feed (bite cycle)
  BOARD pin 33 — emergency stop (active-low)

Set BUTTONS_ENABLED=true with Jetson.GPIO wired.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class DebouncedButton:
    def __init__(self, gpio, pin: int, debounce_sec: float) -> None:
        self._gpio = gpio
        self.pin = pin
        self.debounce_sec = debounce_sec
        self.stable_state = gpio.input(pin)
        self.last_raw_state = self.stable_state
        self.last_raw_change_time = time.time()

    def update(self, now: float) -> bool:
        raw_state = self._gpio.input(self.pin)
        if raw_state != self.last_raw_state:
            self.last_raw_state = raw_state
            self.last_raw_change_time = now
        if (now - self.last_raw_change_time) >= self.debounce_sec:
            if raw_state != self.stable_state:
                self.stable_state = raw_state
                return True
        return False

    def is_pressed(self) -> bool:
        return self.stable_state == self._gpio.LOW


class ButtonManager:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        feed_pin: int | None = None,
        plate_pin: int | None = None,
        estop_pin: int | None = None,
        debounce_ms: int | None = None,
        pin_mode: str | None = None,
    ) -> None:
        self.enabled = _env_bool("BUTTONS_ENABLED", False) if enabled is None else enabled
        self.pin_mode = (pin_mode or os.environ.get("GPIO_PIN_MODE", "BOARD")).strip().upper()
        self.feed_pin = feed_pin if feed_pin is not None else int(os.environ.get("GPIO_FEED_PIN", "37"))
        self.plate_pin = plate_pin if plate_pin is not None else int(os.environ.get("GPIO_PLATE_PIN", "35"))
        self.estop_pin = estop_pin if estop_pin is not None else int(os.environ.get("GPIO_ESTOP_PIN", "33"))
        debounce = debounce_ms if debounce_ms is not None else int(os.environ.get("GPIO_DEBOUNCE_MS", "80"))
        self.debounce_sec = debounce / 1000.0
        self._gpio = None
        self._lock = threading.Lock()
        self._feed_btn: DebouncedButton | None = None
        self._plate_btn: DebouncedButton | None = None
        self._estop_btn: DebouncedButton | None = None
        self.emergency_latched = False
        self.estop_reported = False
        self._feed_edge = False
        self._plate_edge = False
        self._estop_edge = False
        self._last_feed_stable = False
        self._last_plate_stable = False
        self._last_estop_stable = False

    def setup(self) -> bool:
        if not self.enabled:
            logger.info("GPIO buttons disabled (BUTTONS_ENABLED=false)")
            return False
        try:
            try:
                import RPi.GPIO as GPIO  # type: ignore[import-not-found]
            except ImportError:
                import Jetson.GPIO as GPIO  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("RPi.GPIO / Jetson.GPIO not installed — buttons disabled")
            self.enabled = False
            return False

        try:
            self._gpio = GPIO
            GPIO.setwarnings(False)
            if self.pin_mode == "BCM":
                GPIO.setmode(GPIO.BCM)
            else:
                GPIO.setmode(GPIO.BOARD)
            for pin in (self.feed_pin, self.plate_pin, self.estop_pin):
                GPIO.setup(pin, GPIO.IN)
            self._feed_btn = DebouncedButton(GPIO, self.feed_pin, self.debounce_sec)
            self._plate_btn = DebouncedButton(GPIO, self.plate_pin, self.debounce_sec)
            self._estop_btn = DebouncedButton(GPIO, self.estop_pin, self.debounce_sec)
        except Exception as e:
            logger.warning("GPIO setup failed (%s) — buttons disabled", e)
            self.enabled = False
            self._gpio = None
            return False

        logger.info(
            "GPIO buttons feed=%s plate=%s estop=%s (%s)",
            self.feed_pin,
            self.plate_pin,
            self.estop_pin,
            self.pin_mode,
        )
        return True

    def poll(self) -> None:
        if not self.enabled:
            return
        now = time.time()
        if self._estop_btn and self._estop_btn.update(now):
            pressed = self._estop_btn.is_pressed()
            if pressed and not self._last_estop_stable:
                self._estop_edge = True
                self.latch_emergency("GPIO_ESTOP_DEBOUNCED")
            self._last_estop_stable = pressed
        if self._feed_btn and self._feed_btn.update(now):
            pressed = self._feed_btn.is_pressed()
            if pressed and not self._last_feed_stable:
                self._feed_edge = True
            self._last_feed_stable = pressed
        if self._plate_btn and self._plate_btn.update(now):
            pressed = self._plate_btn.is_pressed()
            if pressed and not self._last_plate_stable:
                self._plate_edge = True
            self._last_plate_stable = pressed

    def estop_raw_pressed(self) -> bool:
        if not self.enabled or self._gpio is None:
            return False
        return self._gpio.input(self.estop_pin) == self._gpio.LOW

    def feed_raw_pressed(self) -> bool:
        if not self.enabled or self._gpio is None:
            return False
        return self._gpio.input(self.feed_pin) == self._gpio.LOW

    def clear_emergency_latch(self) -> None:
        with self._lock:
            self.emergency_latched = False

    def latch_emergency(self, reason: str) -> None:
        newly_latched = False
        with self._lock:
            newly_latched = not self.emergency_latched
            if newly_latched:
                self.emergency_latched = True
                logger.warning("[ESTOP] Emergency latched: %s", reason)
        if newly_latched:
            from estop_hooks import notify_estop_latched

            notify_estop_latched()

    def is_emergency_latched(self) -> bool:
        with self._lock:
            return self.emergency_latched

    def feed_pressed(self) -> bool:
        if self._feed_edge:
            self._feed_edge = False
            return True
        return False

    def plate_pressed(self) -> bool:
        if self._plate_edge:
            self._plate_edge = False
            return True
        return False

    def estop_pressed(self) -> bool:
        if self._estop_edge:
            self._estop_edge = False
            return True
        return False

    def wait_for_feed_release(self, timeout: float = 3.0) -> None:
        if not self.enabled or self._gpio is None:
            return
        start = time.time()
        while self.feed_raw_pressed():
            if time.time() - start > timeout:
                logger.warning("[GPIO] FEED still held after timeout")
                return
            time.sleep(0.02)

    def cleanup(self) -> None:
        if self._gpio is not None:
            self._gpio.cleanup()
            self._gpio = None


class ButtonPoller:
    def __init__(self, buttons: ButtonManager, interval_sec: float = 0.005) -> None:
        self.buttons = buttons
        self.interval_sec = interval_sec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.buttons.enabled:
            return
        self._thread = threading.Thread(target=self._run, name="gpio-buttons", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.buttons.poll()
            self._stop.wait(self.interval_sec)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
