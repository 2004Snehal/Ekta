"""
Analytics aggregation endpoints — multi-dim, period-compare, funnel, data-quality, time-series.
"""

import decimal
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_conn

router = APIRouter(prefix="/analytics")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fetch(conn, sql: str, params: tuple = ()) -> list[dict]:
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _serialize_row(row: dict) -> dict:
    """Convert non-JSON-safe types (Decimal, datetime, date) to primitives."""
    clean = {}
    for k, v in row.items():
        if isinstance(v, decimal.Decimal):
            clean[k] = float(v)
        elif isinstance(v, (datetime, date)):
            clean[k] = v.isoformat()
        else:
            clean[k] = v
    return clean


def _serialize(rows: list[dict]) -> list[dict]:
    return [_serialize_row(r) for r in rows]


# ── Dimension mapping ─────────────────────────────────────────────────────────

# key -> (table, pk_column, label_column)
DIM_TABLES = {
    "channel":     ("data.dim_channel",            "channel_id",            "channel_name"),
    "user":        ("data.dim_user",               "user_id",               "user_name"),
    "language":    ("data.dim_language",            "language_id",           "language_name"),
    "input_type":  ("data.dim_input_type",          "input_type_id",         "type_name"),
    "output_type": ("data.dim_output_type",         "output_type_id",        "type_name"),
    "platform":    ("data.dim_published_platform",  "published_platform_id", "platform_name"),
}

# Foreign-key column on fact_created_videos for each dimension key
FACT_DIM_FK = {
    "channel":     "channel_id",
    "user":        "user_id",
    "language":    "language_id",
    "input_type":  "input_type_id",
    "output_type": "output_type_id",
    "platform":    "published_platform_id",
    "team":        "team_id",
}


# ── 1. Multi-dimension cross-tabulation ──────────────────────────────────────

class MultiDimRequest(BaseModel):
    client_id: int = 1
    dim1: str  # channel | user | language | input_type | output_type | platform
    dim2: Optional[str] = None
    metric: str = "count"  # count | duration | published_count | publish_rate
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    filters: Optional[dict] = None


@router.post("/multi-dim")
def multi_dim(req: MultiDimRequest):
    if req.dim1 not in DIM_TABLES:
        raise HTTPException(400, f"Unknown dim1: {req.dim1}")
    if req.dim2 and req.dim2 not in DIM_TABLES:
        raise HTTPException(400, f"Unknown dim2: {req.dim2}")

    d1_table, d1_fk, d1_name = DIM_TABLES[req.dim1]

    # Build JOIN / SELECT / GROUP clauses from validated DIM_TABLES values only
    joins = [f"JOIN {d1_table} d1 ON d1.{d1_fk} = f.{d1_fk}"]
    group_cols = [f"d1.{d1_name} AS dim1"]
    group_by = [f"d1.{d1_name}"]

    if req.dim2:
        d2_table, d2_fk, d2_name = DIM_TABLES[req.dim2]
        joins.append(f"JOIN {d2_table} d2 ON d2.{d2_fk} = f.{d2_fk}")
        group_cols.append(f"d2.{d2_name} AS dim2")
        group_by.append(f"d2.{d2_name}")

    wheres = ["f.client_id = %s"]
    params: list = [req.client_id]

    if req.date_from:
        wheres.append("f.uploaded_at >= %s")
        params.append(req.date_from)
    if req.date_to:
        wheres.append("f.uploaded_at < %s")
        params.append(req.date_to)

    # Filter by dimension label value — join only for dimensions in DIM_TABLES
    if req.filters:
        for fk, fv in req.filters.items():
            if fk in DIM_TABLES:
                ft, ffk, fname = DIM_TABLES[fk]
                fa = f"ff_{fk}"
                joins.append(f"JOIN {ft} {fa} ON {fa}.{ffk} = f.{ffk}")
                wheres.append(f"{fa}.{fname} = %s")
                params.append(fv)

    sql = f"""
        SELECT {', '.join(group_cols)},
               COUNT(*) AS count,
               COALESCE(SUM(f.created_duration_secs), 0) / 3600.0 AS duration_hrs,
               COUNT(*) FILTER (WHERE f.published_flag) AS published_count,
               ROUND(
                   COUNT(*) FILTER (WHERE f.published_flag)::numeric
                   / NULLIF(COUNT(*), 0) * 100, 1
               ) AS publish_rate
        FROM   data.fact_created_videos f
               {' '.join(joins)}
        WHERE  {' AND '.join(wheres)}
        GROUP  BY {', '.join(group_by)}
        ORDER  BY count DESC
    """

    with get_conn() as conn:
        rows = _serialize(_fetch(conn, sql, tuple(params)))

    # Aggregate totals
    dim1_totals: dict = {}
    dim2_totals: dict = {}
    grand_total: dict = {"count": 0, "duration_hrs": 0.0, "published_count": 0}

    for r in rows:
        d1v = r.get("dim1", "")
        if d1v not in dim1_totals:
            dim1_totals[d1v] = {"dim1": d1v, "count": 0, "duration_hrs": 0.0, "published_count": 0}
        dim1_totals[d1v]["count"] += r.get("count", 0)
        dim1_totals[d1v]["duration_hrs"] += r.get("duration_hrs", 0.0)
        dim1_totals[d1v]["published_count"] += r.get("published_count", 0)

        if req.dim2:
            d2v = r.get("dim2", "")
            if d2v not in dim2_totals:
                dim2_totals[d2v] = {"dim2": d2v, "count": 0, "duration_hrs": 0.0, "published_count": 0}
            dim2_totals[d2v]["count"] += r.get("count", 0)
            dim2_totals[d2v]["duration_hrs"] += r.get("duration_hrs", 0.0)
            dim2_totals[d2v]["published_count"] += r.get("published_count", 0)

        grand_total["count"] += r.get("count", 0)
        grand_total["duration_hrs"] += r.get("duration_hrs", 0.0)
        grand_total["published_count"] += r.get("published_count", 0)

    if grand_total["count"] > 0:
        grand_total["publish_rate"] = round(
            grand_total["published_count"] / grand_total["count"] * 100, 1
        )

    return {
        "dim1_key": req.dim1,
        "dim2_key": req.dim2,
        "rows": rows,
        "dim1_totals": list(dim1_totals.values()),
        "dim2_totals": list(dim2_totals.values()) if req.dim2 else [],
        "grand_total": grand_total,
    }


