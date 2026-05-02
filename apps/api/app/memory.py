"""Persistent memory layer (per-user × per-tenant).

Two artifacts:
- `memory_facts`: short, user/tenant-scoped statements that persist across
  conversations (e.g. "We bank with CIB and HSBC; payroll runs from NBE").
  Pinned facts always surface; non-pinned are surfaced by recency × importance.
- `conversation_summaries`: a rolling, short summary per conversation, refreshed
  after every assistant turn so the next turn can be primed cheaply.
"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from app.db import get_db


# ---------- Facts ----------

def pin_fact(*, tenant_id: str, user_id: str, fact: str,
             source: Optional[str] = None, importance: int = 7,
             pinned: bool = True, scope: str = "user_tenant") -> dict:
    fact = (fact or "").strip()
    if not fact:
        raise ValueError("fact is empty")
    fid = "fact_" + uuid.uuid4().hex[:12]
    with get_db() as conn:
        conn.execute(
            """INSERT INTO memory_facts
               (id, tenant_id, user_id, scope, fact, source, importance, pinned)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (fid, tenant_id, user_id, scope, fact, source, max(1, min(10, importance)), pinned),
        )
    return {"id": fid, "fact": fact, "importance": importance, "pinned": pinned, "scope": scope}


def list_facts(*, tenant_id: str, user_id: str, limit: int = 50) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, fact, source, importance, pinned, created_at
               FROM memory_facts
               WHERE tenant_id = %s AND (user_id = %s OR scope = 'tenant')
               ORDER BY pinned DESC, importance DESC, created_at DESC
               LIMIT %s""",
            (tenant_id, user_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_fact(*, tenant_id: str, user_id: str, fact_id: str) -> bool:
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM memory_facts WHERE id = %s AND tenant_id = %s AND user_id = %s",
            (fact_id, tenant_id, user_id),
        )
        return (cur.rowcount or 0) > 0


def recall_relevant(*, tenant_id: str, user_id: str,
                    query: str = "", k: int = 8) -> list[dict]:
    """Return the most relevant facts for a query.

    Strategy: always include pinned + top-importance, then add facts whose text
    has any keyword overlap with the query (case-insensitive). Cheap, no
    embeddings — adequate for the V1 scope and the seeded data volume.
    """
    facts = list_facts(tenant_id=tenant_id, user_id=user_id, limit=200)
    if not facts:
        return []
    if not query:
        return facts[:k]
    qtokens = {w.lower() for w in query.split() if len(w) > 2}
    scored = []
    for f in facts:
        text = f["fact"].lower()
        overlap = sum(1 for w in qtokens if w in text)
        score = (10 if f["pinned"] else 0) + (f["importance"] or 5) + overlap * 3
        scored.append((score, f))
    scored.sort(key=lambda x: -x[0])
    out = [f for _, f in scored[:k]]
    # Mark last_used_at
    try:
        with get_db() as conn:
            conn.execute(
                "UPDATE memory_facts SET last_used_at = NOW() WHERE id = ANY(%s)",
                ([f["id"] for f in out],),
            )
    except Exception:
        pass
    return out


# ---------- Conversation summaries ----------

def get_summary(conversation_id: str) -> Optional[str]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT summary FROM conversation_summaries WHERE conversation_id = %s",
            (conversation_id,),
        ).fetchone()
    return row["summary"] if row else None


def upsert_summary(*, conversation_id: str, tenant_id: str, user_id: str, summary: str) -> None:
    summary = (summary or "").strip()[:4000]
    if not summary:
        return
    with get_db() as conn:
        conn.execute(
            """INSERT INTO conversation_summaries (conversation_id, tenant_id, user_id, summary, updated_at)
               VALUES (%s, %s, %s, %s, NOW())
               ON CONFLICT (conversation_id) DO UPDATE
                 SET summary = EXCLUDED.summary, updated_at = NOW()""",
            (conversation_id, tenant_id, user_id, summary),
        )


def recent_turns(conversation_id: str, limit_turns: int = 6) -> list[dict]:
    """Return the last N (user, assistant) turns for the conversation."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT role, content_json, created_at FROM messages
               WHERE conversation_id = %s
               ORDER BY created_at DESC
               LIMIT %s""",
            (conversation_id, limit_turns * 2),
        ).fetchall()
    rows = list(reversed(rows))
    out = []
    for r in rows:
        try:
            content = json.loads(r["content_json"])
        except Exception:
            content = {"text": r["content_json"]}
        text = content.get("text") or content.get("answer") or ""
        if text:
            out.append({"role": r["role"], "text": text[:2500]})
    return out
