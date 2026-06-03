"""Read AprilTag on plate → set section 1–4 → update GUI."""

from __future__ import annotations

from states.base import FeederStateName


class SelectPlateState:
    name = FeederStateName.SELECT_PLATE

    def enter(self, ctx) -> None:
        ctx.log.info("state=SELECT_PLATE")
        ok, frame = ctx.camera.read()
        if not ok or frame is None:
            ctx.log.warning("No frame for AprilTag — keeping section %s", ctx.selected_section)
            if ctx.display is not None:
                ctx.display.update(
                    error="NO CAMERA — USING LAST SECTION",
                    section_source=f"Section {ctx.selected_section} (cached)",
                )
            return

        apriltag = ctx.apriltag
        if apriltag is None or apriltag._detector is None:
            ctx.log.warning("AprilTag disabled — keeping section %s", ctx.selected_section)
            return

        pick = apriltag.pick_section(frame)
        if pick is None:
            ctx.apriltag_select_failed = True
            ctx.log.warning("No AprilTag visible for sections %s", list(apriltag.tag_to_section))
            ctx.section_source = "AprilTag: not detected"
            if ctx.display is not None:
                ctx.display.update(
                    error="NO APRILTAG — POINT CAMERA AT PLATE TAG",
                    section_source=ctx.section_source,
                )
            return

        ctx.apriltag_select_failed = False
        ctx.selected_section = pick.section
        ctx.last_tag_id = pick.tag_id
        ctx.section_source = f"AprilTag #{pick.tag_id} → Section {pick.section}"
        ctx.log.info(
            "AprilTag selected section=%s tag_id=%s (seen %s tags)",
            pick.section,
            pick.tag_id,
            len(pick.all_detections),
        )
        if ctx.display is not None:
            ctx.display.update(
                section=pick.section,
                section_source=ctx.section_source,
                error="NONE",
            )

    def tick(self, ctx) -> FeederStateName | None:
        if ctx.emergency:
            return FeederStateName.EMERGENCY
        if getattr(ctx, "apriltag_select_failed", False):
            return FeederStateName.IDLE
        return FeederStateName.DETECT_MOUTH

    def exit(self, ctx) -> None:
        pass
