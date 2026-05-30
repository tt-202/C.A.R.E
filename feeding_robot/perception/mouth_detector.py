import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import urllib.request
import os
import time
import lcd_display   # ✅ NEW

class MouthDetector:
    GUI_INSTANCE = None

    # Download model if needed
    MODEL_PATH = "face_landmarker.task"
    if not os.path.exists(MODEL_PATH):
        print("Downloading face landmarker model...")
        urllib.request.urlretrieve(
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
            MODEL_PATH
        )
        print("Done.")

    LIPS_OUTER = [61, 185, 40, 39, 37, 0, 267, 269, 270, 409,
                291, 375, 321, 405, 314, 17, 84, 181, 91, 146]

    LIPS_INNER = [78, 191, 80, 81, 82, 13, 312, 311, 310, 415,
                308, 324, 318, 402, 317, 14, 87, 178, 88, 95]


    def mouth_centroid(landmarks, indices, w, h):
        pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
        cx = int(sum(p[0] for p in pts) / len(pts))
        cy = int(sum(p[1] for p in pts) / len(pts))
        return cx, cy


    def mouth_openness(landmarks, w, h):
        top_lip = landmarks[13]
        bottom_lip = landmarks[14]
        left_corner = landmarks[61]
        right_corner = landmarks[291]

        mouth_height = abs(top_lip.y - bottom_lip.y) * h
        mouth_width = abs(left_corner.x - right_corner.x) * w
        return mouth_height / (mouth_width + 1e-6)


    # Camera setup (unchanged)
    def gstreamer_pipeline(...):
        return (
            "nvarguscamerasrc sensor-id=%d ! "
            "video/x-raw(memory:NVMM), width=(int)%d, height=(int)%d, framerate=(fraction)%d/1 ! "
            "nvvidconv flip-method=%d ! "
            "video/x-raw, width=(int)%d, height=(int)%d, format=(string)BGRx ! "
            "videoconvert ! "
            "video/x-raw, format=(string)BGR ! appsink"
        )


    cap = cv2.VideoCapture(gstreamer_pipeline(flip_method=0), cv2.CAP_GSTREAMER)

    if not cap.isOpened():
        print("Error: Unable to open camera")
        exit(1)

    base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        num_faces=2,  # we allow detection but CONTROL logic handles filtering
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5
    )

    detector = vision.FaceLandmarker.create_from_options(options)

    print("Running... Press Q to quit")

    mouth_state = {}

    while cap.isOpened():

        ret, frame = cap.read()
        if not ret:
            break

        frame = cv2.flip(frame, 1)
        h, w = frame.shape[:2]

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        result = detector.detect(mp_image)

        faces = result.face_landmarks if result.face_landmarks else []
        face_count = len(faces)

        # =========================
        # 🚨 FACE COUNT LOGIC
        # =========================
        if face_count > 1:
            lcd_display.set_message("TOO MANY FACES IN VIEW")
            continue

        if face_count == 0:
            lcd_display.set_message("NO FACE DETECTED")
            continue

        # =========================
        # ✅ SINGLE FACE SAFE
        # =========================
        face = faces[0]

        # centroid
        cx, cy = mouth_centroid(face, LIPS_OUTER, w, h)

        cam_cx = w // 2
        cam_cy = h // 2

        offset_x = cx - cam_cx
        offset_y = cy - cam_cy

        ratio = mouth_openness(face, w, h)
        is_open = ratio > 0.08

        # update state
        mouth_state = {
            "cx": cx,
            "cy": cy,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "is_open": is_open,
            "ratio": ratio
        }

        # =========================
        # 📡 LCD OUTPUT
        # =========================
        if is_open:
            lcd_display.set_message(f"MOUTH OPEN | dx:{offset_x} dy:{offset_y}")
        else:
            lcd_display.set_message(f"TRACKING | dx:{offset_x} dy:{offset_y}")

        # =========================
        # VISUAL DEBUG
        # =========================
        cv2.circle(frame, (cx, cy), 5, (0, 255, 255), -1)
        cv2.circle(frame, (cam_cx, cam_cy), 5, (255, 0, 0), -1)
        cv2.line(frame, (cam_cx, cam_cy), (cx, cy), (0, 255, 255), 2)

        cv2.imshow("Mouth Detection", frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

    # ONE FACE ERROR DIRECTLY SENDS TO LCD_DISPLAY