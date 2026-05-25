# State machines

from state_machine.states import RobotState
from robotics.coordinates import *
import time

class FeedingStateMachine:

    def __init__(
        self,
        arm,
        yolo,
        mouth,
        apriltag,
        buttons,
        tof,
        lcd
    ):

        self.arm = arm
        self.yolo = yolo
        self.mouth = mouth
        self.apriltag = apriltag
        self.buttons = buttons
        self.tof = tof
        self.lcd = lcd

        self.state = RobotState.IDLE

        self.selected_plate = 1

    def update(self):

        if self.buttons.estop_pressed():

            self.state = RobotState.EMERGENCY_STOP

        if self.state == RobotState.IDLE:

            self.lcd.show_status("IDLE")

            if self.buttons.feed_pressed():
                self.state = RobotState.CHECK_SPOON

        elif self.state == RobotState.CHECK_SPOON:

            self.lcd.show_status("CHECK SPOON")

            spoon_has_food = False

            if spoon_has_food:
                self.state = RobotState.MOVE_TO_USER
            else:
                self.state = RobotState.MOVE_TO_PLATE

        elif self.state == RobotState.MOVE_TO_PLATE:

            self.lcd.show_status("MOVE TO PLATE")

            if self.selected_plate == 1:
                self.arm.move_coords(PLATE_1)

            elif self.selected_plate == 2:
                self.arm.move_coords(PLATE_2)

            self.arm.wait_until_done()

            self.state = RobotState.CHECK_PLATE_FOOD

        elif self.state == RobotState.CHECK_PLATE_FOOD:

            food_exists = True

            if food_exists:
                self.state = RobotState.SCOOP_FOOD
            else:
                self.state = RobotState.ERROR

        elif self.state == RobotState.SCOOP_FOOD:

            self.lcd.show_status("SCOOPING")

            time.sleep(2)

            self.state = RobotState.VERIFY_SPOON_FULL

        elif self.state == RobotState.VERIFY_SPOON_FULL:

            spoon_full = True

            if spoon_full:
                self.state = RobotState.MOVE_TO_USER
            else:
                self.state = RobotState.MOVE_TO_PLATE

        elif self.state == RobotState.MOVE_TO_USER:

            self.arm.move_coords(USER_FEED)

            self.arm.wait_until_done()

            self.state = RobotState.ALIGN_TO_MOUTH

        elif self.state == RobotState.ALIGN_TO_MOUTH:

            distance = self.tof.get_distance_mm()

            if distance < 100:
                self.state = RobotState.ERROR

            mouth = True

            if mouth:
                self.state = RobotState.FEED_USER

        elif self.state == RobotState.FEED_USER:

            self.lcd.show_status("FEEDING")

            time.sleep(2)

            self.state = RobotState.RETURN_HOME

        elif self.state == RobotState.RETURN_HOME:

            self.arm.home()

            self.state = RobotState.IDLE

        elif self.state == RobotState.EMERGENCY_STOP:

            self.arm.stop_motion()

            self.lcd.show_status("EMERGENCY STOP")

        elif self.state == RobotState.ERROR:

            self.arm.stop_motion()

            self.lcd.show_status("ERROR")

# mouth detection!!!!!
# from vision_module import get_mouth_state

# state = get_mouth_state()

# dx, dy = state["offset"]

# if state["is_open"]:
#     # trigger feeding action
#     pass

# Use dx/dy as error for motion correction
# make sure, ONE FACE AS WELL, ELSE SEND A COMMAND TO LCD_DISPLAY for ERROR
#