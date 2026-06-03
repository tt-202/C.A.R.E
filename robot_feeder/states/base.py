from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from states.state_machine import FeederContext


class FeederStateName(Enum):
    IDLE = auto()
    SELECT_PLATE = auto()
    DETECT_MOUTH = auto()
    FEED = auto()
    RETRACT = auto()
    EMERGENCY = auto()


class State(Protocol):
    name: FeederStateName

    def enter(self, ctx: "FeederContext") -> None: ...

    def tick(self, ctx: "FeederContext") -> FeederStateName | None: ...

    def exit(self, ctx: "FeederContext") -> None: ...
