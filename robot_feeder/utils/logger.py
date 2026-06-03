"""Logging setup for robot_feeder."""

from __future__ import annotations

import logging


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger("robot_feeder")
