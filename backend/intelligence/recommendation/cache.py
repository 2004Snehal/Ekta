"""
Simple in-memory TTL cache for recommendation responses.
No external dependencies — uses a plain dict + timestamps.
"""

import time
from intelligence.recommendation.models import DashboardContext, RecommendationResponse

TTL_SECONDS = 300  # 5 minutes

_cache: dict[str, tuple[float, RecommendationResponse]] = {}


def _key(ctx: DashboardContext) -> str:
    return (
        f"{ctx.client_id}:{ctx.entity_type}:{ctx.entity_id}"
        f":{ctx.metric_in_focus}:{ctx.time_range}:{ctx.view}"
    )


def get(ctx: DashboardContext) -> RecommendationResponse | None:
    k = _key(ctx)
    entry = _cache.get(k)
    if entry is None:
        return None
    stored_at, response = entry
    if time.time() - stored_at > TTL_SECONDS:
        del _cache[k]
        return None
    return response


def set(ctx: DashboardContext, response: RecommendationResponse) -> None:
    _cache[_key(ctx)] = (time.time(), response)


def clear() -> None:
    _cache.clear()
