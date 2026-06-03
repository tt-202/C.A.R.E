# robot_feeder

Unified **Jetson** process for C.A.R.E: Firestore commands from `care-app`, perception, GPIO buttons, and myCobot feeding motion.

## Plate sections + AprilTag + LCD

Matches **`jetson_controller/gui/lcd_display.py`**: 4 section buttons, section images, status/errors.

- **AprilTag** on each plate quadrant picks section 1–4 before scooping — see [gui/PLATE_SETUP.md](./gui/PLATE_SETUP.md).
- **LCD**: `GUI_ENABLED=true`, `export DISPLAY=:0`, `python main.py`.
- Test tags: `python scripts/test_apriltag_live.py`.

## Layout

```
robot_feeder/
├── main.py
├── config.py
├── gui/                 # Live operator panel (Tkinter)
├── app_bridge/          # Firestore listener
├── perception/
├── robot/
│   ├── coordinates.py   # PLATE_1/2, USER_FEED, HOME (calibrate on rig)
│   ├── motion_planner.py
│   └── mycobot_controller.py
├── sensors/
│   └── gpio_buttons.py  # Feed / plate / e-stop (BCM)
├── states/
├── data/
├── deploy/
│   ├── care-robot-feeder.service
│   └── install-systemd.sh
└── utils/
```

## Motion (from jetson_controller)

`motion_planner.execute_bite(section)`:

1. Move to plate pose (`SECTION_PLATE` — sections 1–2 → plate 1, 3–4 → plate 2)
2. Scoop (Z dip), return to plate
3. Move to `USER_FEED`
4. Return to `HOME_COORDS` `[200, 0, 200, 180, 0, 0]`

Edit `robot/coordinates.py` after calibration.

## GPIO buttons

| Button | Default BCM | Action in IDLE |
|--------|-------------|----------------|
| Feed | 17 | Start detect → feed cycle |
| Plate | 27 | Cycle section 1→4 |
| E-stop | 22 | Emergency stop (any state; held = latched) |

Set `BUTTONS_ENABLED=true` in `.env`. User `jetson` should be in the `gpio` group.

## Testing (step by step)

See **[TESTING.md](./TESTING.md)** for camera, YOLO, face, arm, GPIO, Firestore, state machine, and LCD GUI.

Quick camera + YOLO on Jetson:

```bash
python scripts/test_camera.py
python scripts/test_yolo_live.py   # needs models/food.pt
```

## Run

```bash
cd robot_feeder
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## systemd (production)

```bash
# Adjust FEEDER_DIR if repo is not at /home/jetson/C.A.R.E/robot_feeder
FEEDER_DIR=/home/jetson/C.A.R.E/robot_feeder bash deploy/install-systemd.sh
sudo systemctl enable --now care-robot-feeder
journalctl -u care-robot-feeder -f
```

## care-app link

Same Firestore contract as `app/robot-worker`. Match `ROBOT_ID` with Vercel and set `NEXT_PUBLIC_ROBOT_ENABLED=true`. Retire `robot-worker` after this service is stable on the Jetson.
