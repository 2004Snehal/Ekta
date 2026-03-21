"""
POST /recommendations/contextual
"""

from fastapi import APIRouter, HTTPException

from api.deps import get_conn
from intelligence.recommendation.models import DashboardContext, RecommendationResponse
from intelligence.recommendation.engine import expand_only, get_recommendations

router = APIRouter()


@router.post("/recommendations/contextual", response_model=RecommendationResponse)
def contextual_recommendations(ctx: DashboardContext):
    """
    Accept a dashboard context payload describing what the user is currently
    viewing, expand it with 4 targeted SQL queries, and return 3–5
    cross-dimensional recommendations from the LLM.

    The DB connection is released after context expansion (fast) so it is NOT
    held during the slow LLM call — freeing the pool for other requests.
    """
    try:
        # Phase 1: cache check + SQL context expansion (fast, needs DB)
        with get_conn() as conn:
            result_or_expanded, was_cached = expand_only(ctx, conn)

        if was_cached:
            resp = result_or_expanded.model_copy()
            resp.cached = True
            return resp

        # Phase 2: LLM call + response build (slow, NO DB conn held)
        return get_recommendations(ctx, result_or_expanded)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
