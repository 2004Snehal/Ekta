
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
    profile: str = "operations"
    # "founder" | "client_success" | "operations" | "editorial" | "tech_product"


@router.post("/nlq/query")
def nlq_query(body: NLQRequest):
    """
    Convert a natural language question to SQL, execute it, return results + chart spec.
    The optional ``profile`` field biases the LLM toward the user's role.
    """
    with get_conn() as conn:
        result = run_nlq_query(body.question, body.client_id, conn, profile=body.profile)
    return result
