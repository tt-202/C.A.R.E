# Testing robot_feeder step by step

Run everything from `robot_feeder/` on the **Jetson** (camera/GPIO/arm). On a Mac you can only dry-run motion and Firebase (no CSI camera).

```bash
cd robot_feeder
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install opencv-python ultralytics mediapipe   # vision tests
cp .env.example .env
# edit .env — at minimum DRY_RUN=true until arm is safe
```

---

## Order of tests

| Step | Script | What you verify |
|------|--------|-----------------|
| 1 | `python scripts/test_camera.py` | CSI/USB camera opens, live window |
| 2 | `python scripts/test_apriltag_live.py` | AprilTag → section 1–4 overlay on plate view |
| 3 | `python scripts/test_yolo_live.py` | YOLO draws boxes; `FOOD: YES/NO` overlay |
| 4 | `python scripts/test_face_live.py` | Face detected, mouth open, offset |
| 5 | `python scripts/test_arm_motion.py` | Plate → scoop → user → home (logs if `DRY_RUN=true`) |
| 6 | `BUTTONS_ENABLED=true python scripts/test_gpio.py` | Feed / plate / e-stop prints |
| 7 | `python scripts/test_firebase_command.py` | Firestore commands from care-app |
| 8 | `python scripts/test_states_interactive.py` | Full state machine; type `feed` / `stop` |
| 9 | `python main.py` | Production loop (all pieces together) |

Press **Q** in OpenCV windows to exit.

### YOLO model file

```bash
mkdir -p models
# copy your trained weights, e.g. from jetson_controller:
cp ../jetson_controller/best.pt models/food.pt   # if you have best.pt there
```

Set `YOLO_MODEL_PATH=models/food.pt` in `.env`.

---

## Operator GUI on monitor / “LCD”

The panel is **Tkinter on the Jetson desktop** (HDMI monitor). It is **not** a separate SPI character LCD unless you add that driver later.

**1. Preview GUI only (no robot):**

```bash
export DISPLAY=:0
pip install Pillow
python scripts/test_gui.py
```

**2. GUI + full feeder:**

In `.env`:

```env
GUI_ENABLED=true
# GUI_FULLSCREEN=true   # optional kiosk mode
```

```bash
export DISPLAY=:0
python main.py
```

The window updates automatically:

| Panel field | Source |
|-------------|--------|
| Connection | Firestore connected |
| Current State | IDLE / CHECK MOUTH / FEEDING / RETURN HOME / EMERGENCY |
| Bites | Session bite count |
| Error | NO FOOD, NO FACE, MOUTH CLOSED, EMERGENCY, etc. |
| Plate image | Section 1–4 (`gui/images/sectionN.png`) |

Optional images: copy PNGs to `robot_feeder/gui/images/` or `jetson_controller/gui/images/`.

You do **not** need to run `jetson_controller/gui/lcd_display.py` anymore for live status.

---

## Test with the care-app (end-to-end cloud path)

1. **Jetson:** `GOOGLE_APPLICATION_CREDENTIALS`, `ROBOT_ID=care-01`, `DRY_RUN=true` (first).
2. **care-app `.env`:** same `ROBOT_ID`, `NEXT_PUBLIC_ROBOT_ENABLED=true`, Firebase admin JSON.
3. Deploy Firestore rules: `firebase deploy --only firestore:rules` from `app/care-app`.
4. **Option A — listener only:**  
   `python scripts/test_firebase_command.py`  
   In the app: caregiver starts a meal (auto `next_bite` every 30s) or call API manually.
5. **Option B — full feeder:**  
   `python main.py`  
   Caregiver session should trigger `next_bite` → state machine runs detect → feed → retract.

**Manual API test** (replace token and URL):

```bash
curl -X POST https://YOUR_APP.vercel.app/api/robot/command \
  -H "Authorization: Bearer FIREBASE_ID_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"next_bite","payload":{"sectionNum":1}}'
```

---

## What each state does (when you run `main.py` or step 7)

```text
IDLE          → wait: Firestore next_bite, GPIO feed, or interactive "feed"
SELECT_PLATE  → AprilTag on plate picks section 1–4 (see gui/PLATE_SETUP.md)
DETECT_MOUTH  → one camera frame + YOLO + face + TOF check
FEED          → MotionPlanner.execute_bite(section)
RETRACT       → go_home
EMERGENCY     → stop arm → RETRACT
```

With `DRY_RUN=true`, arm moves are **logged**, not sent to hardware.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Camera fails on Jetson | `CAMERA_DEVICE_ID=0`, display attached or `export DISPLAY=:0` for OpenCV windows |
| Camera works on Mac but not Jetson | Use Jetson CSI pipeline (script uses GStreamer first) |
| YOLO “model not found” | Add `models/food.pt` |
| No Firestore events | `ROBOT_ID` must match app; service account needs Firestore access |
| GPIO no events | `BUTTONS_ENABLED=true`, user in `gpio` group, BCM pins match wiring |
| GUI empty images | Add `jetson_controller/gui/images/section1.png` … `section4.png` |

---

## Recommended progression

1. Mac/CI: `test_arm_motion.py` + `test_states_interactive.py` (DRY_RUN).  
2. Jetson + monitor: steps 1–3 (camera, YOLO, face).  
3. Jetson: step 4 with `DRY_RUN=false` and **clear workspace**.  
4. Jetson: step 6 + care-app caregiver role.  
5. Enable systemd when stable: `deploy/install-systemd.sh`.
