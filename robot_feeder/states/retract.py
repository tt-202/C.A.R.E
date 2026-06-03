from __future__ import annotations

from states.base import FeederStateName


class RetractState:
    name = FeederStateName.RETRACT

    def enter(self, ctx) -> None:
        ctx.log.info("state=RETRACT")
        ctx.planner.go_home()

    def tick(self, ctx) -> FeederStateName | None:
        ctx.emergency = False
        return FeederStateName.IDLE

    def exit(self, ctx) -> None:
        pass