# ── 2. Period comparison ──────────────────────────────────────────────────────

@router.get("/period-compare")
def period_compare(
    client_id: int = 1,
    period: str = Query("month", description="week | month | quarter"),
    ref_date: Optional[str] = Query(None, alias="date", description="YYYY-MM or YYYY-Www"),
):
    today = date.today()

    if period == "week":
        if ref_date and "W" in ref_date:
            year = int(ref_date[:4])
            week = int(ref_date.split("W")[1])
            current_start = date.fromisocalendar(year, week, 1)
        else:
            current_start = today - timedelta(days=today.weekday())
        current_end = current_start + timedelta(days=7)
        prev_start = current_start - timedelta(days=7)
        prev_end = current_start
        current_label = current_start.strftime("%Y-W%V")
        prev_label = prev_start.strftime("%Y-W%V")

    elif period == "quarter":
        q = (today.month - 1) // 3          # 0-based quarter index
        current_start = date(today.year, q * 3 + 1, 1)
        if q == 0:
            prev_start = date(today.year - 1, 10, 1)
        else:
            prev_start = date(today.year, (q - 1) * 3 + 1, 1)
        current_end = date(today.year, (q + 1) * 3 + 1, 1) if q < 3 else date(today.year + 1, 1, 1)
        prev_end = current_start
        current_label = f"{today.year}-Q{q + 1}"
        prev_label = f"{prev_start.year}-Q{(prev_start.month - 1) // 3 + 1}"

    else:  # month (default)
        if ref_date and len(ref_date) >= 7:
            year, month = int(ref_date[:4]), int(ref_date[5:7])
        else:
            year, month = today.year, today.month
        current_start = date(year, month, 1)
        current_end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        prev_start = date(year - 1, 12, 1) if month == 1 else date(year, month - 1, 1)
        prev_end = current_start
        current_label = current_start.strftime("%Y-%m")
        prev_label = prev_start.strftime("%Y-%m")

    sql = """
        SELECT
            CASE
                WHEN f.uploaded_at >= %s AND f.uploaded_at < %s THEN 'current'
                WHEN f.uploaded_at >= %s AND f.uploaded_at < %s THEN 'previous'
            END AS period,
            COUNT(*) AS count,
            COALESCE(SUM(f.created_duration_secs), 0) / 3600.0 AS duration_hrs,
            COUNT(*) FILTER (WHERE f.published_flag) AS published,
            ROUND(
                COUNT(*) FILTER (WHERE f.published_flag)::numeric
                / NULLIF(COUNT(*), 0) * 100, 1
            ) AS publish_rate
        FROM data.fact_created_videos f
        WHERE f.client_id = %s
          AND f.uploaded_at >= %s AND f.uploaded_at < %s
        GROUP BY 1
    """
    params = (
        current_start, current_end,   # CASE WHEN current
        prev_start,    prev_end,       # CASE WHEN previous
        client_id,
        prev_start,    current_end,    # outer WHERE
    )

    with get_conn() as conn:
        rows = _serialize(_fetch(conn, sql, params))

    empty = {"count": 0, "duration_hrs": 0.0, "published": 0, "publish_rate": 0.0}
    current  = next((r for r in rows if r.get("period") == "current"),  dict(empty))
    previous = next((r for r in rows if r.get("period") == "previous"), dict(empty))

    def delta_pct(curr, prev):
        if prev == 0:
            return 100.0 if curr > 0 else 0.0
        return round((curr - prev) / prev * 100, 1)

    current["period"]  = current_label
    previous["period"] = prev_label

    return {
        "current":  current,
        "previous": previous,
        "deltas": {
            "count_pct":          delta_pct(current.get("count", 0),        previous.get("count", 0)),
            "duration_pct":       delta_pct(current.get("duration_hrs", 0), previous.get("duration_hrs", 0)),
            "published_pct":      delta_pct(current.get("published", 0),    previous.get("published", 0)),
            "publish_rate_delta": round(
                (current.get("publish_rate") or 0.0) - (previous.get("publish_rate") or 0.0), 1
            ),
        },
    }


