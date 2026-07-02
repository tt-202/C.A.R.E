# Pi arm server (MyCobot 320 Pi)

JSON TCP server for the MyCobot 320. The Jetson `robot-worker` sends one JSON object per line.

Based on `New_Settings_June26_raspberry/pi_arm_server.py`.

## Run on the Pi

```bash
cd app/pi-server
pip3 install pymycobot
cp .env.example .env   # optional: faster scoop / view / approach timings
python3 pi_arm_server.py
```

Listens on port **5002**. Set `PI_IP` and `PI_PORT=5002` in `robot-worker/.env`.

## Motion tuning (~30s feed cycle)

`pi_arm_server.py` reads optional `app/pi-server/.env` on startup:

| Variable | Default | Effect |
|----------|---------|--------|
| `SCOOP_WAIT_SCALE` | `0.55` | Shorter pause between scoop waypoints |
| `VIEW_SPEED` | `12` | Faster selection / mouth view moves |
| `VIEW_MOUTH_WAIT` | `2.5` | Seconds after mouth view command |
| `HOME_RETURN_WAIT` | `4.0` | Seconds after HOME angle command |
| `APPROACH_STEP_Y` | `3.0` | Larger forward steps during ToF approach |
| `APPROACH_SPEED` | `12` | Approach move speed |
| `TRACK_SPEED` | `65` | Mouth alignment correction speed |
| `ALIGN_PIXEL_THRESHOLD` | `25` | Pi aligns when error exceeds this (match Jetson `CENTER_TOLERANCE`) |

If scoop misses food after speeding up, raise `SCOOP_WAIT_SCALE` toward `1.0`.

## JSON commands

| cmd | Action |
|-----|--------|
| `PING` | Handshake |
| `VIEW_SELECTION` | Plate / AprilTag view |
| `VIEW_MOUTH` | Mouth tracking view |
| `SCOOP` | Fixed scoop trajectory (`section` 1–4) |
| `ALIGN` | X/Z mouth alignment (`error_x`, `error_y`) |
| `CENTERED` | Hold ready state |
| `APPROACH_MOUTH` | One Y step toward user (`tof_cm`) |
| `STOP` | Stop motion |
| `HOME` | Return to startup joint angles |

Tune `SCOOP_TRAJECTORIES`, `MOUTH_VIEW`, and `SELECTION_VIEW` in `pi_arm_server.py`.
