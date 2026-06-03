"""
Operator panel — matches jetson_controller/gui/lcd_display.py layout.

- Left: connection, state, bites, AprilTag section, errors
- Right: PLATE SELECTION — Section 1–4 buttons + section image (like lcd_display.py)
"""

from __future__ import annotations

import logging
import queue
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 700

GUI_DIR = Path(__file__).resolve().parent
DEFAULT_IMAGE_DIR = GUI_DIR / "images"
LEGACY_IMAGE_DIR = GUI_DIR.parent.parent / "jetson_controller" / "gui" / "images"

SECTION_IMAGES = {
    1: "section1.png",
    2: "section2.png",
    3: "section3.png",
    4: "section4.png",
}


class FeedingRobotGUI:
    """Same structure as jetson_controller/gui/lcd_display.py FeedingRobotGUI."""

    def __init__(
        self,
        root: Any,
        *,
        image_dir: Path,
        on_section_click: Callable[[int], None] | None = None,
    ) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self._tk = tk
        self._ttk = ttk
        self.image_dir = image_dir
        self._on_section_click = on_section_click

        self.root.title("Feeding Robot Control Panel")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.configure(bg="#1e1e1e")

        self.connection_status = tk.StringVar(value="NOT CONNECTED")
        self.current_state = tk.StringVar(value="DEFAULT")
        self.error_message = tk.StringVar(value="NONE")
        self.bites_label = tk.StringVar(value="Bites: 0")
        self.section_source = tk.StringVar(value="Section: —")
        self.selected_section = tk.IntVar(value=1)

        title = tk.Label(
            root,
            text="AUTONOMOUS FEEDING SYSTEM",
            font=("Arial", 24, "bold"),
            bg="#1e1e1e",
            fg="white",
        )
        title.pack(pady=15)

        main_frame = tk.Frame(root, bg="#1e1e1e")
        main_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.left_panel = tk.Frame(main_frame, bg="#2a2a2a", width=450)
        self.left_panel.pack(side="left", fill="y", padx=10)

        self.right_panel = tk.Frame(main_frame, bg="#2a2a2a")
        self.right_panel.pack(side="right", fill="both", expand=True, padx=10)

        self._build_status_panel()
        self._build_plate_panel()

    def _build_status_panel(self) -> None:
        tk = self._tk
        tk.Label(
            self.left_panel,
            text="SYSTEM STATUS",
            font=("Arial", 20, "bold"),
            bg="#2a2a2a",
            fg="white",
        ).pack(pady=20)

        for title, var, height in (
            ("Connection Status", self.connection_status, 2),
            ("Current State", self.current_state, 2),
            ("Plate Section (AprilTag)", self.section_source, 2),
            ("Bites (session)", self.bites_label, 2),
            ("Error", self.error_message, 4),
        ):
            self._info_box(title, var, height=height)

        tk.Label(
            self.left_panel,
            text="AprilTag picks quadrant on plate.\nSection buttons = manual override.",
            font=("Arial", 11),
            bg="#2a2a2a",
            fg="#aaaaaa",
            wraplength=380,
            justify="left",
        ).pack(pady=12, padx=16)

    def _info_box(self, title: str, variable: Any, *, height: int = 2) -> None:
        tk = self._tk
        frame = tk.Frame(self.left_panel, bg="#3a3a3a", bd=2, relief="ridge")
        frame.pack(fill="x", padx=20, pady=8)
        tk.Label(frame, text=title, font=("Arial", 14, "bold"), bg="#3a3a3a", fg="#cccccc").pack(
            anchor="w", padx=10, pady=(10, 0)
        )
        tk.Label(
            frame,
            textvariable=variable,
            font=("Arial", 16),
            bg="#3a3a3a",
            fg="white",
            wraplength=350,
            justify="left",
            height=height,
        ).pack(anchor="w", padx=10, pady=10)

    def _build_plate_panel(self) -> None:
        tk, ttk = self._tk, self._ttk
        tk.Label(
            self.right_panel,
            text="PLATE SELECTION",
            font=("Arial", 20, "bold"),
            bg="#2a2a2a",
            fg="white",
        ).pack(pady=20)

        section_frame = tk.Frame(self.right_panel, bg="#2a2a2a")
        section_frame.pack(pady=10)

        for i in range(1, 5):
            ttk.Button(
                section_frame,
                text=f"Section {i}",
                command=lambda x=i: self._section_clicked(x),
            ).grid(row=0, column=i - 1, padx=10)

        self.section_label = tk.Label(
            self.right_panel,
            text="Current Section: 1",
            font=("Arial", 16, "bold"),
            bg="#2a2a2a",
            fg="white",
        )
        self.section_label.pack(pady=10)

        self.image_label = tk.Label(self.right_panel, bg="#2a2a2a")
        self.image_label.pack(pady=10, expand=True)

        self.load_plate_image(1)

    def _section_clicked(self, section: int) -> None:
        self.change_section(section, source=f"Manual → Section {section}")
        if self._on_section_click is not None:
            self._on_section_click(section)

    def load_plate_image(self, section: int) -> None:
        from PIL import Image, ImageTk

        name = SECTION_IMAGES.get(section, "section1.png")
        for folder in (self.image_dir, LEGACY_IMAGE_DIR):
            path = folder / name
            if path.is_file():
                try:
                    image = Image.open(path).resize((500, 500))
                    photo = ImageTk.PhotoImage(image)
                    self.image_label.configure(image=photo, text="")
                    self.image_label.image = photo
                    return
                except Exception as e:
                    logger.warning("Could not load %s: %s", path, e)

        self.image_label.configure(
            image="",
            text=f"Section {section}\n(add gui/images/{name})",
            fg="#cccccc",
            font=("Arial", 18),
        )

    def update_connection(self, connected: bool) -> None:
        self.connection_status.set("CONNECTED" if connected else "NOT CONNECTED")

    def update_state(self, state: str) -> None:
        self.current_state.set(state)

    def update_error(self, error: str) -> None:
        self.error_message.set(error if error else "NONE")

    def update_bites(self, total: int) -> None:
        self.bites_label.set(f"Bites: {total}")

    def update_section_source(self, text: str) -> None:
        self.section_source.set(text if text else "—")

    def change_section(self, section: int, *, source: str | None = None) -> None:
        self.selected_section.set(section)
        self.section_label.config(text=f"Current Section: {section}")
        if source:
            self.section_source.set(source)
        self.load_plate_image(section)


