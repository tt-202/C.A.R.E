from __future__ import annotations

from states.base import FeederStateName


def _next_after_trigger(ctx) -> FeederStateName:
    """AprilTag plate scan first, unless app sent sectionNum."""
    payload = ctx.firebase_payload or {}
    if payload.get("sectionNum") is not None:
        ctx.selected_section = int(payload["sectionNum"])
        ctx.section_source = f"App → Section {ctx.selected_section}"
        if ctx.display is not None:
            ctx.display.update(section=ctx.selected_section, section_source=ctx.section_source)
        return FeederStateName.DETECT_MOUTH
    if ctx.apriltag_enabled and ctx.apriltag is not None:
        return FeederStateName.SELECT_PLATE
    return FeederStateName.DETECT_MOUTH


class IdleState:
    name = FeederStateName.IDLE

    def enter(self, ctx) -> None:
        ctx.log.info("state=IDLE section=%s", ctx.selected_section)

    def tick(self, ctx) -> FeederStateName | None:
        if ctx.buttons is not None and ctx.buttons.estop_held():
            ctx.emergency = True
            return FeederStateName.EMERGENCY

        if ctx.buttons is not None and ctx.buttons.plate_pressed():
            ctx.selected_section = (ctx.selected_section % 4) + 1
            ctx.section_source = f"GPIO → Section {ctx.selected_section}"
            ctx.log.info("GPIO plate → section %s", ctx.selected_section)
            if ctx.display is not None:
                ctx.display.update(section=ctx.selected_section, section_source=ctx.section_source)

        if ctx.pending_firebase_cmd:
            cmd, payload = ctx.pending_firebase_cmd
            ctx.pending_firebase_cmd = None
            if cmd == "stop":
                return FeederStateName.RETRACT
            if cmd == "home":
                ctx.planner.go_home()
                return None
            if cmd == "next_bite":
                ctx.firebase_payload = payload if isinstance(payload, dict) else {}
                return _next_after_trigger(ctx)

        if ctx.request_feed:
            ctx.request_feed = False
            ctx.firebase_payload = {}
            return _next_after_trigger(ctx)

        if ctx.buttons is not None and ctx.buttons.feed_pressed():
            ctx.log.info("GPIO feed button")
            ctx.firebase_payload = {}
            return _next_after_trigger(ctx)

        return None

    def exit(self, ctx) -> None:
        pass
