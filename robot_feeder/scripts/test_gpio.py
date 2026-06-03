#!/usr/bin/env python3
"""Step 5: GPIO buttons — press feed / plate / e-stop. Ctrl+C to quit."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sensors.gpio_buttons import ButtonManager


def main() -> int:
    import os

    os.environ.setdefault("BUTTONS_ENABLED", "true")
    buttons = ButtonManager(enabled=True)
    if not buttons.setup():
        print("FAIL: BUTTONS_ENABLED or RPi.GPIO not available (run on Jetson with GPIO wired).")
        return 1

    print("Listening… feed / plate / e-stop (Ctrl+C to quit)")
    try:
        while True:
            buttons.poll()
            if buttons.feed_pressed():
                print(">>> FEED pressed")
            if buttons.plate_pressed():
                print(">>> PLATE pressed")
            if buttons.estop_pressed():
                print(">>> ESTOP pressed")
            if buttons.estop_held():
                print("!!! ESTOP HELD")
            time.sleep(0.05)
    except KeyboardInterrupt:
        buttons.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
