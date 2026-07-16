"""
Hits care-app so the caregiver gets an e-stop push.

Worker calls this after STOP is already on the arm — don't wait on this for safety.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


def notify_app_backend_emergency(
    *,
    robot_id: str,
    reason: str,
    phase: str,
) -> None:
    # both of these need to be set on the Jetson or we just log and bail
    url = os.environ.get("CARE_APP_EMERGENCY_URL", "").strip()
    secret = os.environ.get("CARE_ROBOT_SHARED_SECRET", "").strip()

    if not url:
        logger.warning("[APP_NOTIFY] CARE_APP_EMERGENCY_URL not set — skipping push route")
        return
    if not secret:
        logger.warning("[APP_NOTIFY] CARE_ROBOT_SHARED_SECRET not set — skipping push route")
        return

    payload = {
        "robotId": robot_id,
        "reason": reason,
        "phase": phase,
        "severity": "critical",
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-robot-secret": secret,  # must match the app backend
        },
    )

    try:
        # short timeout — e-stop path shouldn't hang on a slow network
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            logger.info("[APP_NOTIFY] Push route response %s: %s", resp.status, body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error("[APP_NOTIFY] HTTP %s: %s", e.code, body)
    except urllib.error.URLError as e:
        logger.error("[APP_NOTIFY] URL error: %s", e)
    except Exception:
        logger.exception("[APP_NOTIFY] unexpected error")
