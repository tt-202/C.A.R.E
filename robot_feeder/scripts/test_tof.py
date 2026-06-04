#!/usr/bin/env python3
"""
Test TOF distance reading and safety limits.

Today TOFSensor is a stub: returns TOF_MOCK_MM from .env (default 200 mm).
On Jetson with VL53L0X wired, replace perception/tof_sensor.py with a real driver.

Usage:
  python scripts/test_tof.py
  TOF_MOCK_MM=150 python scripts/test_tof.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from perception.tof_sensor import TOFSensor
from robot.safety import SafetyMonitor


def main() -> int:
    mock = int(os.environ.get("TOF_MOCK_MM", "200"))
    tof = TOFSensor()
    safety = SafetyMonitor()

    print("=== TOF test ===")
    print(f"TOF_MOCK_MM (env) = {mock}")
    print(f"Safety OK range   = {safety.limits.min_tof_mm}–{safety.limits.max_tof_mm} mm")
    print()

    for trial in range(5):
        mm = tof.read_distance_mm()
        ok = safety.tof_ok(mm)
        status = "OK (in range)" if ok else "OUT OF RANGE → would trigger emergency in detect_mouth"
        print(f"  read {trial + 1}: {mm} mm — {status}")

    print()
    print("Try out-of-range values:")
    for mm in (50, 80, 200, 400, 500):
        ok = safety.tof_ok(mm)
        print(f"  {mm} mm → {'OK' if ok else 'FAIL'}")

    print()
    print("Change mock distance: TOF_MOCK_MM=350 python scripts/test_tof.py")
    print("In main.py, TOF is read once per feed cycle in DETECT_MOUTH state.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
