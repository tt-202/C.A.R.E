# 4-section plate + AprilTag + LCD (from jetson_controller design)

## Physical setup

Divide the plate into **4 sections**. Stick one **AprilTag** per section (recommended family: `tag36h11`).

Default mapping in `.env`:

```env
APRILTAG_SECTION_MAP=1:1,2:2,3:3,4:4
```

Meaning: printed tag ID `1` → section 1, tag ID `2` → section 2, etc.

If your printed tags use other IDs (e.g. 10–13):

```env
APRILTAG_SECTION_MAP=10:1,11:2,12:3,13:4
```

Generate tags: https://github.com/AprilRobotics/apriltag-generation

## How the robot picks food

1. Caregiver starts bite (app or GPIO **Feed**).
2. State **SELECT PLATE (APRILTAG)** — camera looks at the plate.
3. Among visible tags, the tag **closest to the image center** wins → that section.
4. LCD updates: section image + `AprilTag #ID → Section N`.
5. Arm moves to `SECTION_PLATE[N]` in `robot/coordinates.py` (calibrate all 4 poses).
6. Then mouth/face check → feed → home.

If the app sends `sectionNum` in `next_bite`, AprilTag is **skipped** and that section is used.

## LCD GUI (`jetson_controller/gui/lcd_display.py` style)

- Right: **Section 1–4** buttons + `sectionN.png` images (copy to `robot_feeder/gui/images/`).
- Left: connection, state, AprilTag line, errors.
- Buttons = **manual override** if tags are hard to see.

Test:

```bash
export DISPLAY=:0
python scripts/test_apriltag_live.py
python scripts/test_gui.py
```
