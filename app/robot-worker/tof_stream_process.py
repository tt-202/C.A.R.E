#!/usr/bin/env python3

import os

# Adafruit Blinka uses this value to select the Jetson Orin Nano pin map.
os.environ["JETSON_MODEL_NAME"] = "JETSON_ORIN_NANO"

import json
import time

import board
import busio
import adafruit_vl53l1x


# The process checks for a new ToF measurement every 50 milliseconds.
PRINT_PERIOD_SECONDS = 0.05

def main():
    sensor = None

    try:
        # Open the Jetson I2C bus and create the VL53L1X sensor object.
        i2c = busio.I2C(board.SCL, board.SDA)
        sensor = adafruit_vl53l1x.VL53L1X(i2c)

        # Inform the parent process that the sensor initialized successfully.
        print(json.dumps({
            "type": "status",
            "message": "tof_initialized",
        }), flush=True)

        # Begin continuous distance measurement.
        sensor.start_ranging()

        while True:
            # Only read the sensor when a new measurement is available.
            if sensor.data_ready:
                distance_cm = sensor.distance

                # Acknowledge the measurement so the sensor can prepare another.
                sensor.clear_interrupt()

                if distance_cm is not None:
                    # stdout acts as the communication channel between this
                    # sensor process and tof_subprocess.py.
                    #
                    # flush=True sends each reading immediately instead of
                    # allowing Python to hold it in an output buffer.
                    print(json.dumps({
                        "type": "distance",
                        "distance_cm": float(distance_cm),
                    }), flush=True)

            # Prevent the loop from continuously consuming a full CPU core.
            time.sleep(PRINT_PERIOD_SECONDS)

    except KeyboardInterrupt:
        # Ctrl+C is treated as a normal shutdown.
        pass

    except Exception as e:
        # Keep errors in JSON format so the parent process can recognize
        # and log them without crashing its reader thread.
        print(json.dumps({
            "type": "error",
            "message": str(e),
        }), flush=True)

    finally:
        # Stop the sensor even if the process is interrupted or an error occurs.
        if sensor is not None:
            try:
                sensor.stop_ranging()
            except Exception:
                # Do not allow a cleanup error to prevent process shutdown.
                pass

        # Inform the parent process that ToF streaming has stopped.
        print(json.dumps({
            "type": "status",
            "message": "tof_stopped",
        }), flush=True)

if __name__ == "__main__":
    main()