# C.A.R.E robot worker (Jetson Orin Nano)

Listens to **Firebase Firestore** for commands from the care-app and runs the **full feeding cycle** via TCP to `../pi-server/pi_arm_server.py`.

Mouth tracking and e-stop behavior match `../With_Emergency_Stop/main_controller_phase4.py`.

## Files

| File | Role |
|------|------|
| `worker.py` | Firestore listener + GPIO buttons |
| `feeding_cycle.py` | Pick → mouth track (MediaPipe + ToF) → return |
| `gpio_buttons.py` | BOARD pins 33/35/37 + emergency latch |
| `tof_subprocess.py` | ToF reader (subprocess avoids GPIO/I2C conflict) |
| `pi_arm_client.py` | TCP client to Pi |
| `plate_calibration.py` | AprilTag plate scan |

## Setup

```bash
cd app/robot-worker
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python mediapipe pupil-apriltags adafruit-circuitpython-vl53l1x Jetson.GPIO
cp .env.example .env
export $(grep -v '^#' .env | xargs)
python worker.py
```

Set `DRY_RUN=false` when Pi server and camera are ready.

## GPIO buttons (BOARD numbering)

| BOARD pin | Action |
|-----------|--------|
| 35 | Plate / selection — AprilTag calibration |
| 37 | Feed — full bite cycle |
| 33 | **E-stop** — STOP arm + Firestore emergency + caregiver push |

Set `GPIO_PIN_MODE=BCM` only if your wiring uses BCM numbers instead.

## E-stop behavior

1. Sends `STOP` to Pi immediately
2. Sets `emergency_latched` — blocks feed/plate until worker restart
3. Writes Firestore `live.emergency: true`
4. POSTs to care-app `/api/robot/emergency` for caregiver push

During mouth tracking, pin 33 is polled every loop iteration (highest priority).

## Firestore commands

`next_bite`, `calibrate_plate`, `home`, `pause`, `stop`

## Tuning

- `CENTER_HOLD_SECONDS`, `STOP_DISTANCE_CM`, `USE_FAKE_TOF` in `.env`
- Arm poses in `../pi-server/pi_arm_server.py`
