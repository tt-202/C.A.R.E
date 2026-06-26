# Pi arm server (MyCobot 320 Pi)

JSON TCP server for the MyCobot 320. The Jetson `robot-worker` sends one JSON object per line.

Based on `New_Settings_June26_raspberry/pi_arm_server.py`.

## Run on the Pi

```bash
cd app/pi-server
pip3 install pymycobot
python3 pi_arm_server.py
```

Listens on port **5002**. Set `PI_IP` and `PI_PORT=5002` in `robot-worker/.env`.

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
