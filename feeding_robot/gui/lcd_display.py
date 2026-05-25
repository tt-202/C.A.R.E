# prints the security codes 
# lcd_display.py

current_message = ""

def set_message(msg):
    global current_message
    current_message = msg
    print("LCD:", msg)  # replace with Tkinter label update later