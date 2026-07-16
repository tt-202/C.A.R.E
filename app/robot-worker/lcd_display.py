#!/usr/bin/env python3
"""
LCD UI for the Jetson panel.

  python3 lcd_display.py           # poke at buttons yourself
  python3 lcd_display.py --stdin   # worker/lcd_gui pipes JSON at us

We don't touch GPIO — just draw whatever comes in.
"""

import argparse
import json
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk


# waveshare size on our setup
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 480

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_FOLDER = os.path.join(BASE_DIR, "images")

SECTION_IMAGES = {
    1: "section1.png",
    2: "section2.png",
    3: "section3.png",
    4: "section4.png",
}

# left "State" box — unknown ones just get uppercased
STATE_LABELS = {
    "startup": "STARTUP",
    "idle": "IDLE",
    "selection": "SELECTION",
    "scooping": "SCOOPING",
    "scoop_complete": "SCOOP COMPLETE",
    "feeding": "FEEDING",
    "mouth_tracking_starting": "MOUTH TRACKING STARTING",
    "mouth_tracking": "MOUTH TRACKING",
    "mouth_centered": "MOUTH CENTERED",
    "approach": "APPROACHING MOUTH",
    "bite_hold_pending": "BITE HOLD PENDING",
    "bite_hold_ready": "BITE HOLD",
    "holding": "HOLDING",
    "plate_checking": "PLATE CHECK",
    "plate_full": "PLATE FULL",
    "plate_empty": "PLATE EMPTY",
    "plate_unknown": "PLATE UNKNOWN",
    "spoon_checking": "SPOON CHECK",
    "spoon_full": "SPOON FULL",
    "spoon_empty": "SPOON EMPTY",
    "spoon_unknown": "SPOON UNKNOWN",
    "recovery": "RECOVERY",
    "emergency": "EMERGENCY STOP",
    "error": "ERROR",
    "shutdown": "SHUTDOWN",
}


class FeedingRobotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("C.A.R.E Feeding Robot Control Panel")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.attributes("-fullscreen", True)
        
        # Esc so you can get out when testing on a laptop
        self.root.bind("<Escape>", lambda _e: self.root.attributes("-fullscreen", False))
        self.root.configure(bg="#1e1e1e")

        self.connection_status = tk.StringVar(value="NOT CONNECTED")
        self.current_state = tk.StringVar(value="STARTUP")
        self.error_message = tk.StringVar(value="NONE")
        self.status_message = tk.StringVar(value="Starting GUI...")
        self.selected_section = tk.IntVar(value=1)

        title = tk.Label(
            root,
            text="C.A.R.E AUTONOMOUS FEEDING SYSTEM",
            font=("Arial", 16, "bold"),
            bg="#1e1e1e",
            fg="white",
        )
        title.pack(pady=5)

        main_frame = tk.Frame(root, bg="#1e1e1e")
        main_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # status left, plate pic right
        self.left_panel = tk.Frame(main_frame, bg="#2a2a2a", width=260)
        self.left_panel.pack(side="left", fill="y", padx=5)

        self.right_panel = tk.Frame(main_frame, bg="#2a2a2a")
        self.right_panel.pack(side="right", fill="both", expand=True, padx=5)

        self.create_status_panel()
        self.create_plate_panel()

    def create_status_panel(self):
        header = tk.Label(
            self.left_panel,
            text="SYSTEM STATUS",
            font=("Arial", 14, "bold"),
            bg="#2a2a2a",
            fg="white",
        )
        header.pack(pady=10)

        self.create_info_box("Connection", self.connection_status)
        self.create_info_box("State", self.current_state)
        self.create_info_box("Message", self.status_message, height=3)
        self.create_info_box("Error", self.error_message, height=3)

        # fake buttons for desk demo — not wired to real SELECT/FEED
        button_frame = tk.Frame(self.left_panel, bg="#2a2a2a")
        button_frame.pack(pady=8)

        ttk.Button(
            button_frame,
            text="TEST SECTION",
            command=self.next_section,
        ).grid(row=0, column=0, padx=3, pady=3)

        ttk.Button(
            button_frame,
            text="TEST EMERGENCY",
            command=lambda: self.apply_update({
                "state": "emergency",
                "message": "Emergency stop test",
                "emergency": True,
            }),
        ).grid(row=0, column=1, padx=3, pady=3)

        ttk.Button(
            button_frame,
            text="CLEAR ERROR",
            command=lambda: self.apply_update({
                "state": "idle",
                "message": "System ready",
                "emergency": False,
                "error": "NONE",
            }),
        ).grid(row=1, column=0, columnspan=2, padx=3, pady=3)

    def create_info_box(self, title, variable, height=2):
        frame = tk.Frame(self.left_panel, bg="#3a3a3a", bd=1, relief="ridge")
        frame.pack(fill="x", padx=10, pady=5)

        label = tk.Label(
            frame,
            text=title,
            font=("Arial", 11, "bold"),
            bg="#3a3a3a",
            fg="#cccccc",
        )
        label.pack(anchor="w", padx=5, pady=(5, 0))

        value_label = tk.Label(
            frame,
            textvariable=variable,
            font=("Arial", 12),
            bg="#3a3a3a",
            fg="white",
            wraplength=215,
            justify="left",
            height=height,
        )
        value_label.pack(anchor="w", padx=5, pady=5)

    def create_plate_panel(self):
        header = tk.Label(
            self.right_panel,
            text="PLATE SELECTION",
            font=("Arial", 14, "bold"),
            bg="#2a2a2a",
            fg="white",
        )
        header.pack(pady=10)

        section_frame = tk.Frame(self.right_panel, bg="#2a2a2a")
        section_frame.pack(pady=5)

        for i in range(1, 5):
            # x=i — classic python for-loop trap
            btn = ttk.Button(
                section_frame,
                text=f"Section {i}",
                command=lambda x=i: self.change_section(x),
            )
            btn.grid(row=0, column=i - 1, padx=5)

        self.section_label = tk.Label(
            self.right_panel,
            text="Current Section: 1",
            font=("Arial", 12, "bold"),
            bg="#2a2a2a",
            fg="white",
        )
        self.section_label.pack(pady=5)

        self.image_label = tk.Label(self.right_panel, bg="#2a2a2a")
        self.image_label.pack(pady=5)

        self.load_plate_image(1)

    def load_plate_image(self, section):
        image_name = SECTION_IMAGES.get(section, SECTION_IMAGES[1])
        image_path = os.path.join(IMAGE_FOLDER, image_name)

        try:
            image = Image.open(image_path)
            image.thumbnail((380, 380))
            photo = ImageTk.PhotoImage(image)

            self.image_label.configure(image=photo, text="")
            self.image_label.image = photo  # gotta keep this or it vanishes
        except Exception as e:
            self.image_label.configure(
                image="",
                text=f"Could not load image:\n{image_path}",
                fg="red",
                font=("Arial", 10),
            )
            print(f"[GUI ERROR] Could not load plate image: {e}", flush=True)

    def update_connection(self, connected):
        self.connection_status.set("CONNECTED" if connected else "NOT CONNECTED")

    def update_state(self, state):
        self.current_state.set(STATE_LABELS.get(str(state), str(state).upper()))

    def update_error(self, error):
        self.error_message.set(error if error else "NONE")

    def update_message(self, message):
        self.status_message.set(message if message else "")

    def change_section(self, section):
        try:
            section = int(section)
        except Exception:
            section = 1

        if section < 1 or section > 4:
            section = 1

        self.selected_section.set(section)
        self.section_label.config(text=f"Current Section: {section}")
        self.load_plate_image(section)

    def next_section(self):
        next_value = (self.selected_section.get() % 4) + 1  # 1→2→3→4→1
        self.change_section(next_value)
        self.update_message(f"Selected plate section {next_value}")

    def apply_update(self, msg):
        # one JSON blob from lcd_gui — fields can be missing, that's fine
        if "connected" in msg:
            self.update_connection(bool(msg["connected"]))

        emergency = bool(msg.get("emergency", False))

        if "state" in msg:
            self.update_state(msg.get("state"))

        if "message" in msg:
            self.update_message(str(msg.get("message", "")))

        if "selected_section" in msg and msg.get("selected_section") is not None:
            self.change_section(msg.get("selected_section"))

        # e-stop wins — jam it into Error so you can't miss it
        if emergency:
            self.update_state("emergency")
            self.update_error(str(msg.get("message", "EMERGENCY STOP ACTIVE")))
        elif "error" in msg:
            self.update_error(str(msg.get("error") or "NONE"))


def stdin_reader(input_queue):
    # background: chew through JSON lines from the worker
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            input_queue.put(json.loads(line))
        except Exception as e:
            print(f"[GUI ERROR] Bad JSON from stdin: {line} | {e}", flush=True)


def poll_queue(root, app, input_queue):
    # Tk hates other threads — only touch widgets from here
    while True:
        try:
            msg = input_queue.get_nowait()
        except queue.Empty:
            break

        try:
            app.apply_update(msg)
        except Exception as e:
            print(f"[GUI ERROR] Could not apply update: {e}", flush=True)

    root.after(50, poll_queue, root, app, input_queue)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read GUI updates as JSON lines from stdin.",
    )
    args = parser.parse_args()

    root = tk.Tk()
    app = FeedingRobotGUI(root)

    if args.stdin:
        input_queue = queue.Queue()
        thread = threading.Thread(target=stdin_reader, args=(input_queue,), daemon=True)
        thread.start()
        root.after(50, poll_queue, root, app, input_queue)

    root.mainloop()


if __name__ == "__main__":
    main()
