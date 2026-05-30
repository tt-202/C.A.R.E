# prints the security codes 
# lcd_display.py

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import os

# =========================================================
# CONFIG
# =========================================================

WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 700

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_FOLDER = os.path.join(BASE_DIR, "images")

SECTION_IMAGES = {
    1: "section1.png",
    2: "section2.png",
    3: "section3.png",
    4: "section4.png"
}

# =========================================================
# MAIN GUI
# =========================================================

class FeedingRobotGUI:

    def __init__(self, root):
        self.root = root
        self.root.title("Feeding Robot Control Panel")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg="#1e1e1e")

        # -----------------------------
        # VARIABLES
        # -----------------------------
        self.connection_status = tk.StringVar(value="NOT CONNECTED")
        self.current_state = tk.StringVar(value="DEFAULT")
        self.error_message = tk.StringVar(value="NONE")
        self.selected_section = tk.IntVar(value=1)

        # -----------------------------
        # TITLE
        # -----------------------------
        title = tk.Label(
            root,
            text="AUTONOMOUS FEEDING SYSTEM",
            font=("Arial", 24, "bold"),
            bg="#1e1e1e",
            fg="white"
        )
        title.pack(pady=15)

        # -----------------------------
        # MAIN FRAME
        # -----------------------------
        main_frame = tk.Frame(root, bg="#1e1e1e")
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        # LEFT PANEL
        self.left_panel = tk.Frame(
            main_frame,
            bg="#2a2a2a",
            width=450
        )
        self.left_panel.pack(side="left", fill="y", padx=10)

        # RIGHT PANEL
        self.right_panel = tk.Frame(
            main_frame,
            bg="#2a2a2a"
        )
        self.right_panel.pack(side="right", fill="both", expand=True, padx=10)

        self.create_status_panel()
        self.create_plate_panel()

    # =====================================================
    # LEFT PANEL
    # =====================================================

    def create_status_panel(self):

        header = tk.Label(
            self.left_panel,
            text="SYSTEM STATUS",
            font=("Arial", 20, "bold"),
            bg="#2a2a2a",
            fg="white"
        )
        header.pack(pady=20)

        # Connection Status
        self.create_info_box(
            "Connection Status",
            self.connection_status
        )

        # State
        self.create_info_box(
            "Current State",
            self.current_state
        )

        # Error
        self.create_info_box(
            "Error",
            self.error_message,
            height=4
        )

        # Buttons
        button_frame = tk.Frame(self.left_panel, bg="#2a2a2a")
        button_frame.pack(pady=30)

        ttk.Button(
            button_frame,
            text="CONNECTED",
            command=lambda: self.update_connection(True)
        ).grid(row=0, column=0, padx=5, pady=5)

        ttk.Button(
            button_frame,
            text="DISCONNECTED",
            command=lambda: self.update_connection(False)
        ).grid(row=0, column=1, padx=5, pady=5)

        ttk.Button(
            button_frame,
            text="FEEDING",
            command=lambda: self.update_state("FEEDING")
        ).grid(row=1, column=0, padx=5, pady=5)

        ttk.Button(
            button_frame,
            text="DEFAULT",
            command=lambda: self.update_state("DEFAULT")
        ).grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(
            button_frame,
            text="EMERGENCY",
            command=lambda: self.update_state("EMERGENCY")
        ).grid(row=2, column=0, padx=5, pady=5)

        # Example Errors
        ttk.Button(
            button_frame,
            text="NO FOOD",
            command=lambda: self.update_error("NO FOOD ON PLATE OR SPOON")
        ).grid(row=3, column=0, padx=5, pady=5)

        ttk.Button(
            button_frame,
            text="NO FACE",
            command=lambda: self.update_error("NO FACE DETECTED")
        ).grid(row=3, column=1, padx=5, pady=5)

        ttk.Button(
            button_frame,
            text="MULTIPLE FACES",
            command=lambda: self.update_error("MULTIPLE FACES DETECTED")
        ).grid(row=4, column=0, padx=5, pady=5)

        ttk.Button(
            button_frame,
            text="CLEAR ERROR",
            command=lambda: self.update_error("NONE")
        ).grid(row=4, column=1, padx=5, pady=5)

    def create_info_box(self, title, variable, height=2):

        frame = tk.Frame(
            self.left_panel,
            bg="#3a3a3a",
            bd=2,
            relief="ridge"
        )
        frame.pack(fill="x", padx=20, pady=10)

        label = tk.Label(
            frame,
            text=title,
            font=("Arial", 14, "bold"),
            bg="#3a3a3a",
            fg="#cccccc"
        )
        label.pack(anchor="w", padx=10, pady=(10, 0))

        value_label = tk.Label(
            frame,
            textvariable=variable,
            font=("Arial", 18),
            bg="#3a3a3a",
            fg="white",
            wraplength=350,
            justify="left",
            height=height
        )
        value_label.pack(anchor="w", padx=10, pady=10)

    # =====================================================
    # RIGHT PANEL
    # =====================================================

    def create_plate_panel(self):

        header = tk.Label(
            self.right_panel,
            text="PLATE SELECTION",
            font=("Arial", 20, "bold"),
            bg="#2a2a2a",
            fg="white"
        )
        header.pack(pady=20)

        # Section Buttons
        section_frame = tk.Frame(self.right_panel, bg="#2a2a2a")
        section_frame.pack(pady=10)

        for i in range(1, 5):
            btn = ttk.Button(
                section_frame,
                text=f"Section {i}",
                command=lambda x=i: self.change_section(x)
            )
            btn.grid(row=0, column=i-1, padx=10)

        # Current Section Label
        self.section_label = tk.Label(
            self.right_panel,
            text="Current Section: 1",
            font=("Arial", 16, "bold"),
            bg="#2a2a2a",
            fg="white"
        )
        self.section_label.pack(pady=10)

        # Image Display
        self.image_label = tk.Label(
            self.right_panel,
            bg="#2a2a2a"
        )
        self.image_label.pack(pady=10, expand=True)

        self.load_plate_image(1)

    # =====================================================
    # IMAGE HANDLING
    # =====================================================

    def load_plate_image(self, section):

        image_path = os.path.join(
            IMAGE_FOLDER,
            SECTION_IMAGES[section]
        )

        try:
            image = Image.open(image_path)

            image = image.resize((500, 500))

            photo = ImageTk.PhotoImage(image)

            self.image_label.configure(image=photo)
            self.image_label.image = photo

        except Exception as e:

            self.image_label.configure(
                image="",
                text=f"Could not load image:\n{image_path}",
                fg="red",
                font=("Arial", 14)
            )
        print("Trying to load:", image_path)
        print("Exists:", os.path.exists(image_path))
    
    # =====================================================
    # UPDATE FUNCTIONS
    # =====================================================

    def update_connection(self, connected):

        if connected:
            self.connection_status.set("CONNECTED")
        else:
            self.connection_status.set("NOT CONNECTED")

    def update_state(self, state):
        self.current_state.set(state)

    def update_error(self, error):
        self.error_message.set(error)

    def change_section(self, section):

        self.selected_section.set(section)

        self.section_label.config(
            text=f"Current Section: {section}"
        )

        self.load_plate_image(section)

# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = FeedingRobotGUI(root)

    root.mainloop()