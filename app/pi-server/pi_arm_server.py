#!/usr/bin/env python3

import json
import socket
import time

from pymycobot.mycobot320 import MyCobot320


SERIAL_PORT = "/dev/ttyAMA0"
BAUD_RATE = 115200

HOST = "0.0.0.0"
PORT = 5002

# Startup is a JOINT-ANGLE move, not a coordinate move.
STARTUP_ANGLES = [0, 0, 0, 0, 0, 0]
STARTUP_SPEED = 20

# View transitions use send_coords with angular coordinate transition mode.
VIEW_SPEED = 5
VIEW_MODE = 0

# Mouth tracking corrections use send_coords with linear coordinate mode.
TRACK_SPEED = 50
TRACK_MODE = 1

# Known working views.
MOUTH_VIEW = [141.1, 180.1, 414.0, -97.87, 1.06, 5.52]
SELECTION_VIEW = [279.8, -90.3, 323.0, -162.44, 3.64, -96.64]

# X/Z mouth alignment correction.
STEP = 2

LIMITS = {
    "x": (21.3, 204.1),
    "z": (334.0, 457.0),
}

# Final forward-to-mouth approach.
APPROACH_STEP_Y = 2.0
APPROACH_SPEED = 5
APPROACH_MODE = 0

# You said +1 moved accurately. Keep +1 unless it reverses after remounting.
APPROACH_Y_DIRECTION = +1

# Keep Y physically bounded.
Y_LIMITS = (180.0, 330.0)



# ---------------------------------------------------------
# Scoop trajectories for the four plate sections
# ---------------------------------------------------------
# Each item is: (coords, speed, mode, wait_seconds)
# mode 0 = angular coordinate transition mode, matching your working scoop tests.
# Edit these lists if your final physical scoop paths change.
SCOOP_TRAJECTORIES = {
    1: [
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
        ([272.5,(-122),187.4,178.15,(-41.48),(-42.16)], 10, 0, 4),
        ([259.4,(-134),172.5,(-150.81),(-9.67),(-85.15)], 10, 0, 4),
        ([269.7,(-135.6),203.8,(-130.07),(-13.99),(-89.39)], 10, 0, 4),
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
    ],
    2: [
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
        ([264.9,(-39.5),188.5,(-170.87),31.49,(-142.47)], 10, 0, 4),
        ([243.2,(-110.9),182.8,(-150.39),9.87,(-102.25)], 10, 0, 4),
        ([245.9,(-108.2),205.2,(-130.34),11.22,(-98.09)], 10, 0, 4),
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
    ],
    3: [
        ([14, -154.5, 523.3, -90.12, -2.81, -179.11], 20, 0, 4),
        ([345.1,(-78.4),173.7,(-174.76),(-44.79),(-21.09)], 10, 0, 4),
        ([344.7,(-35.3),153.2,(-139.78),(-4.81),(-80.02)], 10, 0, 4),
        ([330.2,(-55.2),195.9,(-116.92),1.38,(-84.89)], 10, 0, 4),
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
    Software stop for the myCobot.
    This is not a physical power-cut emergency stop, but it immediately asks
    the arm controller to stop motion.
    """
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
    print("Setting fresh mode 0 before startup angle move...", flush=True)

    mc.set_fresh_mode(0)
    time.sleep(0.5)

    print("Current angles before startup:", mc.get_angles(), flush=True)
    print("Current coords before startup:", mc.get_coords(), flush=True)

    print("Moving to startup all-zero joint angles...", flush=True)
    print("Sending angles:", STARTUP_ANGLES, "speed:", STARTUP_SPEED, flush=True)

    mc.send_angles(STARTUP_ANGLES, STARTUP_SPEED)

    time.sleep(6)

    print("Startup angles actual:", mc.get_angles(), flush=True)
    print("Startup coords actual:", mc.get_coords(), flush=True)


def move_to_selection_view():
    print("Moving to selection / AprilTag view using send_coords angular coordinate mode.", flush=True)

    mc.set_fresh_mode(0)
    time.sleep(0.2)

    print("Sending coords:", SELECTION_VIEW, "speed:", VIEW_SPEED, "mode:", VIEW_MODE, flush=True)

    mc.send_coords(SELECTION_VIEW, VIEW_SPEED, VIEW_MODE)

    time.sleep(4)

    print("Actual after selection view:", mc.get_coords(), flush=True)


def move_to_mouth_view():
    global current

    print("Moving to mouth / feeding view using send_coords angular coordinate mode.", flush=True)

    mc.set_fresh_mode(0)
    time.sleep(0.2)

    print("Sending coords:", MOUTH_VIEW, "speed:", VIEW_SPEED, "mode:", VIEW_MODE, flush=True)

    mc.send_coords(MOUTH_VIEW, VIEW_SPEED, VIEW_MODE)

    time.sleep(4)

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


def apply_move(cmd):
    global current

    if cmd == "MOVE_LEFT":
        current["x"] -= STEP

    elif cmd == "MOVE_RIGHT":
        current["x"] += STEP

    elif cmd == "MOVE_FORWARD":
        current["z"] += STEP

    elif cmd == "MOVE_BACKWARD":
        current["z"] -= STEP

    else:
        return

    current["x"] = clamp(current["x"], *LIMITS["x"])
    current["z"] = clamp(current["z"], *LIMITS["z"])

    send_current_coords(TRACK_SPEED, TRACK_MODE, f"Linear tracking correction {cmd}")


def process_alignment(error_x, error_y):
    if abs(error_x) > 40:
        if error_x > 0:
            apply_move("MOVE_RIGHT")
        else:
            apply_move("MOVE_LEFT")

    if abs(error_y) > 40:
        if error_y > 0:
            apply_move("MOVE_BACKWARD")
        else:
            apply_move("MOVE_FORWARD")


def approach_mouth_step(tof_cm=None):
    global current

    old_y = current["y"]

    current["y"] += APPROACH_Y_DIRECTION * APPROACH_STEP_Y
    current["y"] = clamp(current["y"], *Y_LIMITS)

    print(
        f"Y mouth approach step | ToF={tof_cm} cm | Y {old_y:.1f} -> {current['y']:.1f}",
        flush=True,
    )

    send_current_coords(APPROACH_SPEED, APPROACH_MODE, "Y mouth approach")



def execute_scoop(section):
    """
    Execute the fixed scoop trajectory for the selected plate section.

    The Jetson sends this before starting mouth detection. After this function
    finishes, the arm is back at the safe upper transition pose, ready to move
    into the mouth tracking view.
    """
    section = int(section)

    if section not in SCOOP_TRAJECTORIES:
        raise ValueError(f"Invalid scoop section {section}. Expected 1, 2, 3, or 4.")

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
        time.sleep(wait_seconds)

    print(f"[SCOOP] Completed scoop for plate section {section}", flush=True)

def send_json(conn, msg):
    conn.sendall((json.dumps(msg) + "\n").encode())


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

                    process_alignment(error_x, error_y)


                elif cmd == "CENTERED":
                    print("Mouth centered - holding ready state", flush=True)

                elif cmd == "APPROACH_MOUTH":
                    tof_cm = msg.get("tof_cm", None)

                    approach_mouth_step(tof_cm)


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
