"""
POST /recommendations/contextual
"""

from fastapi import APIRouter, HTTPException

from api.deps import get_conn
from intelligence.recommendation.models import DashboardContext, RecommendationResponse
from intelligence.recommendation.engine import get_recommendations

router = APIRouter()


@router.post("/recommendations/contextual", response_model=RecommendationResponse)
def contextual_recommendations(ctx: DashboardContext):
    """
    Accept a dashboard context payload describing what the user is currently
    viewing, expand it with 4 targeted SQL queries, and return 3–5
    cross-dimensional recommendations from the LLM.

    Example payload:
    {
        "client_id": 1,
        "view": "channel_detail",
        "entity_type": "channel",
        "entity_id": 2,
        "entity_name": "CNN Hindi",
        "metric_in_focus": "publish_rate_pct",
        "current_value": 21.9,
        "time_range": null,
        "user_role": "ops_lead"
    }
    """
    try:
        with get_conn() as conn:
            return get_recommendations(ctx, conn)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
