"""
Pydantic request models for the NLQ API.
"""

from typing import Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural language analytics question",
        examples=["Show monthly output per channel"],
    )
    session_id: str = Field(
        default="default",
        description="Session identifier for conversational context",
        examples=["abc123"],
    )
    explore: bool = Field(
        default=False,
        description="When true, runs LIDA for additional insight visualizations",
    )
    user_role: Optional[str] = Field(
        default=None,
        description="User role key: founder | client_success | operations | editorial | tech",
        examples=["founder"],
    )
