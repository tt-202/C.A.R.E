import os

# Adafruit Blinka checks this name when deciding which Jetson pin map to use.
os.environ["JETSON_MODEL_NAME"] = "JETSON_ORIN_NANO"

import time
import board
import busio
import adafruit_vl53l1x


# Opens the Jetson I2C bus, creates the VL53L1X sensor, and starts continuous distance measurement.
def initialize_tof_sensor():
    i2c = busio.I2C(board.SCL, board.SDA)
    sensor = adafruit_vl53l1x.VL53L1X(i2c)
    sensor.start_ranging()
    return sensor


# Stops the sensor from taking additional measurements.
# Checking for None also makes cleanup safe if initialization failed.
def close_tof_sensor(sensor):
    if sensor is not None:
        sensor.stop_ranging()


# Takes several measurements, averages them, and then closes the sensor.
# This one-time reading is used to determine the plate's Z distance
# during AprilTag calibration.
def get_single_tof_distance_and_close(samples=5):
    sensor = None
    distances = []

    try:
        sensor = initialize_tof_sensor()

        # Continue until the requested number of valid readings is collected.
        while len(distances) < samples:
            # A measurement should only be read when the sensor says it is ready.
            if sensor.data_ready:
                distance = sensor.distance

                # Ignore an empty sensor response.
                if distance is not None:
                    distances.append(distance)

                # Tell the sensor that this measurement has been handled.
                sensor.clear_interrupt()

            # Avoid checking the sensor continuously at full CPU speed.
            time.sleep(0.1)

        # Averaging several readings reduces the effect of a noisy sample.
        average_distance = sum(distances) / len(distances)
        return round(average_distance, 2)

    finally:
        # The finally block runs after success and after any exception,
        # ensuring that the sensor is stopped in either case.
        close_tof_sensor(sensor)