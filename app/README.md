# C.A.R.E — Complete feeding system

```
app/
├── care-app/          Web UI (Next.js) — run on Mac/Vercel
├── robot-worker1/     Jetson worker — Firestore + feeding cycle
└── pi-server/         Pi arm server — MyCobot 320 motion
```

## What runs where

| Machine | Folder | Command |
|---------|--------|---------|
| **Mac / Vercel** | `care-app/` | `npm run dev` or deploy |
| **Jetson Orin Nano** | `robot-worker1/` | `python worker.py` |
| **MyCobot 320 Pi** | `pi-server/` | `python pi_arm_server.py` |

## One bite cycle

1. **SECTION_PICK** — arm picks food from plate section
2. **VIEW_MOUTH** — arm moves to feeding pose
3. **Mouth tracking** — camera centers mouth, arm feeds forward
4. **VIEW_SELECTION** — arm returns to plate

## Quick start

### 1. Pi
```bash
cd app/pi-server && pip3 install pymycobot && python3 pi_arm_server.py
```

### 2. Jetson
```bash
cd app/robot-worker1
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python mediapipe pupil-apriltags adafruit-circuitpython-vl53l1x Jetson.GPIO
cp .env.example .env   # edit PI_IP, GOOGLE_APPLICATION_CREDENTIALS, DRY_RUN=false
export $(grep -v '^#' .env | xargs)
python worker.py
```

### 3. Care-app
```bash
cd app/care-app && npm install && npm run dev
```

Set in `care-app/.env`:
```env
ROBOT_ID=care-01
NEXT_PUBLIC_ROBOT_ID=care-01
NEXT_PUBLIC_ROBOT_ENABLED=true
```

## GPIO buttons (Jetson, BCM)

| Pin | Action |
|-----|--------|
| 33 | Feed — one full bite |
| 35 | Plate — AprilTag calibration |
| 37 | E-stop |

See `robot-worker1/README.md` and `pi-server/README.md` for details.
