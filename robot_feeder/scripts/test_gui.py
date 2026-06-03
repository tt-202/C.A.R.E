#!/usr/bin/env python3
"""Preview operator panel on the main thread (macOS/Linux). Ctrl+C in terminal to quit."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gui.operator_panel import OperatorDisplay


def main() -> int:
    gui = OperatorDisplay()
    gui.setup()
    gui.update(connected=True, state="IDLE", error="NONE", section=1, bites=0)

    states = ["IDLE", "SELECT PLATE (APRILTAG)", "FEEDING", "RETURN HOME", "EMERGENCY STOP"]
    counter = {"i": 0}

    def tick() -> None:
        i = counter["i"]
        gui.update(state=states[i % len(states)], section=(i % 4) + 1, bites=i)
        counter["i"] = i + 1
        if gui.root is not None:
            gui.root.after(3000, tick)

    print("GUI on main thread — cycling demo every 3s. Close window or Ctrl+C to quit.")
    gui.root.after(3000, tick)
    try:
        gui.run_mainloop()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
