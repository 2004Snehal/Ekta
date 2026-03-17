"""
Session context memory — enables multi-turn conversational queries.

In-memory dict keyed by session_id. Persists the last question and SQL
so follow-up questions can modify the previous query instead of starting
from scratch. Replace with Redis for multi-instance deployments.
"""

import logging
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("nlq.session")


@dataclass
class SessionContext:
    session_id: str
    last_question: Optional[str] = None
    last_sql: Optional[str] = None


_sessions: Dict[str, SessionContext] = {}


def get_session(session_id: str) -> SessionContext:
    """Return session context for the given ID, creating it if absent."""
    if session_id not in _sessions:
        _sessions[session_id] = SessionContext(session_id=session_id)
    return _sessions[session_id]


def update_session(session_id: str, question: str, sql: str) -> None:
    """Persist the latest question/SQL after a successful query."""
    ctx = get_session(session_id)
    ctx.last_question = question
    ctx.last_sql = sql
    logger.debug("Session %s updated: '%s'", session_id, question[:80])


def clear_session(session_id: str) -> None:
    _sessions.pop(session_id, None)


def list_sessions() -> list:
    return list(_sessions.keys())
