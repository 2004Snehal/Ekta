
"""
NLQ route — natural language → SQL → results + optional LIDA insights.
"""

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
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


@router.post("/nlq/query")
def nlq_query(body: NLQRequest):
    with get_conn() as conn:
        result = run_nlq_query(
            question=body.question,
            client_id=body.client_id,
            conn=conn,
            session_id=body.session_id,
            explore=body.explore,
            user_role=body.user_role,
        )
    return result


@router.get("/nlq/roles")
def get_roles():
    """Return all supported user roles with display names and suggested questions."""
    from intelligence.nlq.role_config import get_all_roles
    return {"roles": get_all_roles()}
