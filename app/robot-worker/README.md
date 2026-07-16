# Robot worker (Jetson)

This runs on the Jetson. It listens for app commands in Firestore, reads the physical buttons, and tells the Pi what to move.

Talks to the Pi over TCP on port **5002** (`pi_arm_server.py`).

## Buttons (BOARD pins)

| Pin | Button | What it does |
|-----|--------|--------------|
| 35 | SELECT | First press: AprilTag plate scan. After that: cycle section 1→2→3→4 |
| 37 | FEED | One full bite (need a successful scan first) |
| 33 | E-stop | Stop the arm, wait a bit, then HOME |

During a bite, SELECT and FEED are ignored. E-stop always wins.

## One bite

1. Check plate with YOLO (food there?)
2. Scoop that section on the Pi
3. Check spoon with YOLO
4. Move to mouth view, track mouth (MediaPipe + ALIGN)
5. Approach with ToF until close enough
6. Hold still for the bite
7. HOME — then SELECT works again

## Setup

```bash
cd app/robot-worker
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt -r requirements-jetson-hardware.txt
cp .env.example .env
# put firebase-service-account.json here, set PI_IP, DRY_RUN=false
python3 worker.py
```

`worker.py` loads `.env` by itself. Don’t do `export $(grep …)` — it breaks weird values.

Start the Pi first:

```bash
cd app/pi-server
python3 pi_arm_server.py
```

## YOLO

Plate and spoon use different models:

```env
YOLO_PLATE_MODEL_PATH=best.engine
YOLO_SPOON_MODEL_PATH=bestest.engine
ENABLE_YOLO_CHECKS=true
FORCE_PLATE_STATUS=auto
FORCE_SPOON_STATUS=auto
```

To fake an empty plate (test the caregiver alert):

```env
FORCE_PLATE_STATUS=empty
```

## Useful .env knobs

| Variable | Typical | Notes |
|----------|---------|--------|
| `DRY_RUN` | `false` | Must be false on real hardware |
| `BITE_HOLD_SECONDS` | `2` | How long we hold at the mouth (app can override via Firestore) |
| `STOP_DISTANCE_CM` | `50` | ToF stop distance |
| `CENTER_HOLD_SECONDS` | `1.5` | Mouth must stay centered this long before approach |
| `ALIGN_COMMAND_PERIOD` | `0.20` | How often we send ALIGN |
| `EMERGENCY_RECOVERY_SECONDS` | `10` | Hold after e-stop before HOME |

More options are in `.env.example`. Scoop paths live on the Pi in `pi_arm_server.py`.

## AprilTag

First SELECT:

1. Arm goes to plate view
2. Camera looks for tags 0–3
3. Writes `latest_plate_scan.py`
4. FEED unlocks for this run

Quick test:

```bash
python3 run_apriltag_scan.py --preview
```

## If something breaks

**Arm sits at plate after SELECT** — normal. It waits for FEED.

**Stuck after FEED / never HOMEs** — check face in camera, ToF wiring, and logs for `[APPROACH]` / `[BITE_HOLD_READY]`.

**E-stop** — arm stops, holds ~10s, then HOMEs on its own.

**MediaPipe `FieldDescriptor` error** — protobuf mismatch. In the venv:

```bash
pip uninstall -y mediapipe protobuf
pip install "protobuf>=4.25.3,<5" "mediapipe>=0.10.13"
```

**ToF I2C errors** — usually a loose cable. Try `python3 tof_stream_process.py` alone, or reboot.

## App commands (Firestore)

`next_bite`, `calibrate_plate`, `home`, `pause`, `stop`
