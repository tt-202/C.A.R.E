"""
Cartesian poses for myCobot (x, y, z, rx, ry, rz) in mm / degrees.

Values ported from jetson_controller (arm home + state_machine_logic).
Calibrate on your rig before production use.
"""

from __future__ import annotations

# Safe park / retract — matches jetson_controller ArmController.home()
HOME_COORDS: list[float] = [200, 0, 200, 180, 0, 0]

# Plate quadrant poses — calibrate each section on your 4-part plate
PLATE_1: list[float] = [220, -120, 120, 180, 0, 0]
PLATE_2: list[float] = [220, -40, 120, 180, 0, 0]
PLATE_3: list[float] = [220, 40, 120, 180, 0, 0]
PLATE_4: list[float] = [220, 120, 120, 180, 0, 0]

# Approach in front of user for mouth alignment + feed
USER_FEED: list[float] = [180, 0, 160, 180, 0, 0]

# Slight Z dip for scoop motion at plate (added to plate pose Z)
SCOOP_Z_DELTA_MM: float = -25.0

# Per-section plate pick (care-app sectionNum 1–4)
SECTION_PLATE: dict[int, list[float]] = {
    1: PLATE_1,
    2: PLATE_2,
    3: PLATE_3,
    4: PLATE_4,
}
