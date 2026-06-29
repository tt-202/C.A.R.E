"""Notify care-app when YOLO detects an empty plate (caregiver push)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def _plate_alert_url() -> str:
    explicit = os.environ.get("CARE_APP_PLATE_ALERT_URL", "").strip()
    if explicit:
        return explicit
    emergency = os.environ.get("CARE_APP_EMERGENCY_URL", "").strip()
    if emergency.endswith("/api/robot/emergency"):
        return emergency.replace("/api/robot/emergency", "/api/robot/plate-alert")
    return ""


def notify_app_backend_plate_empty(
    *,
    robot_id: str,
    section: int,
    status: str = "empty",
) -> None:
    url = _plate_alert_url()
    secret = os.environ.get("CARE_ROBOT_SHARED_SECRET", "").strip()

    if not url:
        logger.warning("[PLATE_NOTIFY] CARE_APP_PLATE_ALERT_URL not set — skipping caregiver push")
        return
    if not secret:
        logger.warning("[PLATE_NOTIFY] CARE_ROBOT_SHARED_SECRET not set — skipping caregiver push")
        return

    payload = {
        "robotId": robot_id,
        "section": int(section),
        "status": status,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-robot-secret": secret,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            logger.info("[PLATE_NOTIFY] response %s: %s", resp.status, body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("[PLATE_NOTIFY] HTTP %s: %s", e.code, body)
    except urllib.error.URLError as e:
        logger.error("[PLATE_NOTIFY] URL error: %s", e)
    except Exception:
        logger.exception("[PLATE_NOTIFY] unexpected error")
