#!/usr/bin/env python3
"""
pi_arm_server.py  —  Runs on Raspberry Pi (MyCobot 320 Pi)
-------------------------------------------------------------------
Updated version of your Pi arm server.

Main improvement:
- Keeps your existing text command protocol.
- Adds XZ_DELTA <dx_mm> <dz_mm>, so Jetson can send one proportional
  correction for mouth-centering instead of separate LEFT/RIGHT/UP/DOWN
  fixed nudges.

Socket protocol  (received from Jetson):
  PING                  -> ACK
  GET_COORDS            -> COORDS x y z rx ry rz
  LEFT <mm>             -> nudge arm left  (robot -X)
  RIGHT <mm>            -> nudge arm right (robot +X)
  UP <mm>               -> nudge arm up    (robot +Z)
  DOWN <mm>             -> nudge arm down  (robot -Z)
  XZ_DELTA <dx> <dz>    -> nudge robot X/Z together
  VIEW_SELECTION          -> move to plate / AprilTag view
  VIEW_MOUTH              -> move to mouth / feeding view
  SECTION_PICK <n>        -> pick food from plate section 1-4
  MOVE_COORDS x y z rx ry rz [speed] -> absolute pose
  FEED                  -> execute one forward feeding step
  FEED_PAUSE            -> freeze the arm mid-approach
  FEED_RESUME           -> alias for FEED
  STOP                  -> stop all motion immediately

Coordinate convention used by this file:
  +X = robot's right
  +Y = forward toward user
  +Z = up

Safety:
- XZ_DELTA is clamped to small max step sizes.
- Feed only changes Y.
- Orientation rx/ry/rz is preserved from current coords.
"""

import socket
import time
import traceback
from pymycobot import MyCobot320

# Hardware
SERIAL_PORT = "/dev/ttyAMA0"
BAUD_RATE = 115200

# Server
HOST = "0.0.0.0"
PORT = 5001

# Motion parameters
NUDGE_SPEED = 12
FEED_SPEED = 10
NUDGE_SETTLE = 0.15
VIEW_SPEED = 5

FEED_STEP_MM = 5
FEED_STEP_DELAY = 0.4

# Preset poses (from arm_server_combined.py — tune on your hardware).
SELECTION_VIEW = [116.3, -75.8, 352.0, -178.81, -1.19, -88.61]
MOUTH_VIEW = [141.1, 180.1, 414.0, -97.87, 1.06, 5.52]

# Per-section mm offsets from SELECTION_VIEW for plate pickup (tune after AprilTag scan).
SECTION_OFFSETS_MM = {
    1: (0.0, 0.0, 0.0),
    2: (20.0, 10.0, 0.0),
    3: (20.0, 20.0, 0.0),
    4: (0.0, 20.0, 0.0),
}
PICK_DIP_Z_MM = -25.0
PICK_SCOOP_Y_MM = 12.0

# Safety workspace clamps. Adjust after testing your actual safe feeding zone.
X_MIN = -250.0
X_MAX = 250.0
Y_MIN = 100.0
Y_MAX = 350.0
Z_MIN = 100.0
Z_MAX = 450.0

# Max correction accepted from Jetson per command.
MAX_X_STEP_MM = 5.0
MAX_Z_STEP_MM = 5.0

# Safety: do not let Y go beyond this during feed.
FEED_Y_MAX = 350.0


def clamp(value, low, high):
    return max(low, min(high, value))


print("[ARM] Connecting to MyCobot 320...")
mc = MyCobot320(SERIAL_PORT, BAUD_RATE)

print("[ARM] Powering on...")
mc.power_on()
time.sleep(1)

try:
    print("[ARM] Setting fresh mode = 1")
    mc.set_fresh_mode(1)
except Exception as e:
    print(f"[ARM] set_fresh_mode warning: {e}")

try:
    print("[ARM] Setting vision mode = 1")
    mc.set_vision_mode(1)
except Exception as e:
    print(f"[ARM] set_vision_mode warning: {e}")

print("[ARM] Ready.")


def get_coords():
    """Return current [x, y, z, rx, ry, rz] or None on failure."""
    for _ in range(3):
        coords = mc.get_coords()
        if coords and len(coords) == 6:
            return list(coords)
        time.sleep(0.1)

    print("[ARM] Warning: could not read current coords.")
    return None


