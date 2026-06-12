# C.A.R.E robot worker (Jetson + myCobot 320)

Runs on the **Jetson Orin Nano**. Listens to **Firebase Firestore** for commands created by the Vercel app (`POST /api/robot/command`) and executes them via **pymycobot**.

## Prerequisites

1. **Firebase Console** → enable **Firestore** (same project as C.A.R.E auth).
2. Deploy rules from `care-app/firestore.rules` (`firebase deploy --only firestore:rules` if you use Firebase CLI).
3. Create a **service account** for the Jetson (Firestore read/write on `robots/{robotId}/commands/*` only, if you can scope IAM).
4. Copy the JSON to the Jetson (never commit it).

## Jetson setup

```bash
cd robot-worker
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: GOOGLE_APPLICATION_CREDENTIALS, ROBOT_ID, MYCOBOT_PORT, DRY_RUN
python worker.py
```

With `DRY_RUN=true`, commands are logged without moving the arm. Set `DRY_RUN=false` after pymycobot is installed and the arm is connected.

## Vercel / care-app env

| Variable | Example |
|----------|---------|
| `ROBOT_ID` | `care-01` (must match Jetson) |
| `NEXT_PUBLIC_ROBOT_ENABLED` | `true` to send commands from the feeding UI |

## systemd (optional)

```ini
[Unit]
Description=C.A.R.E robot worker
After=network-online.target

[Service]
Type=simple
User=jetson
WorkingDirectory=/home/jetson/robot-worker
EnvironmentFile=/home/jetson/robot-worker/.env
ExecStart=/home/jetson/robot-worker/venv/bin/python worker.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

## Firestore stats (care-app live UI)

The caregiver app listens under `robots/{ROBOT_ID}/`:

| Document | Fields |
|----------|--------|
| `status/live` | `state`, `bite_count`, `section`, `emergency`, `jetson_online`, `last_feed_time` |
| `stats/feed_counts` | `total_bites`, `successful_feeds`, `failed_feeds` |
| `status/button_input` | `eat_pressed`, `stop_pressed`, `last_pin`, `eat_press_seq` |

Each **feed button** press runs one bite motion, increments `eat_press_seq`, and the care-app saves one bite to meal history.

## GPIO buttons

Set `BUTTONS_ENABLED=true` on the Jetson (see `.env.example`). Default BCM pins:

| Button | Pin | Action |
|--------|-----|--------|
| Feed | 17 | One bite (motion + count) |
| Plate | 27 | Cycle plate section 1→4 |
| E-stop | 22 | Reset session, mark emergency |

Requires `RPi.GPIO` (`pip install RPi.GPIO` on Jetson).

The worker updates these automatically after each command (`robot_stats.py`).

## Customize motion

Edit `robot_motion.py` — replace the `next_bite` placeholder angles with your safe feeding trajectory.
