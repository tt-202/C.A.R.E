"""Firestore command listener — same contract as app/robot-worker."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)

ALLOWED = frozenset({"home", "next_bite", "pause", "stop"})


class FirebaseClient:
    def __init__(self, robot_id: str, credentials_path: str | None) -> None:
        self.robot_id = robot_id
        self.credentials_path = credentials_path
        self._db: Any = None
        self._col: Any = None

    def connect(self) -> bool:
        if not self.credentials_path or not os.path.isfile(self.credentials_path):
            logger.warning("Firebase disabled — set GOOGLE_APPLICATION_CREDENTIALS")
            return False
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred = credentials.Certificate(self.credentials_path)
            firebase_admin.initialize_app(cred)
        self._db = firestore.client()
        self._col = self._db.collection("robots").document(self.robot_id).collection("commands")
        logger.info("Firestore connected robot_id=%s", self.robot_id)
        return True

    def listen(self, on_command: Callable[[str, dict[str, Any] | None], None]) -> None:
        if self._col is None:
            return
        from google.cloud.firestore_v1.base_query import FieldFilter

        query = self._col.where(filter=FieldFilter("status", "==", "pending"))

        def on_snapshot(_: list[Any], changes: list[Any], __: Any) -> None:
            for change in changes:
                t = getattr(change, "type", None)
                name = getattr(t, "name", "") if t is not None else ""
                if name not in ("ADDED", "MODIFIED") and t not in (1, 2):
                    text = str(t) if t is not None else ""
                    if not (text.endswith("ADDED") or text.endswith("MODIFIED")):
                        continue
                snap = change.document
                data = snap.to_dict() or {}
                if data.get("status") != "pending":
                    continue
                cmd = data.get("cmd")
                if cmd not in ALLOWED:
                    continue
                ref = self._col.document(snap.id)
                if not self._claim(ref):
                    continue
                payload = data.get("payload")
                try:
                    on_command(str(cmd), payload if isinstance(payload, dict) else None)
                    self._finish(ref, ok=True)
                except Exception as e:
                    logger.exception("command %s failed", snap.id)
                    self._finish(ref, ok=False, error=str(e))

        query.on_snapshot(on_snapshot)
        logger.info("Listening for pending robot commands")

    def _claim(self, ref: Any) -> bool:
        from firebase_admin import firestore

        @firestore.transactional
        def _txn(transaction: Any, doc_ref: Any) -> bool:
            snap = doc_ref.get(transaction=transaction)
            if not snap.exists:
                return False
            data = snap.to_dict() or {}
            if data.get("status") != "pending":
                return False
            transaction.update(
                doc_ref,
                {"status": "running", "updatedAt": datetime.now(timezone.utc)},
            )
            return True

        return _txn(self._db.transaction(), ref)

    def _finish(self, ref: Any, *, ok: bool, error: str | None = None) -> None:
        ref.update(
            {
                "status": "done" if ok else "error",
                "error": error,
                "updatedAt": datetime.now(timezone.utc),
            }
        )
