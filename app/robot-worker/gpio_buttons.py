"""
GPIO Pin Header number of Jetson Orin Nano, can be edited, these are working rn
All set up as active low, so if its released its HIGH, pressed is LOW
  BOARD pin 35 — plate selection
  BOARD pin 37 — feed 
  BOARD pin 33 — emergency stop

"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO") # needed for whenever we use the GPIO pinning, cause it doesn't know jetson board model otherwise, kept getting error without it

#converts our text variable to boolean, for whenever we set true and false values
def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


#Debouncing all our buttons, 
class DebouncedButton:
    def __init__(self, gpio, pin: int, debounce_sec: float) -> None:
        self._gpio = gpio
        self.pin = pin
        self.debounce_sec = debounce_sec #we set it to .80 ms rn, 
        self.stable_state = gpio.input(pin) #reads state of initial state of button, the current debounced electrical condition
        self.last_raw_state = self.stable_state #update the last state of the button to what it is now after a while
        self.last_raw_change_time = time.time()

    #this is called by polling loop, checks whether the stable state got changed
    def update(self, now: float) -> bool:
        raw_state = self._gpio.input(self.pin)
        if raw_state != self.last_raw_state: #if the electrical signal cahnged, save state and restart the time
            self.last_raw_state = raw_state
            self.last_raw_change_time = now
        if (now - self.last_raw_change_time) >= self.debounce_sec: #if the time the state changed for exceeds our debounce time, then call our transition of state
            if raw_state != self.stable_state:
                self.stable_state = raw_state
                return True
        return False

    def is_pressed(self) -> bool: #now checks our stable state reading and returns if pressed, our final reading of the button
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
        self.enabled = _env_bool("BUTTONS_ENABLED", False) if enabled is None else enabled #we can turn off input for buttons if we want to set the state for testing
        self.pin_mode = (pin_mode or os.environ.get("GPIO_PIN_MODE", "BOARD")).strip().upper() 
        #defualt values for each pin and setting our debounce time to 80 ms default
        self.feed_pin = feed_pin if feed_pin is not None else int(os.environ.get("GPIO_FEED_PIN", "37")) 
        self.plate_pin = plate_pin if plate_pin is not None else int(os.environ.get("GPIO_PLATE_PIN", "35"))
        self.estop_pin = estop_pin if estop_pin is not None else int(os.environ.get("GPIO_ESTOP_PIN", "33"))
        debounce = debounce_ms if debounce_ms is not None else int(os.environ.get("GPIO_DEBOUNCE_MS", "80"))
        self.debounce_sec = debounce / 1000.0 #convert to ms
        self._gpio = None
        self._lock = threading.Lock()
        self._feed_btn: DebouncedButton | None = None
        self._plate_btn: DebouncedButton | None = None
        self._estop_btn: DebouncedButton | None = None

        
        self.emergency_latched = False #persistent system emergency condition remains after edge
        self.estop_reported = False
        #makes sure it only gets the edge states of the buttons, doesnt count holding the button multiple calls; #one time press event waiting to be consumed by queue
        self._feed_edge = False 
        self._plate_edge = False
        self._estop_edge = False
        self._last_feed_stable = False
        self._last_plate_stable = False
        self._last_estop_stable = False

        # After emergency recovery, require the physical e-stop input to be
        # released and stable before it can trigger a new emergency. This
        # prevents the GUI from starting a second 10-second emergency timer
        # from switch bounce/stale GPIO state while the arm is returning home
        self._estop_rearm_deadline = 0.0
        self._estop_waiting_for_release = False

    #initialization of the gpio buttons, test the importing of each gpio, tries mulitple gpio libraries, lots of safety checks
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
            for pin in (self.feed_pin, self.plate_pin, self.estop_pin): #set as digital inputs 
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

    #Polling of every button, priority emergency button
    def poll(self) -> None:
        if not self.enabled:
            return
        now = time.time()
        if self._estop_btn and self._estop_btn.update(now):
            pressed = self._estop_btn.is_pressed()
            if not pressed and self._estop_waiting_for_release and now >= self._estop_rearm_deadline: #after pressed, theres a lockout to let arm go through recovery default phase
                self._estop_waiting_for_release = False
                logger.info("[ESTOP] Physical e-stop released; input re-armed")
            if pressed and not self._last_estop_stable:
                if self.estop_can_trigger():
                    self._estop_edge = True
                    self.latch_emergency("GPIO_ESTOP_DEBOUNCED")
                else:
                    logger.info("[ESTOP] Ignoring e-stop edge until release/cooldown completes")
            self._last_estop_stable = pressed
        if self._feed_btn and self._feed_btn.update(now): #2nd priority feed button, polling for this
            pressed = self._feed_btn.is_pressed()
            if pressed and not self._last_feed_stable:
                self._feed_edge = True
            self._last_feed_stable = pressed
        if self._plate_btn and self._plate_btn.update(now): #last priority select
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

    def plate_raw_pressed(self) -> bool:
        if not self.enabled or self._gpio is None:
            return False
        return self._gpio.input(self.plate_pin) == self._gpio.LOW

    def clear_emergency_latch(self) -> None:
        with self._lock:
            self.emergency_latched = False

    def disarm_estop_until_release(self, cooldown_sec: float = 2.0) -> None:
        """Prevent immediate physical e-stop retrigger after recovery.

        Emergency recovery sends STOP, waits, then sends HOME. The physical
        button can still be held, bouncing, or have a stale debounced edge.
        Without this re-arm gate, the worker can interpret that as a second
        emergency and show another countdown.
        """
        now = time.time()
        with self._lock:
            self._estop_edge = False
            self._estop_waiting_for_release = True
            self._estop_rearm_deadline = now + max(0.0, cooldown_sec)
        logger.info("[ESTOP] Input disarmed until release and %.2fs cooldown", cooldown_sec)

    def estop_can_trigger(self) -> bool:
        now = time.time()
        if self._estop_waiting_for_release:
            # If the release happened before cooldown ended, there may be no new
            # GPIO edge when the cooldown expires. Re-arm here once both
            # conditions are true: cooldown elapsed and raw pin is released, stop the double emergency 
            if now >= self._estop_rearm_deadline and not self.estop_raw_pressed():
                self._estop_waiting_for_release = False
                logger.info("[ESTOP] Physical e-stop released; input re-armed")
                return True
            return False
        return now >= self._estop_rearm_deadline

    def latch_emergency(self, reason: str, *, notify: bool = True) -> None:
        newly_latched = False
        with self._lock:
            newly_latched = not self.emergency_latched
            if newly_latched:
                self.emergency_latched = True
                logger.warning("[ESTOP] Emergency latched: %s", reason)
        if newly_latched and notify:
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
        if not self.estop_can_trigger():
            self._estop_edge = False
            return False
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

    def wait_for_plate_release(self, timeout: float = 0.5) -> None:
        if not self.enabled or self._gpio is None:
            return
        start = time.time()
        while self.plate_raw_pressed():
            if time.time() - start > timeout:
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