from __future__ import annotations

from gui.display_bridge import sync_after_detect
from states.base import FeederStateName


class DetectMouthState:
    name = FeederStateName.DETECT_MOUTH

    def enter(self, ctx) -> None:
        ctx.log.info("state=DETECT_MOUTH")
        ok, frame = ctx.camera.read()
        if not ok:
            ctx.log.warning("No camera frame — proceeding with stubs")
            frame = None

        food = ctx.yolo.detect_food(frame) if frame is not None else True
        face = ctx.face.track(frame)
        distance = ctx.tof.read_distance_mm()

        ctx.food_detected = food
        ctx.face_state = face
        ctx.tof_mm = distance

        if ctx.emergency:
            return

        if not ctx.safety.tof_ok(distance):
            ctx.log.warning("TOF out of range: %s mm", distance)
            ctx.emergency = True

        if face.detected and not ctx.safety.mouth_alignment_ok(face.offset_x, face.offset_y):
            ctx.log.info("Face offset x=%.3f y=%.3f — will align in FEED", face.offset_x, face.offset_y)

        sync_after_detect(ctx)

    def tick(self, ctx) -> FeederStateName | None:
        if ctx.emergency:
            return FeederStateName.EMERGENCY
        if not ctx.food_detected:
            ctx.log.warning("No food detected — retract")
            return FeederStateName.RETRACT
        if ctx.face_state and ctx.face_state.detected and not ctx.face_state.is_open:
            return FeederStateName.IDLE
        return FeederStateName.FEED

    def exit(self, ctx) -> None:
        pass
