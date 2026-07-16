# Pi arm server

Runs on the MyCobot’s Raspberry Pi. Jetson sends one JSON command per line on port **5002**.

## Run

```bash
cd app/pi-server
pip3 install pymycobot
cp .env.example .env   # optional timing tweaks
python3 pi_arm_server.py
```

On the Jetson, set `PI_IP` and `PI_PORT=5002` in `robot-worker/.env`.

## Commands we care about

| cmd | What it does |
|-----|----------------|
| `PING` | Hello |
| `VIEW_SELECTION` | Look at the plate |
| `VIEW_MOUTH` | Feeding pose |
| `SCOOP` | Scoop section 1–4 |
| `ALIGN` | Nudge toward the mouth |
| `APPROACH_MOUTH` | Step forward (ToF) |
| `BITE_HOLD_READY` | Freeze for the bite |
| `STOP` | Stop now |
| `HOME` | Back to startup angles |

Scoop paths and poses are hardcoded in `pi_arm_server.py` — edit there if the physical setup changes.

## Speeding things up

Copy `.env.example` → `.env`. Useful knobs:

- `SCOOP_WAIT_SCALE` — lower = faster scoop (try `0.55`; bump toward `1.0` if it misses food)
- `VIEW_MOUTH_WAIT` / `HOME_RETURN_WAIT` — how long we wait after those moves
- `APPROACH_STEP_Y` / `APPROACH_SPEED` — how aggressive the mouth approach is
- `ALIGN_DOMINANT_AXIS_ONLY` — one axis per ALIGN (less jitter)

Restart the server after changing `.env`.
