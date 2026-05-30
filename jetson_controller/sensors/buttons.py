from sensors.buttons import ButtonManager

buttons = ButtonManager()

while True:

    if buttons.feed_pressed():
        print("Feed button pressed")

    if buttons.plate_pressed():
        print("Plate button pressed")

    if buttons.estop_pressed():
        print("EMERGENCY STOP")