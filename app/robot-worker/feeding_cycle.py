"""

One bite:
  1. SCOOP          — fixed trajectory for selected plate section (Pi)
  2. VIEW_MOUTH     — move to feeding pose (Pi)
  3. Mouth tracking — ALIGN / CENTERED / APPROACH_MOUTH + ToF (Jetson + Pi)
  4. BITE_HOLD      — hold still at mouth
  5. HOME           — return to startup joint angles (Pi)

Plate calibration: VIEW_SELECTION + AprilTag scan (SELECT button / calibrate_plate).
"""

from __future__ import annotations

import importlib.util
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")

from pi_arm_client import PiArmClient, wait_after_move
from robot_session import (
    end_feed_cycle, #unlocks control after HOME
    get_selected_section, #gives current section if none is passed
    is_feeding_active, #if feeding active, normal home
    mark_apriltag_scan_done, #allows feed to happen after feed butotn, instead of april tag read
    mark_emergency_state, #record to feed interruption after emergency
    set_robot_view, #recrods what view the robotic arm is in
    set_system_state, 
    start_feed_cycle, #locks more feed and select processes to run, cause its scooping
)
from tof_subprocess import read_tof_cm_safe, start_tof_reader, stop_tof_reader, use_fake_tof
from lcd_gui import GUI_MESSAGES, update_gui_state
from robot_feeding_config import read_bite_hold_seconds #reads bite hold from env or the app (firestore)
from yolo_gates import (
    ensure_plate_has_food_before_feed, #runs before feed starts, 
    run_plate_yolo_check, #updates plate food cache while camera is already looking at plate
    run_spoon_yolo_check_after_scoop, #is there food on the spoon
)

if TYPE_CHECKING:
    from firebase_admin import firestore
    from gpio_buttons import ButtonManager

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent

