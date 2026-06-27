# C.A.R.E robot worker (Jetson Orin Nano)

Listens to **Firebase Firestore** for commands from the care-app and controls the arm via **JSON TCP** to `../pi-server/pi_arm_server.py` (port **5002**).

**Reference:** `New_Settings_June26/main_controller_phase4.py` + `New_Settings_June26_raspberry/pi_arm_server.py` — same GPIO, ToF subprocess, AprilTag scan, and mouth-tracking flow.

## Feed cycle (one bite)

1. **SCOOP** — Pi runs fixed trajectory for selected plate section (1–4)
2. **VIEW_MOUTH** — Pi moves to mouth tracking pose
3. **Mouth tracking** — Jetson MediaPipe + ToF subprocess → Pi `ALIGN` / `CENTERED` / `APPROACH_MOUTH`
4. **BITE_HOLD** — hold at mouth when ToF ≤ `STOP_DISTANCE_CM` (default 30 cm)
5. **HOME** — Pi returns to startup joint angles

## GPIO buttons (BOARD numbering)

| BOARD pin | Action |
|-----------|--------|
| 35 | **SELECT** — first press: AprilTag scan; later: cycle section 1→2→3→4 |
| 37 | **FEED** — full bite (requires scan once per worker run) |
| 33 | **E-stop** — STOP + Firestore emergency + caregiver push |

## Setup (Jetson)

```bash
cd app/robot-worker
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python mediapipe pupil-apriltags adafruit-circuitpython-vl53l1x Jetson.GPIO
cp .env.example .env
# edit .env — place firebase-service-account.json in this folder
python3 worker.py
```

On Pi: `python3 app/pi-server/pi_arm_server.py` (port **5002**).

`worker.py` loads `.env` automatically — do not use `export $(grep ...)` (breaks values with spaces or dashes).

## ToF sensor (same as June26)

- **AprilTag scan:** `tof_sensor.py` reads plate height once in a subprocess (avoids GPIO/I2C conflict)
- **Mouth approach:** `tof_stream_process.py` runs as a background subprocess; parent reads JSON distance lines
- Set `USE_FAKE_TOF=true` + `FAKE_TOF_CM=60` only for desk testing without hardware

## Firestore commands

`next_bite`, `calibrate_plate`, `home`, `pause`, `stop`

## AprilTag plate scan

Uses `april_tag_with_value_update.py` (copied from June26).

1. Pi `VIEW_SELECTION`
2. Camera index **0** detects tags **0–3** (tag36h11)
3. ToF reads plate Z → `latest_plate_scan.py`
4. Unlocks **FEED** for this worker run

### Standalone test

```bash
python3 run_apriltag_scan.py --preview
```

## Tuning (`.env` — defaults match June26)

| Variable | Default |
|----------|---------|
| `STOP_DISTANCE_CM` | 30 |
| `BITE_HOLD_SECONDS` | 5 |
| `CENTER_HOLD_SECONDS` | 3 |
| `CENTER_TOLERANCE` | 30 px |
| `ARM_MOVE_SETTLE` | 1.0 s |

Scoop trajectories and arm poses: `app/pi-server/pi_arm_server.py`
