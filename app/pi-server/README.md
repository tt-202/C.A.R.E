# Pi arm server (MyCobot 320 Pi)

TCP server that moves the MyCobot 320. The Jetson `robot-worker1` sends text commands over the network.

## Run on the Pi

```bash
cd app/pi-server
pip3 install pymycobot
python3 pi_arm_server.py
```

Listens on port **5001**. Set `PI_IP` in `robot-worker1/.env` to this Pi's LAN address.

## Commands

| Command | Action |
|---------|--------|
| `VIEW_SELECTION` | Look-down plate pose |
| `VIEW_MOUTH` | Mouth / feeding pose |
| `SECTION_PICK <1-4>` | Pick food from plate section |
| `XZ_DELTA <dx> <dz>` | Mouth centering correction |
| `FEED` | One forward step toward user |
| `STOP` | Emergency stop |

Tune poses and section offsets at the top of `pi_arm_server.py`.
