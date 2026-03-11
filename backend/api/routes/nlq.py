"""
NLQ route — natural language → SQL → results.
"""

from fastapi import APIRouter
from pydantic import BaseModel
from api.deps import get_conn
from intelligence.nlq.sql_rag import run_nlq_query

router = APIRouter()


class NLQRequest(BaseModel):
    question: str
    client_id: int = 1


@router.post("/nlq/query")
def nlq_query(body: NLQRequest):
    """
    Convert a natural language question to SQL, execute it, return results + chart spec.
    """
    with get_conn() as conn:
        result = run_nlq_query(body.question, body.client_id, conn)
    return result
