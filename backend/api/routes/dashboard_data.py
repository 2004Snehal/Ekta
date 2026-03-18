"""
Unified dashboard data endpoint.

GET /dashboard?user_id=&date_range=&client_id=

Returns DashboardDatasetResponse — the flat record array the frontend caches
locally and applies narrower filters against without re-fetching the backend.

DashboardRecord shape (matches frontend types/dashboard.ts):
  date, client, channel, user, language, type, platform,
  workflow, publisher, content_bucket, status,
  uploadedVideos, processedVideos, publishedVideos,
  promotedVideos, engagement, avgDurationSeconds
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query

from api.deps import get_conn

router = APIRouter()

_RANGE_DAYS: dict[str, Optional[int]] = {
    "last-7-days":  7,
    "last-30-days": 30,
    "last-90-days": 90,
    "all-time":     None,
}

_DIM_LABELS = {
    "client":         "Client",
    "channel":        "Channel",
    "user":           "User",
    "language":       "Language",
    "type":           "Type",
    "platform":       "Platform",
    "workflow":       "Workflow",
    "publisher":      "Publisher",
    "content_bucket": "Content Bucket",
    "status":         "Status",
}

_SQL = """
    SELECT
        uploaded_at::date                                                          AS date,
        client_id::text                                                            AS client,
        COALESCE(channel,            'unknown')                                   AS channel,
        COALESCE(uploaded_by,        'unknown')                                   AS "user",
        COALESCE(language,           'unknown')                                   AS language,
        COALESCE(type,               'unknown')                                   AS type,
        COALESCE(published_platform, 'none')                                      AS platform,
        COALESCE(output_type,        'unknown')                                   AS workflow,
        'Manual'                                                                  AS publisher,
        'uncategorized'                                                           AS content_bucket,
        CASE WHEN LOWER(published) = 'yes'
             THEN 'published' ELSE 'processed' END                               AS status,

        -- metrics (aggregated per date+dimension row)
        COUNT(DISTINCT video_id)                                                  AS uploaded_videos,
        COUNT(*)                                                                  AS processed_videos,
        COUNT(*) FILTER (WHERE LOWER(published) = 'yes')                        AS published_videos,
        COUNT(*) FILTER (WHERE LOWER(published) = 'yes')                        AS promoted_videos,
        0                                                                         AS engagement,
        COALESCE(ROUND(AVG(uploaded_hours * 3600)::numeric, 0), 0)             AS avg_duration_seconds

    FROM  data.shortened_filtered_data

    WHERE client_id = %s
      AND uploaded_at::date >= %s

    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11
    ORDER BY 1 DESC
    LIMIT 100000
"""


@router.get("/dashboard")
def get_dashboard_data(
    user_id: str = Query("demo-user"),
    date_range: str = Query("last-90-days"),
    client_id: int = Query(1),
):
    """
    Return a DashboardDatasetResponse the frontend caches and filters client-side.
    Narrower ranges (7d, 30d) can reuse a cached 90-day dataset without re-fetching.
    """
    days = _RANGE_DAYS.get(date_range, 90)
    now = datetime.now(timezone.utc)
    start_date: date = (now - timedelta(days=days)).date() if days else date(2000, 1, 1)

    with get_conn() as conn:
        cur = conn.cursor()

        # Data window metadata
        cur.execute(
            "SELECT MIN(uploaded_at::date), MAX(uploaded_at::date) FROM data.shortened_filtered_data WHERE client_id = %s",
            (client_id,),
        )
        bounds = cur.fetchone()
        db_min: date = bounds[0] or start_date
        db_max: date = bounds[1] or now.date()

        effective_start: date = max(start_date, db_min) if days else db_min
        coverage_days = max((db_max - effective_start).days + 1, 0)

        # Main data query
        cur.execute(_SQL, (client_id, effective_start))
        cols = [d[0] for d in cur.description]
        raw_rows = cur.fetchall()

    records = []
    for row in raw_rows:
        r = dict(zip(cols, row))
        records.append({
            "date":               r["date"].isoformat() if hasattr(r["date"], "isoformat") else str(r["date"]),
            "client":             r["client"] or "",
            "channel":            r["channel"] or "",
            "user":               r["user"] or "",
            "language":           r["language"] or "",
            "type":               r["type"] or "",
            "platform":           r["platform"] or "",
            "workflow":           r["workflow"] or "",
            "publisher":          r["publisher"] or "",
            "content_bucket":     r["content_bucket"] or "",
            "status":             r["status"] or "",
            "uploadedVideos":     int(r["uploaded_videos"] or 0),
            "processedVideos":    int(r["processed_videos"] or 0),
            "publishedVideos":    int(r["published_videos"] or 0),
            "promotedVideos":     int(r["promoted_videos"] or 0),
            "engagement":         0,
            "avgDurationSeconds": int(r["avg_duration_seconds"] or 0),
        })

    filter_fields = _build_filter_fields(records)

    return {
        "user_id":        user_id,
        "requested_range": date_range,
        "data_window": {
            "start_date":    effective_start.isoformat(),
            "end_date":      db_max.isoformat() if hasattr(db_max, "isoformat") else str(db_max),
            "coverage_days": coverage_days,
        },
        "records":       records,
        "filter_fields": filter_fields,
    }


def _build_filter_fields(records: list[dict]) -> list[dict]:
    """Derive filter field definitions from the actual records returned."""
    skip_empty = {"unknown", "none", ""}
    fields = []
    for key, label in _DIM_LABELS.items():
        values = sorted({r[key] for r in records if r.get(key) and r[key] not in skip_empty})
        if values:
            fields.append({"key": key, "label": label, "values": values})
    return fields
