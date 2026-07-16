#!/usr/bin/env python3

import json
import os
import socket
import time
from pathlib import Path

from pymycobot.mycobot320 import MyCobot320

# Jetson sends commands in the form of json commands to the server which direclty controls the robotic arm.

def _load_dotenv() -> None:
    # Used for the port and track speed parameters
    env_file = Path(__file__).resolve().parent / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

SERIAL_PORT = os.environ.get("SERIAL_PORT", "/dev/ttyAMA0")
BAUD_RATE = int(os.environ.get("BAUD_RATE", "115200"))

HOST = os.environ.get("PI_HOST", "0.0.0.0")
PORT = int(os.environ.get("PI_PORT", "5002"))

# Startup is a JOINT-ANGLE move
STARTUP_ANGLES = [0, 0, 0, 0, 0, 0]
STARTUP_SPEED = int(os.environ.get("STARTUP_SPEED", "20"))

# View transitions use send_coords with angular coordinate transition mode
VIEW_SPEED = int(os.environ.get("VIEW_SPEED", "12"))
VIEW_MODE = 0
VIEW_SELECTION_WAIT = float(os.environ.get("VIEW_SELECTION_WAIT", "2.5"))
VIEW_MOUTH_WAIT = float(os.environ.get("VIEW_MOUTH_WAIT", "2.5"))
HOME_RETURN_WAIT = 0.0  

# Mouth tracking corrections using send_coords with linear coordinate mode
TRACK_SPEED = int(os.environ.get("TRACK_SPEED", "65"))
TRACK_MODE = 1

# Known working views for detecting the mouth starting position and April Tag starting position
MOUTH_VIEW = [141.1, 180.1, 414.0, -97.87, 1.06, 5.52]
SELECTION_VIEW = [279.8, -90.3, 323.0, -162.44, 3.64, -96.64]

# X/Z mouth alignment correction and speed of robot movement during mouth tarcking
TRACK_STEP = float(os.environ.get("TRACK_STEP", "2.5"))
ALIGN_PIXEL_THRESHOLD = int(os.environ.get("ALIGN_PIXEL_THRESHOLD", "25"))
ALIGN_DOMINANT_AXIS_ONLY = os.environ.get("ALIGN_DOMINANT_AXIS_ONLY", "true").lower() in ("1", "true", "yes", "on")
TRACK_LIMIT_MARGIN = float(os.environ.get("TRACK_LIMIT_MARGIN", "0.01"))
# A section bounds the ranges the robot nudges to for mouth detection for x,y in CLAMP
LIMITS = {
    "x": (21.3, 204.1),
    "z": (334.0, 435.0),
}

# Final forward-to-mouth approach
APPROACH_STEP_Y = float(os.environ.get("APPROACH_STEP_Y", "3.0"))
APPROACH_SPEED = int(os.environ.get("APPROACH_SPEED", "12"))
APPROACH_MODE = 0
SCOOP_WAIT_SCALE = float(os.environ.get("SCOOP_WAIT_SCALE", "0.55"))

APPROACH_Y_DIRECTION = +1

# Keep Y physically bounded
Y_LIMITS = (180.0, 330.0)



# ---------------------------------------------------------
# Scoop trajectories for the four plate sections
# ---------------------------------------------------------
# Each item is: (coords, speed, mode, wait_seconds)
# mode 0 = angular coordinate transition mode, matching your working scoop tests.
SCOOP_TRAJECTORIES = {
    1: [
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
        ([272.5,(-102),187.4,178.15,(-41.48),(-42.16)], 10, 0, 4),
        ([259.4,(-114),172.5,(-150.81),(-9.67),(-85.15)], 10, 0, 4),
        ([269.7,(-115.6),203.8,(-130.07),(-13.99),(-89.39)], 10, 0, 4),
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
    ],
    2: [
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
        ([264.9,(-19.5),188.5,(-170.87),31.49,(-142.47)], 10, 0, 4),
        ([243.2,(-95.9),182.8,(-150.39),9.87,(-102.25)], 10, 0, 4),
        ([245.9,(-93.2),205.2,(-130.34),11.22,(-98.09)], 10, 0, 4),
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
    ],
    3: [
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
        ([325.1,(-68.4),173.7,(-174.76),(-44.79),(-21.09)], 10, 0, 4),
        ([334.7,(-25.3),153.2,(-139.78),(-4.81),(-80.02)], 10, 0, 4),
        ([320.2,(-45.2),195.9,(-116.92),1.38,(-84.89)], 10, 0, 4),
        ([4.4, -154.3, 523.5, -89.86, 4.21, -178.76], 20, 0, 4),
    ],
    4: [
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
        ([350,(-103.8),185.9,(-169.94),(-39.48),(-58.32)], 10, 0, 4),
        ([350,(-110),152,(-141.09),(-8.57),(-98.15)], 10, 0, 4),
        ([337.5,(-109.4),212.4,(-108.4),(-3.56),(-101.71)], 10, 0, 4),
        ([4.4, -154.3, 523.5, -89.86, 4.21, -178.76], 20, 0, 4),
    ],
}

