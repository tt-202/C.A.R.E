from enum import Enum

class RobotState(Enum):
    IDLE = 0
    WAIT_FOR_FEED_BUTTON = 1
    CHECK_SPOON = 2
    MOVE_TO_PLATE = 3
    CHECK_PLATE_FOOD = 4
    SCOOP_FOOD = 5
    VERIFY_SPOON_FULL = 6
    MOVE_TO_USER = 7
    ALIGN_TO_MOUTH = 8
    FEED_USER = 9
    RETURN_HOME = 10
    EMERGENCY_STOP = 11
    ERROR = 12