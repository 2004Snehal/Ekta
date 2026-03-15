"""
NLQ Session routes — store and restore full chat sessions.

POST /nlq/sessions               — create or upsert a session (full messages + chart data)
GET  /nlq/sessions/{session_id}  — load full session by UUID  (for ?session= links)
GET  /nlq/sessions               — list sessions for a user_id (titles only)
DELETE /nlq/sessions/{session_id} — delete a session
"""

import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_conn

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class SaveSessionRequest(BaseModel):
    sessionId: Optional[str] = None   # if given → upsert; else → create new
    userId: Optional[str] = None
    title: Optional[str] = None
    messages: list[dict[str, Any]] = []


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/nlq/sessions")
def save_session(body: SaveSessionRequest):
    """
    Create or update an NLQ chat session.
    Stores the full messages array including SQL, chart data, and query results
    so sessions can be restored without any re-fetching.
    Returns session_id and a shareable URL param.
    """
    session_id = body.sessionId or str(uuid.uuid4())

    # Auto-generate title from first user message if not provided
    title = body.title
    if not title:
        first_user = next(
            (m for m in body.messages if m.get("role") == "user" and m.get("question")),
            None,
        )
        title = (first_user["question"][:80] if first_user else "New Chat")

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO internal.nlq_session (id, user_id, title, messages)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
                SET messages   = EXCLUDED.messages,
                    title      = EXCLUDED.title,
                    updated_at = NOW()
            """,
            (session_id, body.userId, title, json.dumps(body.messages)),
        )
        conn.commit()

    return {"session_id": session_id, "share_url_param": f"?session={session_id}"}


@router.get("/nlq/sessions/{session_id}")
def load_session(session_id: str):
    """
    Load a full session by UUID — used when opening a shared ?session= link.
    Returns all messages with their original SQL, chart data, and results.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, title, messages, created_at, updated_at
            FROM internal.nlq_session WHERE id = %s
            """,
            (session_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    id_, user_id, title, messages_json, created_at, updated_at = row
    messages = messages_json if isinstance(messages_json, list) else json.loads(messages_json or "[]")

    return {
        "session_id": str(id_),
        "userId":     user_id,
        "title":      title,
        "messages":   messages,
        "createdAt":  created_at.isoformat() if created_at else None,
        "updatedAt":  (updated_at or created_at).isoformat() if (updated_at or created_at) else None,
    }


@router.get("/nlq/sessions")
def list_sessions(user_id: str = Query(..., description="User identifier")):
    """
    List all sessions for a user (titles + metadata only, no full message data).
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, title, created_at, updated_at,
                   jsonb_array_length(messages) AS message_count
            FROM internal.nlq_session
            WHERE user_id = %s
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT 50
            """,
            (user_id,),
        )
        rows = cur.fetchall()

    return [
        {
            "session_id":    str(r[0]),
            "userId":        r[1],
            "title":         r[2],
            "createdAt":     r[3].isoformat() if r[3] else None,
            "updatedAt":     (r[4] or r[3]).isoformat() if (r[4] or r[3]) else None,
            "messageCount":  r[5] or 0,
        }
        for r in rows
    ]


@router.delete("/nlq/sessions/{session_id}")
def delete_session(session_id: str):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM internal.nlq_session WHERE id = %s", (session_id,))
        conn.commit()
    return {"deleted": session_id}