mc = MyCobot320(SERIAL_PORT, BAUD_RATE)
mc.power_on()


arm_phase = "STARTUP"


def set_arm_phase(new_phase, reason=""):
    global arm_phase
    arm_phase = str(new_phase)
    suffix = f" | {reason}" if reason else ""
    print(f"[ARM_PHASE] {arm_phase}{suffix}", flush=True)


current = {
    "x": MOUTH_VIEW[0],
    "y": MOUTH_VIEW[1],
    "z": MOUTH_VIEW[2],
    "rx": MOUTH_VIEW[3],
    "ry": MOUTH_VIEW[4],
    "rz": MOUTH_VIEW[5],
}


def clamp(val, min_v, max_v):
    return max(min_v, min(val, max_v))


def safe_stop(reason="STOP"):
    """
    Software stop for the myCobot """
    print(f"[STOP] Stopping arm. Reason: {reason}", flush=True)

    try:
        mc.stop()
        time.sleep(0.1)

        # Return to non-continuous/fresh mode after stopping.
        # This helps after mouth tracking enabled fresh/vision modes.
        mc.set_fresh_mode(0)
        time.sleep(0.1)

    except Exception as e:
        print("[STOP ERROR]", e, flush=True)


def move_to_startup_position():
    set_arm_phase("HOME_RETURN")
    print("Setting fresh mode 0 before startup angle move...", flush=True)

    mc.set_fresh_mode(0)
    time.sleep(0.5)

    print("Current angles before startup:", mc.get_angles(), flush=True)
    print("Current coords before startup:", mc.get_coords(), flush=True)

    print("Moving to startup all-zero joint angles...", flush=True)
    print("Sending angles:", STARTUP_ANGLES, "speed:", STARTUP_SPEED, flush=True)

    mc.send_angles(STARTUP_ANGLES, STARTUP_SPEED)

    if HOME_RETURN_WAIT > 0:
        time.sleep(HOME_RETURN_WAIT)

    print("Startup angles actual:", mc.get_angles(), flush=True)
    print("Startup coords actual:", mc.get_coords(), flush=True)
    set_arm_phase("HOME")


def move_to_selection_view():
    set_arm_phase("VIEW_SELECTION")
    print("Moving to selection / AprilTag view using send_coords angular coordinate mode.", flush=True)

    mc.set_fresh_mode(0)
    time.sleep(0.2)

    print("Sending coords:", SELECTION_VIEW, "speed:", VIEW_SPEED, "mode:", VIEW_MODE, flush=True)

    mc.send_coords(SELECTION_VIEW, VIEW_SPEED, VIEW_MODE)

    time.sleep(VIEW_SELECTION_WAIT)

    print("Actual after selection view:", mc.get_coords(), flush=True)


def move_to_mouth_view():
    global current
    set_arm_phase("VIEW_MOUTH")

    print("Moving to mouth / feeding view using send_coords angular coordinate mode.", flush=True)

    mc.set_fresh_mode(0)
    time.sleep(0.2)

    print("Sending coords:", MOUTH_VIEW, "speed:", VIEW_SPEED, "mode:", VIEW_MODE, flush=True)

    mc.send_coords(MOUTH_VIEW, VIEW_SPEED, VIEW_MODE)

    time.sleep(VIEW_MOUTH_WAIT)

    actual = mc.get_coords()

    print("Actual after mouth view:", actual, flush=True)

    current = {
        "x": MOUTH_VIEW[0],
        "y": MOUTH_VIEW[1],
        "z": MOUTH_VIEW[2],
        "rx": MOUTH_VIEW[3],
        "ry": MOUTH_VIEW[4],
        "rz": MOUTH_VIEW[5],
    }

    mc.set_fresh_mode(1)
    mc.set_vision_mode(1)

    set_arm_phase("MOUTH_TRACKING")
    print("Vision tracking modes enabled for linear mouth alignment.", flush=True)


def send_current_coords(speed, mode, label):
    next_coords = [
        current["x"],
        current["y"],
        current["z"],
        current["rx"],
        current["ry"],
        current["rz"],
    ]

    print(f"{label}: {next_coords} speed={speed} mode={mode}", flush=True)

    mc.send_coords(next_coords, speed, mode)


