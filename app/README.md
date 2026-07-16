# C.A.R.E app stack

Three pieces:

```
app/
├── care-app/       Web app (Mac / Vercel)
├── robot-worker/   Jetson — vision, buttons, Firestore
└── pi-server/      Pi — MyCobot motion only
```

## Who runs what

| Machine | Folder | Start with |
|---------|--------|------------|
| Mac / Vercel | `care-app/` | `npm run dev` or deploy |
| Jetson | `robot-worker/` | `python3 worker.py` |
| Pi | `pi-server/` | `python3 pi_arm_server.py` |

## Rough feed flow

1. SELECT once → AprilTag scan (unlocks FEED)
2. FEED → scoop → spoon check → mouth track → bite hold → HOME

Details: `robot-worker/README.md` and `pi-server/README.md`.

## Quick start

**Pi**
```bash
cd app/pi-server
pip3 install pymycobot
python3 pi_arm_server.py
```

**Jetson**
```bash
cd app/robot-worker
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install -r requirements.txt -r requirements-jetson-hardware.txt
cp .env.example .env   # PI_IP, Firebase JSON, DRY_RUN=false
python3 worker.py
```

**Care app**
```bash
cd app/care-app
npm install
npm run dev
```

In `care-app/.env`:
```env
ROBOT_ID=care-01
NEXT_PUBLIC_ROBOT_ID=care-01
NEXT_PUBLIC_ROBOT_ENABLED=true
```

## Buttons on the Jetson (BOARD)

| Pin | Action |
|-----|--------|
| 35 | SELECT |
| 37 | FEED |
| 33 | E-stop |
