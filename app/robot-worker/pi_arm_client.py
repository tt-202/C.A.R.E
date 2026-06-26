"""
JSON TCP client for New_Settings_June26_raspberry/pi_arm_server.py (port 5002).

Commands: PING, VIEW_SELECTION, VIEW_MOUTH, SCOOP, ALIGN, CENTERED,
          APPROACH_MOUTH, STOP, HOME
"""

from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_send_lock = threading.Lock()


class PiArmClient:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.host = host or os.environ.get("PI_IP", "192.168.50.2")
        self.port = port or int(os.environ.get("PI_PORT", "5002"))
        self.timeout = timeout
        self.sock: socket.socket | None = None

    def connect(self) -> None:
        self.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect((self.host, self.port))
        logger.info("Connected to Pi arm server at %s:%s", self.host, self.port)

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _ensure_connected(self) -> socket.socket:
        if self.sock is None:
            self.connect()
        assert self.sock is not None
        return self.sock

    def send_json(self, msg: dict[str, Any], *, wait_reply: bool = True, reply_timeout: float | None = None) -> dict[str, Any] | None:
        sock = self._ensure_connected()
        payload = json.dumps(msg) + "\n"
        with _send_lock:
            sock.sendall(payload.encode())
            if not wait_reply:
                return None
            return self._recv_json(timeout=reply_timeout)

    def _recv_json(self, timeout: float | None = None) -> dict[str, Any]:
        sock = self._ensure_connected()
        if timeout is not None:
            sock.settimeout(timeout)
        buffer = ""
        while "\n" not in buffer:
            chunk = sock.recv(1024)
            if not chunk:
                raise RuntimeError("Pi arm server closed the connection")
            buffer += chunk.decode()
        line, _ = buffer.split("\n", 1)
        return json.loads(line)

    def _ok(self, reply: dict[str, Any] | None, label: str) -> dict[str, Any]:
        if reply is None:
            raise RuntimeError(f"{label}: no reply from Pi")
        if reply.get("status") != "ok":
            raise RuntimeError(f"{label} failed: {reply}")
        return reply

    def ping(self) -> dict[str, Any]:
        return self._ok(self.send_json({"cmd": "PING"}), "PING")

    def stop(self, reason: str = "STOP") -> dict[str, Any] | None:
        try:
            return self.send_json({"cmd": "STOP", "reason": reason}, reply_timeout=0.5)
        except Exception:
            logger.warning("STOP sent (reply optional)")
            return None

    def home(self, reason: str = "HOME") -> dict[str, Any]:
        return self._ok(
            self.send_json({"cmd": "HOME", "reason": reason}, reply_timeout=20.0),
            "HOME",
        )

    def view_selection(self) -> dict[str, Any]:
        return self._ok(self.send_json({"cmd": "VIEW_SELECTION"}), "VIEW_SELECTION")

    def view_mouth(self) -> dict[str, Any]:
        return self._ok(self.send_json({"cmd": "VIEW_MOUTH"}), "VIEW_MOUTH")

    def scoop(self, section: int) -> dict[str, Any]:
        return self._ok(
            self.send_json({"cmd": "SCOOP", "section": int(section)}, reply_timeout=35.0),
            f"SCOOP section {section}",
        )

    def align(self, error_x: float, error_y: float) -> None:
        self.send_json(
            {"cmd": "ALIGN", "error_x": error_x, "error_y": error_y},
            wait_reply=False,
        )

    def centered(self) -> None:
        self.send_json({"cmd": "CENTERED"}, wait_reply=False)

    def approach_mouth(self, tof_cm: float | None) -> None:
        msg: dict[str, Any] = {"cmd": "APPROACH_MOUTH"}
        if tof_cm is not None:
            msg["tof_cm"] = float(tof_cm)
        self.send_json(msg, wait_reply=False)

    def __enter__(self) -> PiArmClient:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def wait_after_move(seconds: float | None = None) -> None:
    delay = seconds if seconds is not None else float(os.environ.get("ARM_MOVE_SETTLE", "2.0"))
    time.sleep(delay)
