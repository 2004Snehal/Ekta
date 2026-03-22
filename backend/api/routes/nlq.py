
"""
NLQ route — natural language → SQL → results + optional LIDA insights.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter
from pydantic import BaseModel, Field
import json
from datetime import datetime
from api.deps import get_conn
from intelligence.nlq.sql_rag import run_nlq_query

router = APIRouter()


class NLQRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    client_id: int = 1
    session_id: str = Field(default="default", description="Session ID for multi-turn conversation context")
    explore: bool = Field(default=False, description="When true, runs LIDA for additional insight visualizations")
    user_role: Optional[str] = Field(
        default=None,
        description="Role key: founder | client_success | operations | editorial | tech_product",
    )
    user_id: Optional[str] = Field(default=None, description="User ID for session persistence")



import uuid

def save_chat_interaction(conn, session_id: str, user_id: str, question: str, result: Dict[str, Any]):
    """
    Persist the chat interaction to internal.nlq_session.
    Matches the frontend Message interface structure.
    """
    if not user_id:
        return

    # If session_id is "default", we can't save to a specific session yet unless we generated one.
    # But the caller (nlq_query) will handle generation.
    
    try:
        with conn.cursor() as cur:
            # 1. Fetch current session messages
            cur.execute("SELECT messages, title FROM internal.nlq_session WHERE id = %s", (session_id,))
            row = cur.fetchone()
            
            messages = []
            title = None
            
            if row:
                existing_msgs = row[0]
                title = row[1]
                if isinstance(existing_msgs, str):
                    messages = json.loads(existing_msgs)
                elif isinstance(existing_msgs, list):
                    messages = existing_msgs
            
            # If new session, set title
            if not title:
                title = question[:80] if len(question) > 80 else question

            # 2. Construct new messages matching frontend Message interface
            # User Message
            user_msg = {
                "id": str(uuid.uuid4()),
                "role": "user",
                "question": question,
                "ts": datetime.now().isoformat()
            }
            
            # Assistant Message
            # The result dict is exactly what NLQResult expects
            ai_msg = {
                "id": str(uuid.uuid4()),
                "role": "assistant",
                "result": result,
                "ts": datetime.now().isoformat()
            }
            
            messages.append(user_msg)
            messages.append(ai_msg)

            # 3. Upsert session
            cur.execute(
                """
                INSERT INTO internal.nlq_session (id, user_id, title, messages, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE
                SET messages = EXCLUDED.messages,
                    title = COALESCE(internal.nlq_session.title, EXCLUDED.title),
                    updated_at = NOW()
                """,
                (session_id, user_id, title, json.dumps(messages))
            )
            conn.commit()
    except Exception as e:
        print(f"Failed to save session interaction: {e}")


@router.post("/nlq/query")
def nlq_query(body: NLQRequest):
    with get_conn() as conn:
        # Determine effective session ID
        current_session_id = body.session_id
        if not current_session_id or current_session_id == "default":
            current_session_id = str(uuid.uuid4())

        result = run_nlq_query(
            question=body.question,
            client_id=body.client_id,
            conn=conn,
            session_id=current_session_id, # Use concrete ID
            explore=body.explore,
            user_role=body.user_role,
        )
        
        # Inject session_id into result so frontend knows it
        result["session_id"] = current_session_id
        
        # Save session automatically
        if body.user_id:
            save_chat_interaction(conn, current_session_id, body.user_id, body.question, result)

    return result


@router.get("/nlq/roles")
def get_roles():
    """Return all supported user roles with display names and suggested questions."""
    from intelligence.nlq.role_config import get_all_roles
    return {"roles": get_all_roles()}