def _limit_hint_for_cmd(cmd):
    """Return a user-facing hint/message for the LCD when the arm reaches a tracking limit!"""
    hints = {
        "MOVE_LEFT": "MOVE_USER_LEFT",
        "MOVE_RIGHT": "MOVE_USER_RIGHT",
        "MOVE_FORWARD": "MOVE_USER_DOWN_OR_BACK",
        "MOVE_BACKWARD": "MOVE_USER_UP_OR_FORWARD",
    }
    return hints.get(cmd, "ADJUST_POSITION")

# Apply_move() receives commands MOVE_LEFT, RIGHT, FORWARD, BACKWARD to adjust the coordinates
def apply_move(cmd):
    global current

    before_x = current["x"]
    before_z = current["z"]
    axis = None

    if cmd == "MOVE_LEFT":
        axis = "x"
        current["x"] -= TRACK_STEP

    elif cmd == "MOVE_RIGHT":
        axis = "x"
        current["x"] += TRACK_STEP

    elif cmd == "MOVE_FORWARD":
        axis = "z"
        current["z"] += TRACK_STEP

    elif cmd == "MOVE_BACKWARD":
        axis = "z"
        current["z"] -= TRACK_STEP

    else:
        return None

    # keeps between safe limits
    current["x"] = clamp(current["x"], *LIMITS["x"])
    current["z"] = clamp(current["z"], *LIMITS["z"])

    blocked_by_limit = (
        abs(current["x"] - before_x) <= TRACK_LIMIT_MARGIN
        and abs(current["z"] - before_z) <= TRACK_LIMIT_MARGIN
    )

    if blocked_by_limit:
        hit = {
            "cmd": cmd,
            "axis": axis,
            "hint": _limit_hint_for_cmd(cmd),
            "x": round(current["x"], 2),
            "z": round(current["z"], 2),
        }
        print(f"[TRACK_LIMIT] {hit}", flush=True)
        return hit

    send_current_coords(TRACK_SPEED, TRACK_MODE, f"Linear tracking correction {cmd}")
    return None

# PROCESS_ALIGNMENT, uses thresholds for the x and y variation from center of USB screen and moves the robotic arm left or right until centered
def process_alignment(error_x, error_y):
    """Apply one bounded alignment correction"""
    set_arm_phase("MOUTH_ALIGN")
    limit_hits = []

    move_cmds = []
    if abs(error_x) > ALIGN_PIXEL_THRESHOLD:
        move_cmds.append((abs(error_x), "MOVE_RIGHT" if error_x > 0 else "MOVE_LEFT"))
    if abs(error_y) > ALIGN_PIXEL_THRESHOLD:
        move_cmds.append((abs(error_y), "MOVE_BACKWARD" if error_y > 0 else "MOVE_FORWARD"))

    if ALIGN_DOMINANT_AXIS_ONLY and move_cmds:
        move_cmds = [max(move_cmds, key=lambda item: item[0])]

    for _, move_cmd in move_cmds:
        hit = apply_move(move_cmd)
        if hit is not None:
            limit_hits.append(hit)

    return limit_hits

# APPROACH MOUTH moves the y axis to the mouth till TOF sensor
def approach_mouth_step(tof_cm=None):
    global current
    set_arm_phase("APPROACH_MOUTH", f"tof_cm={tof_cm}")

    old_y = current["y"]

    current["y"] += APPROACH_Y_DIRECTION * APPROACH_STEP_Y
    current["y"] = clamp(current["y"], *Y_LIMITS)

    print(
        f"Y mouth approach step | ToF={tof_cm} cm | Y {old_y:.1f} -> {current['y']:.1f}",
        flush=True,
    )

    send_current_coords(APPROACH_SPEED, APPROACH_MODE, "Y mouth approach")


# Executes list of predefined coordinates
def execute_scoop(section):
    """
    Execute the fixed scoop trajectory for the selected plate section"""
    section = int(section)

    if section not in SCOOP_TRAJECTORIES:
        raise ValueError(f"Invalid scoop section {section}. Expected 1, 2, 3, or 4.")

    set_arm_phase("SCOOP", f"section={section}")
    print(f"[SCOOP] Starting scoop for plate section {section}", flush=True)

    # Use the same mode setup as your standalone tested scoop scripts.
    mc.set_fresh_mode(0)
    time.sleep(0.2)

    for step_index, (coords, speed, mode, wait_seconds) in enumerate(SCOOP_TRAJECTORIES[section], start=1):
        print(
            f"[SCOOP] Section {section} step {step_index}/{len(SCOOP_TRAJECTORIES[section])}: "
            f"coords={coords} speed={speed} mode={mode}",
            flush=True,
        )
        mc.send_coords(coords, speed, mode)
        time.sleep(max(0.5, float(wait_seconds) * SCOOP_WAIT_SCALE))

    print(f"[SCOOP] Completed scoop for plate section {section}", flush=True)
    set_arm_phase("SCOOP_DONE", f"section={section}")

