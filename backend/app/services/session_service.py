"""
Session context memory (Step 7).

Simple in-memory store keyed by session_id.
Persists the last question and last SQL so follow-up questions can
reference and modify the previous query rather than starting from scratch.

For production scale, replace the in-memory dict with Redis.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional

from app.utils.logger import get_logger

logger = get_logger("nlq.session")


@dataclass
class SessionContext:
    session_id: str
    last_question: Optional[str] = None
    last_sql: Optional[str] = None


# In-memory store: session_id → SessionContext
_sessions: Dict[str, SessionContext] = {}


def get_session(session_id: str) -> SessionContext:
    """Return the session context for the given ID, creating it if absent."""
    if session_id not in _sessions:
        _sessions[session_id] = SessionContext(session_id=session_id)
        logger.debug("New session created: %s", session_id)
    return _sessions[session_id]


def update_session(session_id: str, question: str, sql: str) -> None:
    """Persist the latest question/SQL for a session after a successful query."""
    ctx = get_session(session_id)
    ctx.last_question = question
    ctx.last_sql = sql
    logger.debug(
        "Session %s updated: question='%s'",
        session_id,
        question[:80],
    )


def clear_session(session_id: str) -> None:
    """Remove all context for a session (e.g. on explicit reset)."""
    _sessions.pop(session_id, None)
    logger.info("Session %s cleared.", session_id)


def list_sessions() -> list:
    """Debug helper — returns all active session IDs."""
    return list(_sessions.keys())
