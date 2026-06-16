#!/usr/bin/env python3

import argparse
import sys

from plate_calibration import get_initial_plate_coordinates


def main():
    parser = argparse.ArgumentParser()
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
        print(f"Plate calibration failed: {error}", flush=True)
        return 1

    print("\nCalibration complete.", flush=True)
    print("---------------------", flush=True)
    print(f"Plate Center: {coordinates['plate_center']}", flush=True)
    print(f"Plate Z: {coordinates['plate_z_cm']} cm", flush=True)
    for n in range(1, 5):
        print(f"Section {n} 3D: {coordinates['sections_3d'][n]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
