"""TCP client for pi_arm_server_xz_delta.py on myCobot 320 Pi."""

from __future__ import annotations

import logging
import socket
import time
from typing import Any

from robot.coordinates import HOME_COORDS

logger = logging.getLogger(__name__)


class PiArmSocketController:
    """Same interface as MyCobotController; sends commands to the Pi arm server."""

    def __init__(
        self,
        host: str,
        port: int = 5001,
        *,
        dry_run: bool = True,
        connect_timeout: float = 5.0,
        recv_timeout: float = 10.0,
    ) -> None:
        self.host = host
        self.port = port
        self.dry_run = dry_run
        self.connect_timeout = connect_timeout
        self.recv_timeout = recv_timeout
        self._sock: socket.socket | None = None

    def connect(self) -> None:
        if self.dry_run:
            logger.info("DRY_RUN: skipping Pi arm socket connect to %s:%s", self.host, self.port)
            return
        self._connect()

    def _connect(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.connect_timeout)
        sock.connect((self.host, self.port))
        sock.settimeout(self.recv_timeout)
        self._sock = sock
        logger.info("Connected to Pi arm server at %s:%s", self.host, self.port)
        response = self._send_raw("PING")
        if response is None or not response.startswith("ACK"):
            raise RuntimeError(f"Pi arm server PING failed: {response!r}")

    def _send_raw(self, cmd: str) -> str | None:
        if self._sock is None:
            return None
        try:
            self._sock.sendall((cmd + "\n").encode())
            data = self._sock.recv(1024).decode().strip()
            logger.debug("Pi arm TX=%r RX=%r", cmd, data)
            return data
        except OSError as e:
            logger.warning("Pi arm socket error: %s", e)
            self._sock = None
            return None

    def _send(self, cmd: str) -> str | None:
        if self.dry_run:
            logger.info("DRY_RUN Pi arm: %s", cmd)
            time.sleep(0.2)
            return "ACK"
        if self._sock is None:
            self._connect()
        response = self._send_raw(cmd)
        if response is None:
            self._connect()
            response = self._send_raw(cmd)
        if response is None:
            logger.error("Pi arm command failed after reconnect: %s", cmd)
        else:
            logger.info("Pi arm %s -> %s", cmd.split()[0], response)
        return response

    def stop(self) -> None:
        self._send("STOP")

    def go_home(self) -> None:
        self.move_coords(HOME_COORDS, speed=30)

    def move_coords(self, coords: list[float], *, speed: int = 30, mode: int = 0) -> None:
        del mode  # Pi server always uses mode=1 internally for MOVE_COORDS
        parts = " ".join(f"{c:.3f}" for c in coords)
        self._send(f"MOVE_COORDS {parts} {speed}")

    def move_angles(self, angles: list[float], *, speed: int = 35) -> None:
        logger.warning("Pi arm server has no angle moves; ignoring %s speed=%s", angles, speed)

    def xz_delta(self, dx_mm: float, dz_mm: float) -> None:
        self._send(f"XZ_DELTA {dx_mm:.2f} {dz_mm:.2f}")

    def feed_step(self) -> None:
        self._send("FEED")

    def feed_pause(self) -> None:
        self._send("FEED_PAUSE")

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def wait_until_done(self, seconds: float = 2.0) -> None:
        self.wait(seconds)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