def safe_send_coords(coords, speed=NUDGE_SPEED, mode=1):
    """Send coords after applying workspace clamps."""
    coords = list(coords)
    coords[0] = clamp(coords[0], X_MIN, X_MAX)
    coords[1] = clamp(coords[1], Y_MIN, Y_MAX)
    coords[2] = clamp(coords[2], Z_MIN, Z_MAX)

    print(f"[ARM] send_coords speed={speed} mode={mode} -> "
          f"{[round(c, 1) for c in coords]}")
    mc.send_coords(coords, speed, mode)


def move_to_view(coords, label):
    """Angular coordinate view transition (mode 0)."""
    try:
        mc.set_fresh_mode(0)
    except Exception as e:
        print(f"[ARM] set_fresh_mode warning: {e}")
    time.sleep(0.2)
    print(f"[ARM] Moving to {label}")
    safe_send_coords(coords, VIEW_SPEED, mode=0)
    time.sleep(4.0)


def move_to_selection_view():
    move_to_view(SELECTION_VIEW, "selection / plate view")


def move_to_mouth_view():
    move_to_view(MOUTH_VIEW, "mouth / feeding view")
    try:
        mc.set_fresh_mode(1)
        mc.set_vision_mode(1)
    except Exception as e:
        print(f"[ARM] vision mode warning: {e}")
    print("[ARM] Vision tracking modes enabled.")


def section_pick(section_num):
    """Move to a plate section, dip, scoop, and lift."""
    section = int(section_num)
    if section not in SECTION_OFFSETS_MM:
        return f"ERROR: invalid section {section}"

    ox, oy, oz = SECTION_OFFSETS_MM[section]
    base = list(SELECTION_VIEW)
    base[0] += ox
    base[1] += oy
    base[2] += oz

    move_to_selection_view()

    coords = list(base)
    print(f"[ARM] SECTION_PICK {section} approach -> {coords}")
    safe_send_coords(coords, NUDGE_SPEED, mode=1)
    time.sleep(NUDGE_SETTLE)

    dip = list(coords)
    dip[2] += PICK_DIP_Z_MM
    print(f"[ARM] SECTION_PICK {section} dip z={PICK_DIP_Z_MM}")
    safe_send_coords(dip, NUDGE_SPEED, mode=1)
    time.sleep(NUDGE_SETTLE)

    scoop = list(dip)
    scoop[1] += PICK_SCOOP_Y_MM
    print(f"[ARM] SECTION_PICK {section} scoop y={PICK_SCOOP_Y_MM}")
    safe_send_coords(scoop, FEED_SPEED, mode=1)
    time.sleep(FEED_STEP_DELAY)

    lift = list(scoop)
    lift[2] = coords[2]
    print(f"[ARM] SECTION_PICK {section} lift")
    safe_send_coords(lift, NUDGE_SPEED, mode=1)
    time.sleep(NUDGE_SETTLE)

    return f"ACK SECTION_PICK {section}"


def nudge(axis, delta_mm):
    """Move relative to current position. axis: 0=X, 1=Y, 2=Z."""
    coords = get_coords()
    if coords is None:
        print("[ARM] Nudge skipped — could not read coords.")
        return

    coords[axis] += delta_mm
    print(f"[ARM] Nudge axis={axis} delta={delta_mm:+.2f}mm")
    safe_send_coords(coords, NUDGE_SPEED, mode=1)
    time.sleep(NUDGE_SETTLE)


def xz_delta(dx_mm, dz_mm):
    """Combined mouth-centering correction. Only changes X and Z."""
    dx_mm = clamp(float(dx_mm), -MAX_X_STEP_MM, MAX_X_STEP_MM)
    dz_mm = clamp(float(dz_mm), -MAX_Z_STEP_MM, MAX_Z_STEP_MM)

    coords = get_coords()
    if coords is None:
        print("[ARM] XZ_DELTA skipped — could not read coords.")
        return "ERROR: could not read coords"

    coords[0] += dx_mm
    coords[2] += dz_mm

    print(f"[ARM] XZ_DELTA dx={dx_mm:+.2f} dz={dz_mm:+.2f}")
    safe_send_coords(coords, NUDGE_SPEED, mode=1)
    time.sleep(NUDGE_SETTLE)

    return f"ACK XZ_DELTA {dx_mm:.2f} {dz_mm:.2f}"


feed_paused = False
feed_running = False