class OperatorDisplay:
    """
    Tk must run on the main thread (required on macOS).

    Typical use:
      display.setup()
      threading.Thread(target=machine.run, daemon=True).start()
      display.run_mainloop()  # blocks
    """

    def __init__(
        self,
        *,
        image_dir: str | None = None,
        fullscreen: bool = False,
        on_manual_section: Callable[[int], None] | None = None,
    ) -> None:
        self.image_dir = Path(image_dir) if image_dir else DEFAULT_IMAGE_DIR
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self.fullscreen = fullscreen
        self._on_manual_section = on_manual_section
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._app: FeedingRobotGUI | None = None
        self.root: Any = None

    def setup(self) -> None:
        """Create the window on the current (main) thread."""
        if self.root is not None:
            return
        import tkinter as tk

        root = tk.Tk()
        if self.fullscreen:
            root.attributes("-fullscreen", True)

        def on_click(section: int) -> None:
            if self._on_manual_section is not None:
                self._on_manual_section(section)

        self.root = root
        self._app = FeedingRobotGUI(
            root,
            image_dir=self.image_dir,
            on_section_click=on_click,
        )
        self._schedule_poll(root)

    def run_mainloop(self) -> None:
        if self.root is None:
            self.setup()
        self.root.mainloop()

    def start(self) -> None:
        """Create window only — call run_mainloop() to show it (main thread)."""
        self.setup()

    def _schedule_poll(self, root: Any) -> None:
        self._drain_queue()
        root.after(100, lambda: self._schedule_poll(root))

    def _drain_queue(self) -> None:
        if self._app is None:
            return
        while True:
            try:
                msg = self._queue.get_nowait()
            except queue.Empty:
                break
            self._apply(msg)

    def _apply(self, msg: dict[str, Any]) -> None:
        app = self._app
        if app is None:
            return
        if "connected" in msg:
            app.update_connection(bool(msg["connected"]))
        if "state" in msg:
            app.update_state(str(msg["state"]))
        if "error" in msg:
            app.update_error(str(msg["error"]))
        if "section" in msg:
            app.change_section(int(msg["section"]), source=msg.get("section_source"))
        elif "section_source" in msg:
            app.update_section_source(str(msg["section_source"]))
        if "bites" in msg:
            app.update_bites(int(msg["bites"]))

    def update(self, **kwargs: Any) -> None:
        self._queue.put(kwargs)

    def stop(self) -> None:
        self.update(state="STOPPED")
