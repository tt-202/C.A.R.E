import cv2
import numpy as np
from pupil_apriltags import Detector

# Initialize Detector
at_detector = Detector(families='tag36h11')

# SMART CAMERA PICKER
cap = None
for i in [0, 1, 2]:
    temp_cap = cv2.VideoCapture(i)
    if temp_cap.isOpened():
        print(f"Trying camera index {i}...")
        cap = temp_cap
        break

if cap is None or not cap.isOpened():
    print("Error: No camera found. Check System Settings > Privacy > Camera.")
    exit()

print("Running AprilTag Detector")
print("Press 'q' to quit.")

while True:
    ret, frame = cap.read()
    if not ret: break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    results = at_detector.detect(gray)

    for r in results:
        (A, B, C, D) = r.corners
        corners = np.array([A, B, C, D], dtype=np.int32)
        cv2.polylines(frame, [corners], True, (0, 255, 0), 2)
        cv2.putText(frame, f"ID: {r.tag_id}", (int(A[0]), int(A[1]) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

    cv2.imshow("AprilTag Detection", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()