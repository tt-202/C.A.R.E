"""Read feeding settings from Firestore (written by care-app)."""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

MIN_BITE_HOLD_SECONDS = float(os.environ.get("MIN_BITE_HOLD_SECONDS", "1.0"))
MAX_BITE_HOLD_SECONDS = float(os.environ.get("MAX_BITE_HOLD_SECONDS", "10.0"))
DEFAULT_BITE_HOLD_SECONDS = float(os.environ.get("BITE_HOLD_SECONDS", "2.0"))


def _clamp_bite_hold(seconds: float) -> float:
    return max(MIN_BITE_HOLD_SECONDS, min(MAX_BITE_HOLD_SECONDS, float(seconds)))


def read_bite_hold_seconds(db, robot_id: str | None) -> float:
    """
    Read bite_hold_seconds from robots/{robotId}/config/feeding.
    Falls back to BITE_HOLD_SECONDS env when missing or on error.
    """
    if db is None or not robot_id:
        return _clamp_bite_hold(DEFAULT_BITE_HOLD_SECONDS)

    try:
        snap = (
            db.collection("robots")
            .document(str(robot_id))
            .collection("config")
            .document("feeding")
            .get()
        )
        if snap.exists:
            raw = (snap.to_dict() or {}).get("bite_hold_seconds")
            if raw is not None:
                value = _clamp_bite_hold(float(raw))
                logger.info("[FEED_CONFIG] bite_hold_seconds=%.1f (Firestore)", value)
                return value
    except Exception:
        logger.exception("[FEED_CONFIG] Failed to read bite_hold_seconds from Firestore")

    fallback = _clamp_bite_hold(DEFAULT_BITE_HOLD_SECONDS)
    logger.info("[FEED_CONFIG] bite_hold_seconds=%.1f (env default)", fallback)
    return fallback
