# C.A.R.E robot worker (Jetson Orin Nano)

Listens to **Firebase Firestore** for commands from the care-app and controls the arm via **JSON TCP** to `../pi-server/pi_arm_server.py` (port **5002**).

Movement logic matches `New_Settings_June26/main_controller_phase4.py` + `New_Settings_June26_raspberry/pi_arm_server.py`.

## Feed cycle (one bite)

1. **SCOOP** — Pi runs fixed trajectory for selected plate section (1–4)
2. **VIEW_MOUTH** — Pi moves to mouth tracking pose
3. **Mouth tracking** — Jetson MediaPipe + ToF → Pi `ALIGN` / `CENTERED` / `APPROACH_MOUTH`
4. **BITE_HOLD** — hold at mouth (`BITE_HOLD_SECONDS`)
5. **HOME** — Pi returns to startup joint angles

## GPIO buttons (BOARD numbering)

| BOARD pin | Action |
|-----------|--------|
| 35 | **SELECT** — first press: AprilTag scan; later: cycle section 1→2→3→4 |
| 37 | **FEED** — full bite (requires scan once per worker run) |
| 33 | **E-stop** — STOP + Firestore emergency + caregiver push |

## Setup

```bash
cd app/robot-worker
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python mediapipe pupil-apriltags adafruit-circuitpython-vl53l1x Jetson.GPIO
cp .env.example .env
export $(grep -v '^#' .env | xargs)
python worker.py
```

On Pi, run `app/pi-server/pi_arm_server.py` (listens on **5002**).

Set `DRY_RUN=false` on Jetson when Pi + camera are ready.

## Firestore commands

`next_bite`, `calibrate_plate`, `home`, `pause`, `stop`

## Tuning

- `STOP_DISTANCE_CM=30`, `BITE_HOLD_SECONDS=5`, `CENTER_HOLD_SECONDS=3` in `.env`
- Scoop trajectories and poses in `app/pi-server/pi_arm_server.py`
