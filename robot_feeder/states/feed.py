from __future__ import annotations

from states.base import FeederStateName


class FeedState:
    name = FeederStateName.FEED

    def enter(self, ctx) -> None:
        ctx.log.info("state=FEED")
        payload = ctx.firebase_payload or {}
        section = int(payload.get("sectionNum", ctx.selected_section))
        ctx.planner.execute_bite(section)
        total = ctx.bites.increment(section)
        ctx.meal_log.add_bite(total)
        ctx.firebase_payload = None
        if ctx.display is not None:
            ctx.display.update(bites=total, section=section, error="NONE")

    def tick(self, ctx) -> FeederStateName | None:
        return FeederStateName.RETRACT

    def exit(self, ctx) -> None:
        pass