def execute_feed():
    """One small forward feeding step. Each FEED command advances +Y one step."""
    global feed_paused, feed_running

    if feed_paused:
        print("[ARM] FEED received but feed is paused — ignoring.")
        return "FEED PAUSED"

    coords = get_coords()
    if coords is None:
        return "ERROR: could not read coords"

    if coords[1] >= FEED_Y_MAX:
        print("[ARM] FEED_Y_MAX reached — stopping feed.")
        feed_running = False
        return "FEED COMPLETE"

    coords[1] += FEED_STEP_MM
    print(f"[ARM] FEED step -> Y={coords[1]:.1f}mm")
    safe_send_coords(coords, FEED_SPEED, mode=1)

    time.sleep(FEED_STEP_DELAY)
    feed_running = True
    return "FEED STEP OK"


def handle_command(raw):
    global feed_paused, feed_running

    parts = raw.strip().split()
    if not parts:
        return "EMPTY COMMAND"

    cmd = parts[0].upper()

    try:
        if cmd == "PING":
            return "ACK"

        if cmd == "GET_COORDS":
            coords = get_coords()
            if coords is None:
                return "ERROR: could not read coords"
            return "COORDS " + " ".join(f"{c:.3f}" for c in coords)

        if cmd == "LEFT":
            mm = float(parts[1]) if len(parts) > 1 else 10.0
            nudge(0, -mm)
            return "ACK"

        if cmd == "RIGHT":
            mm = float(parts[1]) if len(parts) > 1 else 10.0
            nudge(0, +mm)
            return "ACK"

        if cmd == "UP":
            mm = float(parts[1]) if len(parts) > 1 else 10.0
            nudge(2, +mm)
            return "ACK"

        if cmd == "DOWN":
            mm = float(parts[1]) if len(parts) > 1 else 10.0
            nudge(2, -mm)
            return "ACK"

        if cmd == "XZ_DELTA":
            if len(parts) < 3:
                return "ERROR: XZ_DELTA requires dx dz"
            dx = float(parts[1])
            dz = float(parts[2])
            return xz_delta(dx, dz)

        if cmd == "VIEW_SELECTION":
            move_to_selection_view()
            return "ACK VIEW_SELECTION"

        if cmd == "VIEW_MOUTH":
            move_to_mouth_view()
            return "ACK VIEW_MOUTH"

        if cmd == "SECTION_PICK":
            if len(parts) < 2:
                return "ERROR: SECTION_PICK requires section"
            return section_pick(int(parts[1]))

        if cmd == "MOVE_COORDS":
            if len(parts) < 7:
                return "ERROR: MOVE_COORDS requires x y z rx ry rz"
            coords = [float(parts[i]) for i in range(1, 7)]
            speed = int(float(parts[7])) if len(parts) > 7 else NUDGE_SPEED
            safe_send_coords(coords, speed, mode=1)
            time.sleep(NUDGE_SETTLE)
            return "ACK MOVE_COORDS"

        if cmd == "FEED":
            feed_paused = False
            return execute_feed()

        if cmd == "FEED_PAUSE":
            feed_paused = True
            feed_running = False
            print("[ARM] Feed paused.")
            mc.stop()
            return "FEED PAUSED"

        if cmd == "FEED_RESUME":
            feed_paused = False
            return execute_feed()

        if cmd == "STOP":
            feed_paused = True
            feed_running = False
            mc.stop()
            print("[ARM] STOP received — all motion halted.")
            return "STOPPED"

        print(f"[ARM] Unknown command: {raw!r}")
        return "UNKNOWN COMMAND"

    except Exception as e:
        print(f"[ARM] Command error for {raw!r}: {e}")
        traceback.print_exc()
        return f"ERROR: {e}"


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)

    print(f"[NET] Listening on {HOST}:{PORT} — waiting for Jetson...")

    while True:
        conn, addr = server.accept()
        print(f"[NET] Connected: {addr}")

        buffer = ""
        try:
            while True:
                chunk = conn.recv(1024).decode()
                if not chunk:
                    print("[NET] Connection closed by Jetson.")
                    break

                buffer += chunk

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()

                    if not line:
                        continue

                    print(f"[NET] RX: {line!r}")
                    response = handle_command(line)
                    conn.sendall((response + "\n").encode())
                    print(f"[NET] TX: {response!r}")

        except Exception as e:
            print(f"[NET] Error: {e}")
            traceback.print_exc()

        finally:
            conn.close()
            print("[NET] Connection closed. Waiting for next connection...")


if __name__ == "__main__":
    main()
