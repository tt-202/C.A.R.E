from __future__ import annotations

from states.base import FeederStateName


class EmergencyState:
    name = FeederStateName.EMERGENCY

    def enter(self, ctx) -> None:
        ctx.log.error("state=EMERGENCY")
        ctx.robot.stop()
        if ctx.display is not None:
            ctx.display.update(error="EMERGENCY STOP")

    def tick(self, ctx) -> FeederStateName | None:
        ctx.emergency = False
        return FeederStateName.RETRACT

    def exit(self, ctx) -> None:
        pass
