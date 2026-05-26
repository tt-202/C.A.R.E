from ultralytics import YOLO
import cv2

# =========================
# LOAD TRAINED YOLO MODEL
# =========================
model = YOLO("best.pt")

# =========================
# JETSON CSI CAMERA PIPELINE
# Raspberry Pi Camera -> Jetson CSI Port
# =========================
def gstreamer_pipeline(
    sensor_id=0,
    capture_width=1280,
    capture_height=720,
    display_width=1280,
    display_height=720,
    framerate=30,
    flip_method=0,
):
    return (
        "nvarguscamerasrc sensor-id=%d ! "
        "video/x-raw(memory:NVMM), "
        "width=(int)%d, height=(int)%d, "
        "framerate=(fraction)%d/1 ! "
        "nvvidconv flip-method=%d ! "
        "video/x-raw, width=(int)%d, height=(int)%d, "
        "format=(string)BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=(string)BGR ! appsink"
        % (
            sensor_id,
            capture_width,
            capture_height,
            framerate,
            flip_method,
            display_width,
            display_height,
        )
    )

# =========================
# OPEN JETSON CAMERA
# =========================
cap = cv2.VideoCapture(
    gstreamer_pipeline(flip_method=0),
    cv2.CAP_GSTREAMER
)

if not cap.isOpened():
    print("Error: Unable to open Jetson camera")
    exit(1)

print("Camera started successfully")

# =========================
# MAIN LOOP
# =========================
while True:
    ret, frame = cap.read()

    if not ret:
        print("Failed to capture frame")
        break

    # =========================
    # YOLO INFERENCE
    # =========================
    results = model(frame)

    # Draw detections
    annotated_frame = results[0].plot()

    # =========================
    # DISPLAY OUTPUT
    # =========================
    cv2.imshow("Jetson YOLO Detection", annotated_frame)

    # Press Q to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# =========================
# CLEANUP
# =========================
cap.release()
cv2.destroyAllWindows()