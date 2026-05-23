# Initializes everything

from robotics.arm_controller import ArmController

from perception.yolo_detector import YOLODetector
from feeding_robot.perception.yolo_detector import MouthDetector
from perception.april_tag_detector import AprilTagDetector

from sensors.buttons import ButtonManager
from sensors.tof_sensor import TOFSensor

from gui.lcd_display import LCDDisplay

from state_machine.state_machine import FeedingStateMachine

import time

def main():

    print("Initializing System...")

    arm = ArmController()

    yolo = YOLODetector()

    mouth = MouthDetector()

    apriltag = AprilTagDetector()

    buttons = ButtonManager()

    tof = TOFSensor()

    lcd = LCDDisplay()

    machine = FeedingStateMachine(
        arm,
        yolo,
        mouth,
        apriltag,
        buttons,
        tof,
        lcd
    )

    arm.home()

    while True:

        machine.update()

        time.sleep(0.1)

if __name__ == "__main__":
    main()