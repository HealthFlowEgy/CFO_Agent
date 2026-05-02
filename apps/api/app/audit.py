import hashlib
import json
from typing import Optional

from app.db import get_db


def _hash(prev: Optional[str], event: str, payload: dict) -> str:
    h = hashlib.sha256()
    h.update((prev or "").encode())
    h.update(event.encode())
    h.update(json.dumps(payload, sort_keys=True, default=str).encode())
    return h.hexdigest()


def record(event: str, payload: dict, *, tenant_id: Optional[str] = None,
           user_id: Optional[str] = None) -> None:
    with get_db() as conn:
        prev_row = conn.execute(
            "SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        prev = prev_row["hash"] if prev_row else None
        h = _hash(prev, event, payload)
        conn.execute(
            """INSERT INTO audit_log (tenant_id, user_id, event, payload_json, prev_hash, hash)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (tenant_id, user_id, event, json.dumps(payload, default=str), prev, h),
        )
