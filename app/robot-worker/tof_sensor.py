import os
os.environ["JETSON_MODEL_NAME"] = "JETSON_ORIN_NANO"

import time
import board
import busio
import adafruit_vl53l1x


def initialize_tof_sensor():
    i2c = busio.I2C(board.SCL, board.SDA)
    sensor = adafruit_vl53l1x.VL53L1X(i2c)
    sensor.start_ranging()
    return sensor


def close_tof_sensor(sensor):
    if sensor is not None:
        sensor.stop_ranging()


def get_single_tof_distance_and_close(samples=5):
    sensor = None
    distances = []

    try:
        sensor = initialize_tof_sensor()

        while len(distances) < samples:
            if sensor.data_ready:
                distance = sensor.distance

                if distance is not None:
                    distances.append(distance)

                sensor.clear_interrupt()

            time.sleep(0.1)

        average_distance = sum(distances) / len(distances)
        return round(average_distance, 2)

    finally:
        close_tof_sensor(sensor)
