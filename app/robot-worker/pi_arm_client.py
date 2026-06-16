"""TCP client for pi_arm_server_xz_delta.py on the MyCobot 320 Pi."""

from __future__ import annotations

import os
import socket
import time
from typing import Optional


class PiArmClient:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.host = host or os.environ.get("PI_IP", "192.168.50.2")
        self.port = port or int(os.environ.get("PI_PORT", "5001"))
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def connect(self) -> None:
        self.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def send(self, cmd: str) -> str:
        if self.sock is None:
            self.connect()
        assert self.sock is not None
        self.sock.sendall((cmd + "\n").encode())
        buffer = ""
        while "\n" not in buffer:
            chunk = self.sock.recv(1024)
            if not chunk:
                raise RuntimeError("Pi arm server closed the connection")
            buffer += chunk.decode()
        line, _ = buffer.split("\n", 1)
        return line.strip()

    def ping(self) -> str:
        return self.send("PING")

    def stop(self) -> str:
        return self.send("STOP")

    def move_coords(
        self,
        x: float,
        y: float,
        z: float,
        rx: float,
        ry: float,
        rz: float,
        speed: int = 12,
    ) -> str:
        return self.send(
            f"MOVE_COORDS {x:.3f} {y:.3f} {z:.3f} {rx:.3f} {ry:.3f} {rz:.3f} {speed}"
        )

    def xz_delta(self, dx_mm: float, dz_mm: float) -> str:
        return self.send(f"XZ_DELTA {dx_mm:.2f} {dz_mm:.2f}")

    def feed(self) -> str:
        return self.send("FEED")

    def feed_pause(self) -> str:
        return self.send("FEED_PAUSE")

    def view_selection(self) -> str:
        return self.send("VIEW_SELECTION")

    def view_mouth(self) -> str:
        return self.send("VIEW_MOUTH")

    def section_pick(self, section: int) -> str:
        return self.send(f"SECTION_PICK {section}")

    def __enter__(self) -> "PiArmClient":
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def wait_after_move(seconds: float | None = None) -> None:
    delay = seconds if seconds is not None else float(os.environ.get("ARM_MOVE_SETTLE", "2.0"))
    time.sleep(delay)
