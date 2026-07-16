#!/usr/bin/env python3

import argparse
import sys

from april_tag_with_value_update import get_initial_plate_coordinates


# Provides a command-line entry point for plate calibration.
# feeding_cycle.py runs this file as a subprocess and checks its exit code:
# 0 means calibration succeeded, while 1 means calibration failed.
def main():
    parser = argparse.ArgumentParser()

    # When supplied, --preview displays the camera image and detected tags.
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()

    print("Starting look-down plate calibration...", flush=True)

    try:
        coordinates = get_initial_plate_coordinates(
            camera_index=0,
            timeout_seconds=20,
            save_to_file=True,
            show_preview=args.preview,
        )

    except Exception as error:
        # Return a nonzero exit code so the parent feeding process knows
        # the user must retry calibration.
        print(f"Plate calibration failed: {error}", flush=True)
        return 1

    # Print the generated coordinates for the operator and robot logs.
    print("\nCalibration complete.", flush=True)
    print("---------------------", flush=True)
    print(f"Plate Center: {coordinates['plate_center']}", flush=True)
    print(f"Plate Z: {coordinates['plate_z_cm']} cm", flush=True)
    print(f"Section 1 3D: {coordinates['sections_3d'][1]}", flush=True)
    print(f"Section 2 3D: {coordinates['sections_3d'][2]}", flush=True)
    print(f"Section 3 3D: {coordinates['sections_3d'][3]}", flush=True)
    print(f"Section 4 3D: {coordinates['sections_3d'][4]}", flush=True)

    # A zero exit code indicates successful calibration.
    return 0


if __name__ == "__main__":
    sys.exit(main())