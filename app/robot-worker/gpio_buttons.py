"""
Physical feed / plate / e-stop buttons (BCM numbering).

Set BUTTONS_ENABLED=true on Jetson with RPi.GPIO wired.
Without GPIO, Firestore commands still control the arm.
"""

from __future__ import annotations

import logging
import os
import threading

logger = logging.getLogger(__name__)


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class ButtonManager:
    """Debounced GPIO inputs; active-low with internal pull-ups."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        feed_pin: int | None = None,
        plate_pin: int | None = None,
        estop_pin: int | None = None,
        debounce_ms: int | None = None,
    ) -> None:
        self.enabled = _env_bool("BUTTONS_ENABLED", False) if enabled is None else enabled
        self.feed_pin = feed_pin if feed_pin is not None else int(os.environ.get("GPIO_FEED_PIN", "17"))
        self.plate_pin = plate_pin if plate_pin is not None else int(os.environ.get("GPIO_PLATE_PIN", "27"))
        self.estop_pin = estop_pin if estop_pin is not None else int(os.environ.get("GPIO_ESTOP_PIN", "22"))
        self.debounce_ms = debounce_ms if debounce_ms is not None else int(os.environ.get("GPIO_DEBOUNCE_MS", "80"))
        self._gpio = None
        self._lock = threading.Lock()
        self._feed = False
        self._plate = False
        self._estop = False
        self._last_feed = False
        self._last_plate = False
        self._last_estop = False

    def setup(self) -> bool:
        if not self.enabled:
            logger.info("GPIO buttons disabled (BUTTONS_ENABLED=false)")
            return False
        try:
            import RPi.GPIO as GPIO  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("RPi.GPIO not installed — buttons disabled")
            self.enabled = False
            return False

        self._gpio = GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in (self.feed_pin, self.plate_pin, self.estop_pin):
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        logger.info(
            "GPIO buttons feed=%s plate=%s estop=%s (BCM)",
            self.feed_pin,
            self.plate_pin,
            self.estop_pin,
        )
        return True

    def _pressed(self, pin: int) -> bool:
        if not self.enabled or self._gpio is None:
            return False
        return self._gpio.input(pin) == self._gpio.LOW

    def poll(self) -> None:
        if not self.enabled:
            return
        feed = self._pressed(self.feed_pin)
        plate = self._pressed(self.plate_pin)
        estop = self._pressed(self.estop_pin)
        with self._lock:
            if feed and not self._last_feed:
                self._feed = True
            if plate and not self._last_plate:
                self._plate = True
            if estop and not self._last_estop:
                self._estop = True
            self._last_feed = feed
            self._last_plate = plate
            self._last_estop = estop

    def feed_pressed(self) -> bool:
        with self._lock:
            if self._feed:
                self._feed = False
                return True
        return False

    def plate_pressed(self) -> bool:
        with self._lock:
            if self._plate:
                self._plate = False
                return True
        return False

    def estop_pressed(self) -> bool:
        with self._lock:
            if self._estop:
                self._estop = False
                return True
        return False

    def cleanup(self) -> None:
        if self._gpio is not None:
            self._gpio.cleanup()
            self._gpio = None


class ButtonPoller:
    """Background thread so the main loop stays responsive."""

    def __init__(self, buttons: ButtonManager, interval_sec: float = 0.05) -> None:
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
