"""
robot_feeding_config.py

Reads feeding settings (such as bite hold time) from Firestore.

Flow:
  Caregiver App → Firestore → Jetson → Feeding Cycle

If the Firestore value is missing or invalid, the system uses the
default BITE_HOLD_SECONDS from the environment variable.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# safety rails — tweak with env if you really need to
MIN_BITE_HOLD_SECONDS = float(os.environ.get("MIN_BITE_HOLD_SECONDS", "1.0"))
MAX_BITE_HOLD_SECONDS = float(os.environ.get("MAX_BITE_HOLD_SECONDS", "10.0"))
# used when Firestore has nothing useful
DEFAULT_BITE_HOLD_SECONDS = float(os.environ.get("BITE_HOLD_SECONDS", "2.0"))


def _clamp_bite_hold(seconds: float) -> float:
    #Keep the hold time between min and max so bad values don't hurt anyone.
    return max(MIN_BITE_HOLD_SECONDS, min(MAX_BITE_HOLD_SECONDS, float(seconds)))


def read_bite_hold_seconds(db, robot_id: str | None) -> float:
    
    # offline / unit-test path — just use the env default
    if db is None or not robot_id:
        return _clamp_bite_hold(DEFAULT_BITE_HOLD_SECONDS)

    try:
        # same path care-app writes when the slider saves
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
        # don't crash the feed cycle just because config fetch failed
        logger.exception("[FEED_CONFIG] Failed to read bite_hold_seconds from Firestore")

    # nothing usable in Firestore — fall back to env
    fallback = _clamp_bite_hold(DEFAULT_BITE_HOLD_SECONDS)
    logger.info("[FEED_CONFIG] bite_hold_seconds=%.1f (env default)", fallback)
    return fallback
