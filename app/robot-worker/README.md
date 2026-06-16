# C.A.R.E robot worker (Jetson Orin Nano)

Listens to **Firebase Firestore** for commands from the care-app and runs the **full feeding cycle** via TCP to `../pi-server/pi_arm_server.py`.

## Files

| File | Role |
|------|------|
| `worker.py` | Firestore listener + GPIO buttons |
| `robot_motion.py` | Command dispatch |
| `feeding_cycle.py` | Pick → mouth track → feed → return |
| `pi_arm_client.py` | TCP client to Pi |
| `plate_calibration.py` | AprilTag plate scan |
| `tof_sensor.py` | ToF distance for plate Z |
| `run_apriltag_scan.py` | Plate scan CLI |

## Setup

```bash
cd app/robot-worker1
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python mediapipe pupil-apriltags adafruit-circuitpython-vl53l1x Jetson.GPIO
cp .env.example .env
export $(grep -v '^#' .env | xargs)
python worker.py
```

Set `DRY_RUN=false` when Pi server and camera are ready.

## GPIO buttons (BCM)

| Pin | Action |
|-----|--------|
| Feed (33) | One full bite cycle |
| Plate (35) | AprilTag plate calibration |
| E-stop (37) | Emergency stop + session reset |

## Firestore commands

`next_bite`, `calibrate_plate`, `home`, `pause`, `stop`

## Tuning

- `FEED_STEPS_PER_BITE`, `STABLE_SECONDS` in `.env`
- Arm poses in `../pi-server/pi_arm_server.py`