#camera configuration
CAMERA_ID = os.environ.get("CAMERA_ID", "/dev/video0")
CAMERA_WIDTH = int(os.environ.get("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "480"))
#how tolerant the circle radius of mouth centering
CENTER_TOLERANCE = int(
    os.environ.get("CENTER_TOLERANCE", os.environ.get("DEAD_ZONE_PX", "30"))
)
# Settings for feeding
CENTER_HOLD_SECONDS = float(os.environ.get("CENTER_HOLD_SECONDS", "1.5"))
STOP_DISTANCE_CM = float(os.environ.get("STOP_DISTANCE_CM", "50.0")) #how far before the tof stops the arm from moving
STOP_DISTANCE_STABLE_SECONDS = float(os.environ.get("STOP_DISTANCE_STABLE_SECONDS", "1.0")) #how long it has to be stable before it goes back to default
BITE_HOLD_SECONDS = float(os.environ.get("BITE_HOLD_SECONDS", "2.0"))
APPROACH_COMMAND_PERIOD = float(os.environ.get("APPROACH_COMMAND_PERIOD", "0.12")) #limits frequency of the jetson sends approach mouth command
ALIGN_COMMAND_PERIOD = float(os.environ.get("ALIGN_COMMAND_PERIOD", "0.20")) #limits frequency jetson can send align command
TRACK_LIMIT_GUI_COOLDOWN = float(os.environ.get("TRACK_LIMIT_GUI_COOLDOWN", "1.0")) #limit the updating of gui screen
MAX_APPROACH_SECONDS = float(os.environ.get("MAX_APPROACH_SECONDS", "8.0")) #how long the arm can approach for, so its not infinite
LOOP_DELAY = float(os.environ.get("LOOP_DELAY", "0.02"))
VIEW_SETTLE_SECONDS = float(os.environ.get("ARM_MOVE_SETTLE", "0.5"))
MOUTH_TRACK_WIDTH = int(os.environ.get("MOUTH_TRACK_WIDTH", "480"))
MOUTH_TRACK_HEIGHT = int(os.environ.get("MOUTH_TRACK_HEIGHT", "360"))

# MEdia Pipe Configuration, confidences for mouth tracking
MOUTH_REFINE_LANDMARKS = os.environ.get("MOUTH_REFINE_LANDMARKS", "false").lower() in (
    "1",
    "true",
    "yes",
)
#how certain it needs to be, before it identifes mouth 
MOUTH_MIN_DETECTION_CONFIDENCE = float(os.environ.get("MOUTH_MIN_DETECTION_CONFIDENCE", "0.55"))
MOUTH_MIN_TRACKING_CONFIDENCE = float(os.environ.get("MOUTH_MIN_TRACKING_CONFIDENCE", "0.55"))
SHOW_APRILTAG_PREVIEW = os.environ.get("SHOW_APRILTAG_PREVIEW", "true").lower() in (
    "1",
    "true",
    "yes",
)
# Whehter preview gui shows for april tag
SHOW_MOUTH_PREVIEW = os.environ.get("SHOW_MOUTH_PREVIEW", "false").lower() in (
    "1",
    "true",
    "yes",
)
MOUTH_SESSION_TIMEOUT = float(os.environ.get("MOUTH_SESSION_TIMEOUT", "0")) #right now, there is no strong timeout 

#decides whether the robot will move or not, was for earlier when we were testing just outputs
def _dry_run() -> bool: 
    return os.environ.get("DRY_RUN", "true").lower() in ("1", "true", "yes")

# gets height of image mediapipe is taking, then gets center of x and y
def get_mouth_center(landmarks, w: int, h: int) -> tuple[int, int]:
    left = landmarks[61]
    right = landmarks[291]
    x = int(((left.x + right.x) / 2) * w)
    y = int(((left.y + right.y) / 2) * h)
    return x, y

#hints at the user where to move when tracking, so it doesnt get stuck
def _track_limit_message(limit_hits: list[dict] | None) -> str | None:
    if not limit_hits:
        return None

    hint = str(limit_hits[0].get("hint", "ADJUST_POSITION"))
    message_map = {
        "MOVE_USER_LEFT": GUI_MESSAGES.get("track_limit_move_left", "Please move slightly LEFT."),
        "MOVE_USER_RIGHT": GUI_MESSAGES.get("track_limit_move_right", "Please move slightly RIGHT."),
        "MOVE_USER_UP_OR_FORWARD": GUI_MESSAGES.get(
            "track_limit_adjust_up_forward", "Please adjust slightly up or forward."
        ),
        "MOVE_USER_DOWN_OR_BACK": GUI_MESSAGES.get(
            "track_limit_adjust_down_back", "Please adjust slightly down or back."
        ),
        "ADJUST_POSITION": GUI_MESSAGES.get(
            "track_limit_adjust_position", "Please adjust your head position."
        ),
    }
    return message_map.get(hint, message_map["ADJUST_POSITION"])

#loads the april tag results
def _load_plate_scan_module():
    scan_file = ROOT_DIR / "latest_plate_scan.py"
    if not scan_file.exists():
        return None
    spec = importlib.util.spec_from_file_location("latest_plate_scan", scan_file)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

#homing arm , differentiates between recovery or feeding homing
def _home_arm(arm: PiArmClient, reason: str) -> None:
    set_system_state(
        "FEEDING_RETURN_HOME" if is_feeding_active() else "RECOVERY_HOME",
        reason,
    )
    arm.home(reason)
    set_robot_view("home")

#this checks emergency in the long motions of feeding, it can only act after a stop point
def _estop_during_motion(buttons: ButtonManager | None, arm: PiArmClient, reason: str) -> bool:
    if buttons is None:
        return False
    if buttons.estop_raw_pressed():
        buttons.latch_emergency(reason)
    if buttons.is_emergency_latched():
        logger.warning("[ESTOP] %s — sending STOP", reason)
        try:
            #helper that will send the stop for estop
            arm.stop(reason)
        except Exception:
            logger.exception("Failed to send STOP during estop")
        return True
    return False

# runs initial april tag scan
def run_apriltag_selection_phase(arm: PiArmClient, *, preview: bool = False) -> bool:

    #only update information
    if _dry_run():
        logger.info("DRY_RUN apriltag selection phase")
        time.sleep(1.0)
        mark_apriltag_scan_done()
        return True

    #move arm to selection_view,  
    arm.view_selection()
    set_robot_view("selection")
    time.sleep(VIEW_SETTLE_SECONDS)

    
    update_gui_state(
        "selection",
        GUI_MESSAGES["apriltag_scan_start"],
        connected=True,
        error="NONE",
        force=True,
    )

    script = ROOT_DIR / "run_apriltag_scan.py"
    if not script.exists():
        raise RuntimeError(f"Missing {script}")

    cmd = [sys.executable, str(script)]
    if preview or SHOW_APRILTAG_PREVIEW:
        cmd.append("--preview")

    logger.info("Starting AprilTag scan: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT_DIR), check=False)
    if result.returncode != 0:
        logger.error("AprilTag scan failed (exit %s)", result.returncode)
        update_gui_state(
            "error",
            GUI_MESSAGES["apriltag_scan_failed"],
            connected=True,
            error=f"AprilTag scan failed: exit {result.returncode}",
            force=True,
        )
        return False

    # updates state in robot_session
    mark_apriltag_scan_done()

    update_gui_state(
        "idle",
        GUI_MESSAGES["apriltag_scan_success"],
        connected=True,
        error="NONE",
        force=True,
    )
    logger.info("AprilTag scan completed for this run")
    return True

# adds plate yolo verification and makes sure pi is connected, validates if the april tag file was created
def calibrate_plate(
    *,
    preview: bool = False,
    db: firestore.Client | None = None,
    robot_id: str | None = None,
) -> dict:
    if _dry_run():
        logger.info("DRY_RUN calibrate_plate")
        time.sleep(1.0)
        mark_apriltag_scan_done()
        return {"plate_center": (320, 240), "plate_z_cm": 25.0}

    with PiArmClient() as arm:
        arm.ping()
        ok = run_apriltag_selection_phase(arm, preview=preview)
        if ok:
            run_plate_yolo_check(arm, db, robot_id, already_in_selection_view=True)
    if not ok:
        raise RuntimeError("Plate calibration / AprilTag scan failed")

    plate = _load_plate_scan_module()
    if plate is None and not _dry_run():
        raise RuntimeError("Scan finished but latest_plate_scan.py is missing")
    return {
        "plate_center": getattr(plate, "PLATE_CENTER", (320, 240)) if plate else (320, 240),
        "plate_z_cm": getattr(plate, "PLATE_Z_CM", 25.0) if plate else 25.0,
    }

#entire mouth_delivery session after successful scoop, all the way to home
def run_mouth_feed_session(
    arm: PiArmClient,
    buttons: ButtonManager | None = None,
    *,
    bite_hold_seconds: float | None = None,
) -> bool:

    #resolve bite hold duration
    hold_seconds = (
        float(bite_hold_seconds)
        if bite_hold_seconds is not None
        else BITE_HOLD_SECONDS
    )
    # Dry run behavior
    if _dry_run():
        logger.info(
            "DRY_RUN mouth_feed_session (hold=%.1fs, stop=%.1fcm, bite_hold=%.1fs)",
            CENTER_HOLD_SECONDS,
            STOP_DISTANCE_CM,
            hold_seconds,
        )
        time.sleep(2.0)
        return True

    import cv2
    import mediapipe as mp

    # clear previous emergency latch, checks again in function if emergency latch is pressed again
    if buttons is not None:
        buttons.clear_emergency_latch()
        #checks physical ESTOP
        if buttons.estop_raw_pressed():
            buttons.latch_emergency("EMERGENCY_BEFORE_MOUTH_TRACKING")
            arm.stop("EMERGENCY_BEFORE_MOUTH_TRACKING")
            return False

    arm.view_mouth()
    set_robot_view("mouth")
    time.sleep(VIEW_SETTLE_SECONDS)

    #tells user is going to mouth tracking
    update_gui_state(
        "mouth_tracking_starting",
        "Moving to mouth tracking view",
        connected=True,
        error="NONE",
        force=True,
    )

    #code waits for feed release, before another feed
    if buttons is not None:
        buttons.wait_for_feed_release()

    # initialize all the mediapipe face mesh
    try:
        #initalize media pipe
        face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=MOUTH_REFINE_LANDMARKS,
            min_detection_confidence=MOUTH_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=MOUTH_MIN_TRACKING_CONFIDENCE,
        )
    except AttributeError as exc:
        if "FieldDescriptor" in str(exc) or "label" in str(exc):
            raise RuntimeError(
                "MediaPipe failed to start (protobuf version mismatch). "
                "On Jetson run: pip install 'protobuf>=4.25.3,<5' 'mediapipe>=0.10.13'"
            ) from exc
        raise

    #opens camera
    cap = cv2.VideoCapture(CAMERA_ID, cv2.CAP_V4L2)
    if not cap.isOpened():
        face_mesh.close()
        raise RuntimeError(f"Could not open USB camera: {CAMERA_ID}")

    if not use_fake_tof():
        start_tof_reader()

    #initialize control state variables for mouth session
    center_start_time: float | None = None
    approach_active = False
    approach_start_time: float | None = None
    stop_distance_start: float | None = None
    bite_hold_active = False
    last_approach_command_time = 0.0
    last_align_command_time = 0.0
    last_valid_tof_cm: float | None = None
    last_tof_print_time = 0.0
    last_tracking_gui_time = 0.0
    last_limit_gui_time = 0.0
    feeding_completed_and_homed = False
    deadline = (
        time.time() + MOUTH_SESSION_TIMEOUT if MOUTH_SESSION_TIMEOUT > 0 else None
    )

    #update the gui state
    logger.info(
        "Mouth tracking (track=%dx%d, hold=%.1fs, stop=%.1fcm stable=%.1fs, bite_hold=%.1fs, fake_tof=%s)",
        MOUTH_TRACK_WIDTH,
        MOUTH_TRACK_HEIGHT,
        CENTER_HOLD_SECONDS,
        STOP_DISTANCE_CM,
        STOP_DISTANCE_STABLE_SECONDS,
        hold_seconds,
        use_fake_tof(),
    )

    #repeats reading processing for media pipe after checking for emergency state
    try:
        while True:
            if deadline is not None and time.time() > deadline:
                logger.warning("[MOUTH] Session timeout reached")
                break

            now = time.time()

            #breaks out if estop is activated during feeding
            if _estop_during_motion(buttons, arm, "EMERGENCY_BUTTON_MOUTH_TRACKING"):
                break
            
            #breaks out if emergency is latched
            if buttons is not None and buttons.is_emergency_latched():
                arm.stop("EMERGENCY_LATCHED")
                break

            #ignores feed if its already active
            if buttons is not None and buttons.feed_raw_pressed():
                logger.info("[FEED] Ignored during active feed cycle")
                update_gui_state(
                    "feeding",
                    "FEED ignored during active feeding phase",
                    connected=True,
                )
                buttons.wait_for_feed_release(timeout=0.5)

            #ignore select during feed
            if buttons is not None and buttons.plate_raw_pressed():
                logger.info("[SELECT] Ignored during feeding phase")
                update_gui_state(
                    "feeding",
                    GUI_MESSAGES["select_during_feed"],
                    connected=True,
                )
                buttons.wait_for_plate_release(timeout=0.5)

            #read newest tof measure
            tof_reading = read_tof_cm_safe()
            if tof_reading is not None:
                last_valid_tof_cm = tof_reading
                if now - last_tof_print_time >= 0.5: #paces the command "ALIGN"
                    logger.info("[TOF] Latest distance: %.1f cm", last_valid_tof_cm)
                    last_tof_print_time = now

            ret, frame = cap.read() #capture frame

            #camera failure to capture, repeats if failed
            if not ret:
                time.sleep(LOOP_DELAY)
                continue

            #resize to our resolution
            if frame.shape[1] != MOUTH_TRACK_WIDTH or frame.shape[0] != MOUTH_TRACK_HEIGHT:
                track_frame = cv2.resize(frame, (MOUTH_TRACK_WIDTH, MOUTH_TRACK_HEIGHT))
            else:
                track_frame = frame
            h, w, _ = track_frame.shape #read processed frame dimensions
            results = face_mesh.process(cv2.cvtColor(track_frame, cv2.COLOR_BGR2RGB)) #convert bgr to rgb
            
            
            if results.multi_face_landmarks:
                landmarks = results.multi_face_landmarks[0].landmark
                mx, my = get_mouth_center(landmarks, w, h) 
                cx, cy = w // 2, h // 2 #calculate image center
                #image center
                error_x = mx - cx
                error_y = my - cy
                is_centered = (
                    abs(error_x) < CENTER_TOLERANCE and abs(error_y) < CENTER_TOLERANCE
                )

                #determines if mouth is centered
                if is_centered:
                    if center_start_time is None:
                        center_start_time = now
                    centered_duration = now - center_start_time #calc how long mouth has been centered
                    arm.centered()

                    if now - last_tracking_gui_time >= 1.0:
                        update_gui_state(
                            "mouth_centered",
                            f"Mouth centered for {centered_duration:.1f} sec",
                            connected=True,
                        )
                        last_tracking_gui_time = now #gui updated at most once per second

                    if centered_duration >= CENTER_HOLD_SECONDS and not approach_active:
                        logger.info("[MOUTH] Centered %.1fs — approach allowed", centered_duration)
                        update_gui_state(
                            "approach",
                            "Mouth centered; guarded approach active",
                            connected=True,
                            force=True,
                        )
                        approach_active = True
                        approach_start_time = now
                        stop_distance_start = None
                        last_approach_command_time = 0.0
                else:
                    center_start_time = None
                    if approach_active and not bite_hold_active:
                        logger.info("[APPROACH] Mouth left center — stopping")
                        update_gui_state(
                            "mouth_tracking",
                            "Mouth left center zone; approach stopped",
                            connected=True,
                            force=True,
                        )
                        arm.stop("MOUTH_NOT_CENTERED")
                    if not bite_hold_active:
                        approach_active = False
                        approach_start_time = None
                        stop_distance_start = None

                    if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_ALIGN"):
                        break
                    if now - last_align_command_time >= ALIGN_COMMAND_PERIOD:
                        align_reply = arm.align(float(error_x), float(error_y))
                        last_align_command_time = now

                        limit_hits: list[dict] = []
                        if isinstance(align_reply, dict):
                            limit_hits = align_reply.get("limit_hits") or []
                        limit_message = _track_limit_message(limit_hits)
                        if limit_message and (now - last_limit_gui_time) >= TRACK_LIMIT_GUI_COOLDOWN:
                            update_gui_state(
                                "mouth_tracking_limit",
                                limit_message,
                                connected=True,
                                force=True,
                            )
                            last_limit_gui_time = now #reset gui timer      

                if approach_active:
                    if _estop_during_motion(buttons, arm, "EMERGENCY_DURING_APPROACH"): #check estop latch just in case,
                        approach_active = False 
                        break

                    if approach_start_time is None: #set start time if nothing got set
                        approach_start_time = now

                    if now - approach_start_time > MAX_APPROACH_SECONDS:
                        logger.info("[APPROACH] Timeout — stopping")
                        arm.stop("APPROACH_TIMEOUT")
                        approach_active = False

                    elif now - last_approach_command_time >= APPROACH_COMMAND_PERIOD:
                        tof_cm = last_valid_tof_cm

                        if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_APPROACH_COMMAND"): #check estop before 
                            approach_active = False
                            break

                        if tof_cm is None:
                            update_gui_state(
                                "holding",
                                "No valid ToF reading; holding approach",
                                connected=True,
                            )
                            arm.centered()
                            last_approach_command_time = now

                        elif tof_cm <= STOP_DISTANCE_CM:
                            if stop_distance_start is None:
                                stop_distance_start = now
                                logger.info(
                                    "[APPROACH] ToF %.1f cm reached threshold %.1f cm — starting stable timer",
                                    tof_cm,
                                    STOP_DISTANCE_CM,
                                )

                            stable_duration = now - stop_distance_start
                            seconds_left = max(
                                0,
                                int(round(STOP_DISTANCE_STABLE_SECONDS - stable_duration)),
                            )

                            # Stop forward motion while confirming the ToF reading is stable.
                            # This prevents the arm from continuing to approach during the 2 s guard window.
                            arm.centered()
                            update_gui_state(
                                "bite_hold_pending",
                                f"Mouth distance ready. Confirming for {seconds_left} sec",
                                connected=True,
                            )
                            last_approach_command_time = now

                            if stable_duration >= STOP_DISTANCE_STABLE_SECONDS:
                                logger.info(
                                    "[BITE_HOLD_READY] ToF %.1f cm stable for %.1fs — stopping tracking and holding still",
                                    tof_cm,
                                    STOP_DISTANCE_STABLE_SECONDS,
                                )
                                bite_hold_active = True
                                approach_active = False
                                set_system_state("BITE_HOLD_READY", f"tof_cm={tof_cm:.1f}")

                                # Tell the Pi to stop/hold the arm once. After this, do not send ALIGN,
                                # APPROACH_MOUTH, or CENTERED during the bite window.
                                arm.bite_hold_ready(tof_cm)

                                update_gui_state(
                                    "bite_hold_ready",
                                    GUI_MESSAGES["feed_hold_at_mouth"].format(
                                        seconds=int(round(hold_seconds))
                                    ),
                                    connected=True,
                                    error="NONE",
                                    force=True,
                                )

                                # Camera and MediaPipe are no longer needed during the bite hold.
                                # Release them before the 3 s hold so no alignment loop can continue.
                                cap.release()
                                cap = None
                                cv2.destroyAllWindows()
                                face_mesh.close()
                                face_mesh = None
                                stop_tof_reader()

                                hold_start = time.time()
                                while time.time() - hold_start < hold_seconds:
                                    if _estop_during_motion(buttons, arm, "EMERGENCY_DURING_BITE_HOLD"):
                                        break
                                    seconds_left = max(
                                        0,
                                        int(round(hold_seconds - (time.time() - hold_start))),
                                    )
                                    update_gui_state(
                                        "bite_hold_ready",
                                        GUI_MESSAGES["feed_hold_at_mouth"].format(seconds=seconds_left),
                                        connected=True,
                                    )
                                    time.sleep(0.2)

                                if buttons is not None and buttons.is_emergency_latched():
                                    break

                                update_gui_state(
                                    "recovery",
                                    GUI_MESSAGES["feed_return_home"],
                                    connected=True,
                                    error="NONE",
                                    force=True,
                                )
                                _home_arm(arm, "FEED_COMPLETE_RETURN_HOME")
                                feeding_completed_and_homed = True
                                break

                        else:
                            stop_distance_start = None
                            bite_hold_active = False
                            logger.info("[APPROACH] ToF=%.1f cm — APPROACH_MOUTH", tof_cm)
                            update_gui_state(
                                "approach",
                                f"Approaching mouth | ToF {tof_cm:.1f} cm",
                                connected=True,
                            )
                            arm.approach_mouth(tof_cm)
                            last_approach_command_time = now
            else:
                if approach_active and not bite_hold_active: #this is the approach before the tof hits limit
                    logger.info("[APPROACH] Face lost — stopping")
                    update_gui_state(
                        "error",
                        "Face lost during approach",
                        connected=True,
                        error="No face detected",
                        force=True,
                    )
                    arm.stop("FACE_LOST")
                center_start_time = None
                if not bite_hold_active:
                    approach_active = False
                    approach_start_time = None
                    stop_distance_start = None

            #if enabled, sets up the frame of the gui popup
            if SHOW_MOUTH_PREVIEW:
                preview_frame = track_frame
                if results.multi_face_landmarks: #if mediapipe doesnt find a face
                    landmarks = results.multi_face_landmarks[0].landmark
                    mx, my = get_mouth_center(landmarks, w, h)
                    cv2.circle(preview_frame, (mx, my), 6, (0, 255, 0), -1)
                    cv2.circle(preview_frame, (w // 2, h // 2), 4, (0, 0, 255), -1)
                cv2.imshow("Jetson Mouth Tracking", preview_frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    logger.info("[MOUTH] Preview exit key pressed")
                    arm.stop("KEY_EXIT")
                    break

            time.sleep(LOOP_DELAY)

    finally:
        if not feeding_completed_and_homed: #after the homing phases
            # If an emergency is latched, the emergency path already sent STOP.
            # Do not send another cleanup STOP here; it can look like a small
            # unexpected movement before recovery HOME starts.
            if buttons is None or not buttons.is_emergency_latched():
                arm.stop("MOUTH_TRACKING_PHASE_ENDED")
                try:
                    update_gui_state(
                        "recovery",
                        GUI_MESSAGES["feed_return_home"],
                        connected=True,
                        error="NONE",
                        force=True,
                    )
                    _home_arm(arm, "FEED_PHASE_ENDED_RETURN_HOME")
                    feeding_completed_and_homed = True
                except Exception:
                    logger.exception("Home return failed after mouth phase ended")
                    update_gui_state(
                        "error",
                        "Home return failed after feed",
                        connected=True,
                        error="Home return failed after feed",
                        force=True,
                    )
                    set_system_state("FEED_ERROR_HOME_FAILED", "mouth_phase_ended")

        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        if face_mesh is not None:
            face_mesh.close()
        stop_tof_reader()

        if buttons is not None and buttons.is_emergency_latched():
            update_gui_state(
                "emergency",
                "Emergency stop active",
                emergency=True,
                connected=True,
                force=True,
            )
        elif feeding_completed_and_homed:
            end_feed_cycle("FEED_COMPLETE_HOME_DONE")
            update_gui_state(
                "idle",
                GUI_MESSAGES["feed_end"],
                connected=True,
                error="NONE",
                force=True,
            )
        else:
            update_gui_state(
                "idle",
                "Mouth tracking phase ended",
                connected=True,
                error="NONE",
                force=True,
            )

        logger.info("Mouth tracking phase ended (homed=%s)", feeding_completed_and_homed)

    return feeding_completed_and_homed


def execute_next_bite(
    section_num: int | None = None,
    buttons: ButtonManager | None = None,
    *,
    db: firestore.Client | None = None,
    robot_id: str | None = None,
) -> bool:

    if buttons is not None and buttons.is_emergency_latched(): #always checks emergency latch
        logger.warning("Skipping bite — emergency latched")
        return False

    #chooses section for plate, validates its 1-4
    section = int(section_num if section_num is not None else get_selected_section())
    if section < 1 or section > 4:
        raise ValueError(f"section must be 1-4, got {section}")

    if _dry_run():
        start_feed_cycle(section)
        logger.info("DRY_RUN next_bite: plate gate → SCOOP → spoon → mouth → HOME")
        time.sleep(2.0)
        end_feed_cycle("FEED_COMPLETE_HOME_DONE")
        logger.info("=== BITE DONE (dry run) ===")
        return True

    #actual bite handling, start sending to pi
    try:
        with PiArmClient() as arm:
            bite_t0 = time.monotonic() #cycle timer
            logger.info("Pi ping: %s", arm.ping())
            update_gui_state("idle", "Connected to Raspberry Pi arm server", connected=True, force=True)

            #make sure there is food on the plate, cant go into feed unless there is
            if not ensure_plate_has_food_before_feed(arm, db, robot_id):
                logger.warning("FEED blocked — plate YOLO did not pass")
                return False

            start_feed_cycle(section) #start the cycle
            logger.info("=== BITE START section=%s ===", section)

            #show proper gui messages
            update_gui_state(
                "feeding",
                GUI_MESSAGES["feed_start"].format(section=section),
                selected_plate_section=section,
                connected=True,
                error="NONE",
                force=True,
            )

            if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_SCOOP"):
                return False

            logger.info("Step 1/3: SCOOP section %s", section)
            update_gui_state(
                "scooping",
                GUI_MESSAGES["scoop_start"].format(section=section),
                selected_plate_section=section,
                connected=True,
                error="NONE",
                force=True,
            )
            arm.scoop(section)
            update_gui_state(
                "scoop_complete",
                GUI_MESSAGES["scoop_success"],
                selected_plate_section=section,
                connected=True,
                error="NONE",
                force=True,
            )

            # Let arm/camera settle so spoon is in frame before YOLO scan.
            time.sleep(float(os.environ.get("SCOOP_YOLO_SETTLE_SECONDS", "1.5")))

            #check for the spoon emtpiness after it has gone to default mode, this helps with our models.
            if not run_spoon_yolo_check_after_scoop(section, db, robot_id):
                _home_arm(arm, "SPOON_EMPTY_AFTER_SCOOP_RETURN_HOME")
                end_feed_cycle("SPOON_EMPTY_AFTER_SCOOP")
                update_gui_state(
                    "idle",
                    "Spoon check stopped feeding. Press FEED again to retry, or SELECT another section.",
                    selected_plate_section=section,
                    connected=True,
                    error="NONE",
                    force=True,
                )
                return False

            #check the estop once again
            if _estop_during_motion(buttons, arm, "EMERGENCY_BEFORE_MOUTH"):
                return False

            logger.info("Step 2/3: mouth tracking + ToF approach")
            bite_hold = read_bite_hold_seconds(db, robot_id)
            completed = run_mouth_feed_session(arm, buttons, bite_hold_seconds=bite_hold)

            if buttons is not None and buttons.is_emergency_latched():
                logger.warning("=== BITE ABORTED (emergency) section=%s ===", section)
                return False

            #marks the end of the feeding cycle
            if completed:
                elapsed = time.monotonic() - bite_t0
                logger.info("=== BITE DONE section=%s (%.1fs) ===", section, elapsed)
                target = float(os.environ.get("FEED_CYCLE_TARGET_SECONDS", "30"))
                if elapsed > target:
                    logger.warning(
                        "Feed cycle exceeded target (%.1fs > %.1fs) — tune mouth/YOLO/Pi motion env vars",
                        elapsed,
                        target,
                    )
            return completed
    #failing exceptions catch
    except Exception as exc:
        logger.exception("Bite failed for section %s", section)
        update_gui_state(
            "error",
            f"Mouth phase failed: {exc}. Returning home before unlocking selection.",
            connected=True,
            error="Mouth phase failed",
            force=True,
        )
        try:
            with PiArmClient() as arm:
                arm.stop("MOUTH_PHASE_ERROR")
        except Exception:
            logger.exception("STOP after mouth phase error failed")

        if buttons is not None and buttons.is_emergency_latched():
            mark_emergency_state("FEED_ERROR_DURING_EMERGENCY")
        else:
            try:
                with PiArmClient() as arm:
                    _home_arm(arm, "FEED_ERROR_RETURN_HOME")
                end_feed_cycle("FEED_ERROR_HOME_DONE")
                update_gui_state(
                    "idle",
                    "Feed error handled; arm returned home. SELECT is enabled again.",
                    connected=True,
                    error="NONE",
                    force=True,
                )
            except Exception as home_error:
                logger.exception("Feed error occurred, but HOME also failed")
                set_system_state("FEED_ERROR_HOME_FAILED", str(home_error))
                update_gui_state(
                    "error",
                    f"Feed error, and home return failed: {home_error}. SELECT remains locked.",
                    connected=True,
                    error="Home return failed",
                    force=True,
                )
        raise

    return False

#update the app for selection
def handle_plate_select_after_scan(
    arm: PiArmClient,
    db: firestore.Client | None,
    robot_id: str | None,
) -> int:
    """SELECT after scan: YOLO plate check from home, or cycle section at plate view."""
    from yolo_gates import handle_plate_button_after_scan

    return handle_plate_button_after_scan(arm, db, robot_id)

#send stop command to arm
def execute_stop(reason: str = "STOP") -> None:
    if _dry_run():
        logger.info("DRY_RUN stop (%s)", reason)
        return
    with PiArmClient() as arm:
        arm.stop(reason)

#send home message to arm
def execute_home(reason: str = "HOME") -> None:
    if _dry_run():
        logger.info("DRY_RUN home")
        return
    with PiArmClient() as arm:
        _home_arm(arm, reason)