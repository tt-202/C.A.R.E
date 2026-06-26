"""Callback when physical e-stop latches (e.g. during mouth tracking)."""

from __future__ import annotations

from typing import Callable

_callback: Callable[[], None] | None = None


def set_estop_callback(fn: Callable[[], None] | None) -> None:
    global _callback
    _callback = fn


def notify_estop_latched() -> None:
    if _callback is not None:
        _callback()
