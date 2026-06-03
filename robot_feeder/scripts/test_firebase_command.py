#!/usr/bin/env python3
"""
Step 6: Firestore listener only — logs commands from care-app without running the full state machine.

From another machine / care-app: enable ROBOT_ID match and POST /api/robot/command
Or enqueue manually in Firebase Console on robots/{ROBOT_ID}/commands.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import load_settings
from app_bridge.firebase_client import FirebaseClient


def main() -> int:
    settings = load_settings()
    fb = FirebaseClient(settings.robot_id, settings.firebase_credentials)
    if not fb.connect():
        print("FAIL: set GOOGLE_APPLICATION_CREDENTIALS to service account JSON")
        return 1

    def on_cmd(cmd: str, payload: dict | None) -> None:
        print(f"EXECUTED cmd={cmd} payload={payload}")

    fb.listen(on_cmd)
    print(f"Listening robot_id={settings.robot_id} … Ctrl+C to stop")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
