import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import urllib.request
import os
import time

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

def get_lip_points(landmarks, indices, w, h):
    return [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in indices]

def mouth_openness(landmarks, w, h):
    top_lip = landmarks[13]
    bottom_lip = landmarks[14]
    left_corner = landmarks[61]
    right_corner = landmarks[291]
    mouth_height = abs(top_lip.y - bottom_lip.y) * h
    mouth_width = abs(left_corner.x - right_corner.x) * w
    return mouth_height / (mouth_width + 1e-6)

# Setup detector
base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    num_faces=2,
    min_face_detection_confidence=0.5,
    min_face_presence_confidence=0.5,
    min_tracking_confidence=0.5
)
detector = vision.FaceLandmarker.create_from_options(options)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

print("Press 'q' to quit.")
print("Benchmarking started...\n")

# Benchmark variables
frame_count = 0
total_detect_time = 0.0
total_loop_time = 0.0
start_time = time.perf_counter()
last_report_time = start_time

while cap.isOpened():
    loop_start = time.perf_counter()

    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 1)
    h, w = frame.shape[:2]

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

    # Time only the MediaPipe detection
    detect_start = time.perf_counter()
    result = detector.detect(mp_image)
    detect_end = time.perf_counter()
    detect_time_ms = (detect_end - detect_start) * 1000

    overlay = frame.copy()

    if result.face_landmarks:
        for face in result.face_landmarks:
            outer_pts = get_lip_points(face, LIPS_OUTER, w, h)
            inner_pts = get_lip_points(face, LIPS_INNER, w, h)

            cv2.fillPoly(overlay, [np.array(outer_pts)], (0, 60, 200))
            cv2.fillPoly(overlay, [np.array(inner_pts)], (20, 20, 20))
            cv2.polylines(frame, [np.array(outer_pts)], True, (0, 100, 255), 2)
            cv2.polylines(frame, [np.array(inner_pts)], True, (0, 200, 255), 1)

            for idx in set(LIPS_OUTER + LIPS_INNER):
                pt = (int(face[idx].x * w), int(face[idx].y * h))
                cv2.circle(frame, pt, 2, (255, 255, 255), -1)

            ratio = mouth_openness(face, w, h)
            status = "OPEN" if ratio > 0.08 else "CLOSED"
            color = (0, 255, 100) if ratio > 0.08 else (100, 100, 255)

            mouth_x = int(face[0].x * w)
            mouth_y = int(face[0].y * h) - 20
            cv2.putText(frame, status, (mouth_x - 40, mouth_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)
    cv2.rectangle(frame, (0, 0), (w, 36), (0, 0, 0), -1)
    cv2.putText(frame, "MediaPipe Mouth Detection  |  Press Q to quit",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 200), 1)

    cv2.imshow("Mouth Detection", frame)

    # End loop timing
    loop_end = time.perf_counter()
    loop_time_ms = (loop_end - loop_start) * 1000

    # Update stats
    frame_count += 1
    total_detect_time += detect_time_ms
    total_loop_time += loop_time_ms

    elapsed_total = loop_end - start_time
    avg_detect_ms = total_detect_time / frame_count
    avg_loop_ms = total_loop_time / frame_count
    avg_fps = frame_count / elapsed_total if elapsed_total > 0 else 0

    # Print to terminal every 1 second
    if loop_end - last_report_time >= 1.0:
        print(
            f"Frames: {frame_count} | "
            f"Avg Detect: {avg_detect_ms:.2f} ms | "#Avg Detect = just MediaPipe inference
            f"Avg Loop: {avg_loop_ms:.2f} ms | " #Avg Loop = everything in the loop, including camera read, drawing, display
            f"Avg FPS: {avg_fps:.2f}"#Avg FPS = actual practical performance
        )
        last_report_time = loop_end

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()

# Final summary
total_elapsed = time.perf_counter() - start_time
if frame_count > 0:
    print("\nFinal Benchmark Summary")
    print(f"Total Frames Processed: {frame_count}")
    print(f"Total Runtime: {total_elapsed:.2f} s")
    print(f"Average Detection Time: {total_detect_time / frame_count:.2f} ms")
    print(f"Average Loop Time: {total_loop_time / frame_count:.2f} ms")
    print(f"Average FPS: {frame_count / total_elapsed:.2f}")
else:
    print("No frames processed.")
    #conda activate base
    #python mediapipe_mouth_detection.py

    """ Measure centroid of mouth, add !!
    def mouth_centroid(landmarks, indices, w, h):
    pts = [(landmarks[i].x * w, landmarks[i].y * h) for i in indices]
    cx = int(sum(p[0] for p in pts) / len(pts))
    cy = int(sum(p[1] for p in pts) / len(pts))
    return cx, cy"""

# getter to get the value of mouth centroid, and whether it's open or closed
