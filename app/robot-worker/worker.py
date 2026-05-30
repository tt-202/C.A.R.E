#!/usr/bin/env python3
"""
Listen for Firestore robot commands and run them on myCobot 320 (Jetson Orin Nano).

Setup:
  python3 -m venv venv && source venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env   # edit paths
  export $(grep -v '^#' .env | xargs)
  python worker.py
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from robot_motion import execute_command

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("care-robot-worker")

ALLOWED = frozenset({"home", "next_bite", "pause", "stop"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def robot_id() -> str:
    return os.environ.get("ROBOT_ID", "care-01").strip() or "care-01"


def commands_col(db: firestore.Client) -> firestore.CollectionReference:
    return db.collection("robots").document(robot_id()).collection("commands")


@firestore.transactional
def _claim_transaction(transaction: firestore.Transaction, ref: firestore.DocumentReference) -> bool:
    snap = ref.get(transaction=transaction)
    if not snap.exists:
        return False
    data = snap.to_dict() or {}
    if data.get("status") != "pending":
        return False
    transaction.update(ref, {"status": "running", "updatedAt": utc_now()})
    return True


def claim_command(db: firestore.Client, ref: firestore.DocumentReference) -> bool:
    return _claim_transaction(db.transaction(), ref)


def finish_command(
    ref: firestore.DocumentReference,
    *,
    ok: bool,
    error: str | None = None,
) -> None:
    ref.update(
        {
            "status": "done" if ok else "error",
            "error": error,
            "updatedAt": utc_now(),
        }
    )


def process_change(db: firestore.Client, col: firestore.CollectionReference, change: Any) -> None:
    if change.type not in (
        firestore.DocumentChange.Type.ADDED,
        firestore.DocumentChange.Type.MODIFIED,
    ):
        return
    snap = change.document
    data = snap.to_dict() or {}
    if data.get("status") != "pending":
        return
    cmd = data.get("cmd")
    if cmd not in ALLOWED:
        logger.warning("skip invalid cmd on %s", snap.id)
        return
    ref = col.document(snap.id)
    if not claim_command(db, ref):
        return
    payload = data.get("payload")
    try:
        execute_command(str(cmd), payload if isinstance(payload, dict) else None)
        finish_command(ref, ok=True)
        logger.info("done %s cmd=%s", snap.id, cmd)
    except Exception as e:
        logger.exception("command %s failed", snap.id)
        finish_command(ref, ok=False, error=str(e))


def main() -> int:
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path or not os.path.isfile(cred_path):
        logger.error("Set GOOGLE_APPLICATION_CREDENTIALS to a service account JSON file")
        return 1

    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    col = commands_col(db)
    query = col.where(filter=FieldFilter("status", "==", "pending"))

    def on_snapshot(doc_snapshots: list[Any], changes: list[Any], read_time: Any) -> None:
        for change in changes:
            process_change(db, col, change)

    logger.info("listening robot_id=%s dry_run=%s", robot_id(), os.environ.get("DRY_RUN", "true"))
    query.on_snapshot(on_snapshot)

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.info("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