# ── 3. Publishing funnel ──────────────────────────────────────────────────────

@router.get("/funnel")
def funnel(
    client_id: int = 1,
    group_by: str = Query("channel", description="channel | user | input_type | language"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    if group_by not in DIM_TABLES:
        raise HTTPException(400, f"Unknown group_by: {group_by}")

    dim_table, dim_fk, dim_name = DIM_TABLES[group_by]

    wheres = ["f.client_id = %s"]
    params: list = [client_id]
    if date_from:
        wheres.append("f.uploaded_at >= %s")
        params.append(date_from)
    if date_to:
        wheres.append("f.uploaded_at < %s")
        params.append(date_to)

    sql = f"""
        SELECT d.{dim_name} AS "group",
               COUNT(DISTINCT f.video_id) AS uploaded,
               COUNT(*) AS processed,
               COUNT(*) FILTER (WHERE f.published_flag) AS published,
               ROUND(COUNT(*)::numeric / NULLIF(COUNT(DISTINCT f.video_id), 0) * 100, 1) AS process_rate,
               ROUND(
                   COUNT(*) FILTER (WHERE f.published_flag)::numeric
                   / NULLIF(COUNT(*), 0) * 100, 1
               ) AS publish_rate
        FROM   data.fact_created_videos f
        JOIN   {dim_table} d ON d.{dim_fk} = f.{dim_fk}
        WHERE  {' AND '.join(wheres)}
        GROUP  BY d.{dim_name}
        ORDER  BY processed DESC
    """

    with get_conn() as conn:
        rows = _serialize(_fetch(conn, sql, tuple(params)))

    totals = {
        "uploaded":  sum(r.get("uploaded",  0) for r in rows),
        "processed": sum(r.get("processed", 0) for r in rows),
        "published": sum(r.get("published", 0) for r in rows),
    }
    totals["process_rate"] = round(totals["processed"] / max(totals["uploaded"], 1) * 100, 1)
    totals["publish_rate"] = round(totals["published"] / max(totals["processed"], 1) * 100, 1)

    return {"funnel": rows, "totals": totals}


# ── 4. Data quality ───────────────────────────────────────────────────────────

@router.get("/data-quality")
def data_quality(client_id: int = 1):
    sql = """
        SELECT
            COUNT(*) AS total_records,
            COUNT(*) FILTER (WHERE f.language_id IS NULL)          AS lang_null,
            COUNT(*) FILTER (WHERE f.published_platform_id IS NULL) AS platform_null,
            COUNT(*) FILTER (WHERE f.team_id IS NULL)              AS team_null,
            COUNT(*) FILTER (WHERE f.user_id IS NULL)              AS user_null,
            COUNT(*) FILTER (WHERE f.input_type_id IS NULL)        AS input_type_null,
            COUNT(*) FILTER (WHERE f.output_type_id IS NULL)       AS output_type_null,
            COUNT(*) FILTER (WHERE f.published_flag AND f.publish_url IS NULL) AS null_publish_url_on_published,
            COUNT(DISTINCT f.video_id) AS distinct_videos,
            COUNT(*) - COUNT(DISTINCT f.video_id) AS potential_duplicates
        FROM data.fact_created_videos f
        WHERE f.client_id = %s
    """

    with get_conn() as conn:
        rows = _serialize(_fetch(conn, sql, (client_id,)))

    if not rows:
        return {
            "total_records": 0,
            "missing_by_field": {},
            "null_publish_urls_on_published": 0,
            "duplicate_video_ids": 0,
        }

    r = rows[0]
    total = r.get("total_records", 0)

    fields = {
        "language":    r.get("lang_null",        0),
        "platform":    r.get("platform_null",    0),
        "team":        r.get("team_null",        0),
        "user":        r.get("user_null",        0),
        "input_type":  r.get("input_type_null",  0),
        "output_type": r.get("output_type_null", 0),
    }

    missing_by_field = {
        field: {"null_count": null_count, "pct": round(null_count / max(total, 1) * 100, 1)}
        for field, null_count in fields.items()
    }

    return {
        "total_records":                total,
        "missing_by_field":             missing_by_field,
        "null_publish_urls_on_published": r.get("null_publish_url_on_published", 0),
        "duplicate_video_ids":          r.get("potential_duplicates", 0),
        "distinct_videos":              r.get("distinct_videos", 0),
    }


# ── 5. Flexible time-series ───────────────────────────────────────────────────

@router.get("/time-series")
def time_series(
    client_id: int = 1,
    metric: str = Query("count", description="count | duration_hrs | published_count | publish_rate"),
    granularity: str = Query("month", description="day | week | month"),
    group_by: Optional[str] = Query(None, description="channel | user | input_type | language | platform"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    # Period truncation / label expressions — built from literals, not user input
    if granularity == "day":
        period_trunc = "f.uploaded_at::date"
        period_label = "TO_CHAR(f.uploaded_at::date, 'YYYY-MM-DD')"
    elif granularity == "week":
        period_trunc = "DATE_TRUNC('week', f.uploaded_at)::date"
        period_label = "TO_CHAR(DATE_TRUNC('week', f.uploaded_at), 'IYYY-\"W\"IW')"
    else:  # month
        period_trunc = "DATE_TRUNC('month', f.uploaded_at)::date"
        period_label = "TO_CHAR(DATE_TRUNC('month', f.uploaded_at), 'YYYY-MM')"

    wheres = ["f.client_id = %s"]
    params: list = [client_id]
    joins: list[str] = []

    if date_from:
        wheres.append("f.uploaded_at >= %s")
        params.append(date_from)
    if date_to:
        wheres.append("f.uploaded_at < %s")
        params.append(date_to)

    # Optional dimension grouping — validated against DIM_TABLES
    group_select = ""
    group_by_extra = ""
    if group_by and group_by in DIM_TABLES:
        dim_table, dim_fk, dim_name = DIM_TABLES[group_by]
        joins.append(f"JOIN {dim_table} gd ON gd.{dim_fk} = f.{dim_fk}")
        group_select = f", gd.{dim_name} AS group_name"
        group_by_extra = f", gd.{dim_name}"

    sql = f"""
        SELECT {period_label} AS period
               {group_select},
               COUNT(*) AS count,
               COALESCE(SUM(f.created_duration_secs), 0) / 3600.0 AS duration_hrs,
               COUNT(*) FILTER (WHERE f.published_flag) AS published_count,
               ROUND(
                   COUNT(*) FILTER (WHERE f.published_flag)::numeric
                   / NULLIF(COUNT(*), 0) * 100, 1
               ) AS publish_rate
        FROM   data.fact_created_videos f
               {' '.join(joins)}
        WHERE  {' AND '.join(wheres)}
        GROUP  BY {period_trunc}{group_by_extra}
        ORDER  BY {period_trunc}
    """

    with get_conn() as conn:
        rows = _serialize(_fetch(conn, sql, tuple(params)))

    # When grouped, pivot into period -> {group_name: metric_value}
    if group_by and group_by in DIM_TABLES:
        series: dict = {}
        for r in rows:
            period_val = r["period"]
            if period_val not in series:
                series[period_val] = {"period": period_val, "groups": {}}
            gname = r.get("group_name", "unknown")
            series[period_val]["groups"][gname] = r.get(metric, r.get("count", 0))
        return {"series": list(series.values())}

    return {"series": rows}
