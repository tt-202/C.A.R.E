from pymycobot.mycobot import MyCobot
import time

class ArmController:

    def __init__(self, port="/dev/ttyUSB0"):
        self.mc = MyCobot(port, 115200)

    def move_coords(self, coords, speed=30):
        self.mc.send_coords(coords, speed, 0)

    def move_angles(self, angles, speed=30):
        self.mc.send_angles(angles, speed)

    def get_position(self):
        angles = self.mc.get_angles()
        coords = self.mc.get_coords()

        return {
            "angles": angles,
            "coords": coords
        }

    def stop_motion(self):
        self.mc.stop()

    def home(self):
        HOME = [200, 0, 200, 180, 0, 0]
        self.move_coords(HOME)

    def wait_until_done(self, seconds=2):
        time.sleep(seconds)