# Stops the robot and halts motion
def bite_hold_ready(tof_cm=None):
    """Stop active tracking/approach motion and hold position for the bite window."""
    set_arm_phase("BITE_HOLD_READY", f"tof_cm={tof_cm}")
    safe_stop("BITE_HOLD_READY")


def send_json(conn, msg):
    conn.sendall((json.dumps(msg) + "\n").encode())

# View selection, scoop to execute_scoop, to the pi, and the pi sends back a status ok and reply scoop done
def handle_client(conn, addr):
    print(f"Connected: {addr}", flush=True)

    buffer = ""

    while True:
        data = conn.recv(1024)

        if not data:
            print("Client disconnected.", flush=True)
            break

        buffer += data.decode()

        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()

            if not line:
                continue

            try:
                msg = json.loads(line)
                cmd = msg.get("cmd")

                print(f"Received command: {cmd}", flush=True)

                if cmd == "PING":
                    send_json(conn, {
                        "status": "ok",
                        "reply": "PONG",
                    })

                elif cmd == "VIEW_SELECTION":
                    move_to_selection_view()
                    send_json(conn, {
                        "status": "ok",
                        "reply": "VIEW_SELECTION_DONE",
                    })

                elif cmd == "VIEW_MOUTH":
                    move_to_mouth_view()
                    send_json(conn, {
                        "status": "ok",
                        "reply": "VIEW_MOUTH_DONE",
                    })

                elif cmd == "SCOOP":
                    section = int(msg.get("section", 1))
                    execute_scoop(section)
                    send_json(conn, {
                        "status": "ok",
                        "reply": "SCOOP_DONE",
                        "section": section,
                    })

                elif cmd == "ALIGN":
                    error_x = msg.get("error_x", 0)
                    error_y = msg.get("error_y", 0)

                    limit_hits = process_alignment(error_x, error_y)
                    send_json(conn, {
                        "status": "ok",
                        "reply": "ALIGN_DONE",
                        "limit_hits": limit_hits,
                        "current": {
                            "x": round(current["x"], 2),
                            "y": round(current["y"], 2),
                            "z": round(current["z"], 2),
                        },
                    })

                elif cmd == "CENTERED":
                    print("Mouth centered - holding ready state", flush=True)

                elif cmd == "APPROACH_MOUTH":
                    tof_cm = msg.get("tof_cm", None)

                    approach_mouth_step(tof_cm)

                elif cmd == "BITE_HOLD_READY":
                    tof_cm = msg.get("tof_cm", None)
                    bite_hold_ready(tof_cm)
                    send_json(conn, {
                        "status": "ok",
                        "reply": "BITE_HOLD_READY",
                        "tof_cm": tof_cm,
                    })

                elif cmd == "STOP":
                    reason = msg.get("reason", "STOP")
                    safe_stop(reason)

                    send_json(conn, {
                        "status": "ok",
                        "reply": "STOPPED",
                        "reason": reason,
                    })

                elif cmd == "HOME":
                    reason = msg.get("reason", "HOME")
                    print(f"HOME requested. Reason: {reason}", flush=True)

                    if "EMERGENCY" not in str(reason).upper():
                        safe_stop(reason)

                    move_to_startup_position()

                    send_json(conn, {
                        "status": "ok",
                        "reply": "HOME_DONE",
                        "reason": reason,
                    })

                else:
                    send_json(conn, {
                        "status": "error",
                        "reply": f"Unknown command: {cmd}",
                    })

            except Exception as e:
                print("Parse/command error:", e, flush=True)

                try:
                    send_json(conn, {
                        "status": "error",
                        "reply": str(e),
                    })
                except Exception:
                    pass


def main():
    move_to_startup_position()
    # Pi acts as TCP server where server.listen(1) command is inputted to wait for Jetson to connect
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    server.bind((HOST, PORT))
    server.listen(1)

    print(f"Pi server listening on {HOST}:{PORT}", flush=True)

    try:
        while True:
            conn, addr = server.accept()

            try:
                handle_client(conn, addr)
            finally:
                conn.close()

    except KeyboardInterrupt:
        print("\nStopping Pi server.", flush=True)

    finally:
        try:
            safe_stop("PI_SERVER_SHUTDOWN")
        except Exception:
            pass

        server.close()


if __name__ == "__main__":
    main()