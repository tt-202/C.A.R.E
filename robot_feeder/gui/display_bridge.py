"""Map feeder context → operator panel updates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from states.base import FeederStateName

if TYPE_CHECKING:
    from gui.operator_panel import OperatorDisplay
    from states.state_machine import FeederContext

_STATE_LABELS = {
    FeederStateName.IDLE: "IDLE",
    FeederStateName.SELECT_PLATE: "SELECT PLATE (APRILTAG)",
    FeederStateName.DETECT_MOUTH: "CHECK MOUTH / VISION",
    FeederStateName.FEED: "FEEDING",
    FeederStateName.RETRACT: "RETURN HOME",
    FeederStateName.EMERGENCY: "EMERGENCY STOP",
}


def sync_display(ctx: "FeederContext", state: FeederStateName, *, error: str | None = None) -> None:
    display: OperatorDisplay | None = getattr(ctx, "display", None)
    if display is None:
        return
    payload: dict = {
        "state": _STATE_LABELS.get(state, state.name),
        "section": ctx.selected_section,
        "bites": ctx.bites.total,
        "section_source": getattr(ctx, "section_source", ""),
    }
    if error is not None:
        payload["error"] = error
    display.update(**payload)


def sync_after_detect(ctx: "FeederContext") -> None:
    display: OperatorDisplay | None = getattr(ctx, "display", None)
    if display is None:
        return
    if not ctx.food_detected:
        display.update(error="NO FOOD ON PLATE OR SPOON")
        return
    face = ctx.face_state
    if face is not None and not face.detected:
        display.update(error="NO FACE DETECTED")
        return
    if face is not None and face.detected and not face.is_open:
        display.update(error="MOUTH CLOSED — WAITING")
    else:
        display.update(error="NONE")
