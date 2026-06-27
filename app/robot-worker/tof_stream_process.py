#!/usr/bin/env python3

import os
os.environ["JETSON_MODEL_NAME"] = "JETSON_ORIN_NANO"

import json
import time

import board
import busio
import adafruit_vl53l1x


PRINT_PERIOD_SECONDS = 0.05


def main():
    sensor = None

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_vl53l1x.VL53L1X(i2c)

        print(json.dumps({
            "type": "status",
            "message": "tof_initialized",
        }), flush=True)

        sensor.start_ranging()

        while True:
            if sensor.data_ready:
                distance_cm = sensor.distance
                sensor.clear_interrupt()

                if distance_cm is not None:
                    print(json.dumps({
                        "type": "distance",
                        "distance_cm": float(distance_cm),
                    }), flush=True)

            time.sleep(PRINT_PERIOD_SECONDS)

    except KeyboardInterrupt:
        pass

    except Exception as e:
        print(json.dumps({
            "type": "error",
            "message": str(e),
        }), flush=True)

    finally:
        if sensor is not None:
            try:
                sensor.stop_ranging()
            except Exception:
                pass

        print(json.dumps({
            "type": "status",
            "message": "tof_stopped",
        }), flush=True)


if __name__ == "__main__":
    main()
