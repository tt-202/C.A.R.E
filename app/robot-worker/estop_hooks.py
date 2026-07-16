#prevents circular import between gpio and woker.py

from __future__ import annotations

from typing import Callable

_callback: Callable[[], None] | None = None

#stores function that runs when new emergency detected
def set_estop_callback(fn: Callable[[], None] | None) -> None:
    global _callback
    _callback = fn

#calls stored function when buttons latches new estop
def notify_estop_latched() -> None:
    if _callback is not None:
        _callback()