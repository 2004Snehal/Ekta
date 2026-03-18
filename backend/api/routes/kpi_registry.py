"""
KPI Registry routes — manual KPI creation, AI agent KPI creation,
registry CRUD, and expandable detail page generation agent.

Endpoints (all under /kpi-lab prefix):

  GET    /kpi-lab/functions               - list formula builder functions
  GET    /kpi-lab/registry                - list all saved KPIs
  POST   /kpi-lab/registry                - save a discovered KPI to registry
  GET    /kpi-lab/registry/{kpi_id}       - get KPI + execute expand page queries live
  DELETE /kpi-lab/registry/{kpi_id}       - delete KPI
  POST   /kpi-lab/kpi/manual              - formula builder → SQL via LLM → execute → save
  POST   /kpi-lab/kpi/agent-create        - AI agent generates KPIs from business context
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from api.deps import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kpi-lab", tags=["KPI Registry"])

# ================================================================== #
# LLM helpers — reuse main backend config (Gemini / OpenAI)
# ================================================================== #

_BACKEND_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def _load_llm_config():
    from backend_config import LLM_PROVIDER, LLM_MODEL, GOOGLE_API_KEY, OPENAI_API_KEY  # noqa: PLC0415
    return LLM_PROVIDER, LLM_MODEL, GOOGLE_API_KEY, OPENAI_API_KEY


def _call_llm_json(system_prompt: str, user_message: str) -> dict:
    """Call the configured LLM and return a parsed JSON dict."""
    provider, model, google_key, openai_key = _load_llm_config()
    if provider == "gemini":
        import google.genai as genai  # noqa: PLC0415
        if not google_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        client = genai.Client(api_key=google_key)
        resp = client.models.generate_content(
            model=model,
            contents=user_message,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
            },
        )
        return json.loads(resp.text)
    else:
        from openai import OpenAI  # noqa: PLC0415
        if not openai_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        client = OpenAI(api_key=openai_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)


# ================================================================== #
# Formula builder functions catalogue
# ================================================================== #

KPI_FUNCTIONS: List[Dict[str, str]] = [
    {
        "name": "COUNT",
        "signature": "COUNT(column)",
        "description": "Count non-null values in a column",
        "example": "COUNT(video_id)",
        "category": "aggregation",
    },
    {
        "name": "COUNT_DISTINCT",
        "signature": "COUNT_DISTINCT(column)",
        "description": "Count unique (distinct) values in a column",
        "example": "COUNT_DISTINCT(video_id)",
        "category": "aggregation",
    },
    {
        "name": "SUM",
        "signature": "SUM(column)",
        "description": "Sum of all values",
        "example": "SUM(duration_seconds)",
        "category": "aggregation",
    },
    {
        "name": "AVG",
        "signature": "AVG(column)",
        "description": "Average of all values",
        "example": "AVG(duration_seconds)",
        "category": "aggregation",
    },
    {
        "name": "MAX",
        "signature": "MAX(column)",
        "description": "Maximum value",
        "example": "MAX(duration_seconds)",
        "category": "aggregation",
    },
    {
        "name": "MIN",
        "signature": "MIN(column)",
        "description": "Minimum value",
        "example": "MIN(duration_seconds)",
        "category": "aggregation",
    },
    {
        "name": "RATIO",
        "signature": "RATIO(numerator_expr, denominator_expr)",
        "description": "Safe ratio as percentage: (A / B) × 100, NULL-safe",
        "example": "RATIO(COUNT(published_videos), COUNT(uploaded_videos))",
        "category": "derived",
    },
    {
        "name": "GROWTH",
        "signature": "GROWTH(current_expr, previous_expr)",
        "description": "Period-over-period growth %: ((current − previous) / previous) × 100",
        "example": "GROWTH(COUNT_DISTINCT(video_id, current_30d), COUNT_DISTINCT(video_id, prev_30d))",
        "category": "derived",
    },
    {
        "name": "CURRENT_PERIOD",
        "signature": "CURRENT_PERIOD(expr, days=30)",
        "description": "Filter expression to the most recent N days",
        "example": "CURRENT_PERIOD(COUNT(video_id), 30)",
        "category": "temporal",
    },
    {
        "name": "PREVIOUS_PERIOD",
        "signature": "PREVIOUS_PERIOD(expr, days=30)",
        "description": "Filter expression to the N-day window before the current period",
        "example": "PREVIOUS_PERIOD(COUNT(video_id), 30)",
        "category": "temporal",
    },
    {
        "name": "FILTER",
        "signature": "FILTER(expr, condition)",
        "description": "Aggregate only rows matching the condition",
        "example": "FILTER(COUNT(video_id), is_published = true)",
        "category": "filter",
    },
    {
        "name": "RATE",
        "signature": "RATE(metric_expr, total_expr)",
        "description": "Metric as a percentage of total: (metric / total) × 100",
        "example": "RATE(COUNT_DISTINCT(published_id), COUNT_DISTINCT(video_id))",
        "category": "derived",
    },
]


# ================================================================== #
# Schema helper
# ================================================================== #

def _get_schema_summary() -> str:
    """
    Build a schema string for LLM prompts.
    Includes column types and one sample row per table so the LLM knows
    exact column names and realistic value shapes.
    Starts with an explicit allowlist of tables to prevent hallucination.
    """
    try:
        from api.routes.kpi_lab import get_pg_adapter  # noqa: PLC0415
        adapter = get_pg_adapter()
        raw = adapter.get_schema()
        table_names = list(raw.keys())

        header = (
            "AVAILABLE TABLES (use ONLY these, with the 'data.' prefix):\n"
            + ", ".join(f"data.{t}" for t in table_names)
            + "\n\nDETAILED SCHEMA:\n"
        )

        lines = []
        for table, cols in raw.items():
            col_str = ", ".join(
                f"{c['name']} ({c['type']})" for c in (cols[:25] if isinstance(cols, list) else [])
            )
            try:
                samples = adapter.sample_rows(table, n=1)
                sample_str = f"\n  sample row: {samples[0]}" if samples else ""
            except Exception:
                sample_str = ""
            lines.append(f"data.{table}:\n  columns: {col_str}{sample_str}")

        return header + "\n\n".join(lines) if lines else "Schema unavailable"
    except Exception as exc:
        logger.warning("schema summary failed: %s", exc)
        return "Schema unavailable"


# ================================================================== #
# DB helpers
# ================================================================== #

def _execute_scalar(sql: str) -> Any:
    """Execute SQL and return the first cell of the first row."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql)
            row = cur.fetchone()
            cur.close()
            conn.rollback()  # close implicit transaction so connection returns clean
            return row[0] if row else None
    except Exception as exc:
        logger.warning("scalar query failed: %s | sql: %.200s", exc, sql)
        return None


def _execute_rows(sql: str, limit: int = 500) -> List[Dict[str, Any]]:
    """Execute SQL and return list of row dicts."""
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(sql)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchmany(limit)]
            cur.close()
            conn.rollback()  # close implicit transaction so connection returns clean
            return rows
    except Exception as exc:
        logger.warning("rows query failed: %s | sql: %.200s", exc, sql)
        return []


# ================================================================== #
# Agent 1: Expandable page generator
# ================================================================== #

_EXPAND_SYSTEM = """\
You are a KPI analytics expert for a media analytics platform called Frammer.
Given a KPI definition and the ACTUAL database schema (provided in the user message), produce a JSON specification for its expandable detail page.

IMPORTANT: Use ONLY the tables and columns that appear in the "Available schema" section of the user message.
Do NOT assume or invent column names. Use the exact column names shown.
Database uses PostgreSQL with "data." schema prefix on all tables.

Return a JSON object with EXACTLY these keys:
{
  "interpretation": "2-3 sentences: what this KPI measures and why it matters to the business",
  "value_range": "Typical numeric range and scale, e.g. '0-100%, strong above 70%'",
  "high_value_means": "Business meaning of a high value",
  "low_value_means": "Business meaning of a low value",
  "chart_configs": [
    {
      "chart_type": "line",
      "title": "Chart title",
      "axes": {"x": {"field": "exact_column_name", "label": "Label"}, "y": {"field": "exact_column_name", "label": "Label"}},
      "sql": "SELECT exact_col AS exact_col, COUNT(*) AS exact_col FROM data.table ... valid PostgreSQL"
    }
  ],
  "stat_queries": [
    {"label": "Stat label", "sql": "SELECT single_value AS value FROM data.table ..."}
  ]
}

Rules for chart_configs (generate 2-3 charts — ONLY if meaningful data exists):
- Chart 1: time-series trend (chart_type=line) using the date/time column from the schema, ORDER BY date ASC
- Chart 2: breakdown by a secondary dimension column from the schema (chart_type=bar), LIMIT 10, ORDER BY value DESC
- Chart 3 (optional): another breakdown only if a third relevant dimension exists
- axes.x.field and axes.y.field must match EXACTLY the column aliases in the SELECT
- SQL must use "data." prefix, be valid PostgreSQL, and return at least one row

Rules for stat_queries (3-4 stats):
- Each returns ONE ROW with ONE COLUMN named "value"
- Typical stats: current-period total, previous-period total, all-time total, growth rate
- Use NULLIF to protect all divisions from zero
- Only include a stat if you are confident the SQL will return a non-null value
"""


def _generate_expand_page(kpi: Dict[str, Any]) -> Dict[str, Any]:
    """Call LLM to build the expandable detail page spec for a KPI."""
    schema_summary = _get_schema_summary()
    user_msg = (
        f"KPI Name: {kpi.get('name', '')}\n"
        f"Description: {kpi.get('description', '')}\n"
        f"Formula: {kpi.get('formula', '')}\n"
        f"SQL: {kpi.get('sql_expression', '')}\n"
        f"Columns used: {json.dumps(kpi.get('columns_used', []))}\n"
        f"Tables used: {json.dumps(kpi.get('tables_used', []))}\n"
        f"Current value: {kpi.get('current_value', 'unknown')}\n"
        f"Category: {kpi.get('category', '')}\n\n"
        f"Available schema:\n{schema_summary}"
    )
    try:
        return _call_llm_json(_EXPAND_SYSTEM, user_msg)
    except Exception as exc:
        logger.warning("expand page generation failed: %s", exc)
        return {
            "interpretation": kpi.get("description", ""),
            "value_range": "N/A",
            "high_value_means": "N/A",
            "low_value_means": "N/A",
            "chart_configs": [],
            "stat_queries": [],
        }


# ================================================================== #
# Agent 2: Formula → SQL converter
# ================================================================== #

_FORMULA_SQL_SYSTEM = """\
You are a PostgreSQL SQL expert for a media analytics platform (Frammer).
Convert a human-readable KPI formula into a single executable PostgreSQL query.

Database schema (use "data." prefix):
{schema}

Return a JSON object:
{{
  "sql": "SELECT ... AS value FROM data. ...",
  "columns_used": ["col1", "col2"],
  "tables_used": ["data.fact_created_videos", ...]
}}

Rules:
- SQL must return EXACTLY ONE ROW with ONE COLUMN named "value"
- Use NULLIF() to protect all divisions from zero
- The date/time column in data.fact_created_videos is "uploaded_at" (TIMESTAMPTZ) — NOT "date"
- For period comparisons: WHERE uploaded_at >= CURRENT_DATE - INTERVAL 'N days'
- NEVER hardcode dimension values (e.g. platform names, channel names) — use aggregate over ALL rows
- For GROWTH formula — combine current and previous periods with CASE WHEN in a single query:
  SELECT
    ((COUNT(DISTINCT CASE WHEN uploaded_at >= CURRENT_DATE - INTERVAL '30 days' THEN video_id END)
    - COUNT(DISTINCT CASE WHEN uploaded_at >= CURRENT_DATE - INTERVAL '60 days'
                               AND uploaded_at < CURRENT_DATE - INTERVAL '30 days' THEN video_id END))
    / NULLIF(COUNT(DISTINCT CASE WHEN uploaded_at >= CURRENT_DATE - INTERVAL '60 days'
                                      AND uploaded_at < CURRENT_DATE - INTERVAL '30 days' THEN video_id END), 0)
    ) * 100 AS value
  FROM data.fact_created_videos
- For RATIO: (numerator_expr) / NULLIF(denominator_expr, 0) * 100 AS value
- published_flag is BOOLEAN (use published_flag = TRUE, not is_published)
- duration columns are: uploaded_duration_secs, created_duration_secs, published_duration_secs (INTEGER seconds)
"""


def _formula_to_sql(name: str, formula: str, columns: List[str]) -> Dict[str, Any]:
    schema_summary = _get_schema_summary()
    system = _FORMULA_SQL_SYSTEM.format(schema=schema_summary)
    user_msg = (
        f"KPI Name: {name}\n"
        f"Formula: {formula}\n"
        f"Columns selected by user: {json.dumps(columns)}\n\n"
        "Convert this formula to a single PostgreSQL query returning one scalar named 'value'."
    )
    try:
        return _call_llm_json(system, user_msg)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Formula-to-SQL conversion failed: {exc}")


# ================================================================== #
# Agent 3: Context → KPIs
# ================================================================== #

_AGENT_KPI_SYSTEM = """\
You are a KPI expert for a media analytics platform (Frammer) used by content operations teams.
Create meaningful, business-relevant KPIs from a context description.

Database schema (use "data." prefix):
{schema}

Return a JSON object with key "kpis" — an array where each element has:
{{
  "name": "Concise title-case KPI name",
  "description": "One sentence — what it measures",
  "formula": "Human-readable formula using function names: GROWTH(), RATIO(), COUNT_DISTINCT(), CURRENT_PERIOD(), etc.",
  "sql_expression": "PostgreSQL query returning ONE ROW with column 'value'",
  "columns_used": ["col1", "col2"],
  "tables_used": ["data.table1"],
  "category": "growth | quality | efficiency | engagement | volume",
  "unit": "% | count | ratio | seconds"
}}

Rules:
- Generate 3-6 KPIs relevant to the context
- Prefer complex multi-step formulas: growth rates, period-over-period comparisons, ratios
- All SQL uses "data." prefix and returns EXACTLY ONE row with column named "value"
- Use NULLIF to protect all divisions; CASE WHEN for period filters
- Vary categories: do not generate all KPIs of the same type
- The date/time column in data.fact_created_videos is "uploaded_at" (TIMESTAMPTZ) — NOT "date"
- NEVER hardcode dimension values (platform names, channel names, user names, etc.)
  Always aggregate across ALL rows — filters by dimension value will return NULL if that value doesn't exist
- published_flag is BOOLEAN (use published_flag = TRUE, not is_published or published = 'yes')
- duration columns are: uploaded_duration_secs, created_duration_secs, published_duration_secs (INTEGER seconds)
- Only use columns that actually appear in the schema provided above
"""


# ================================================================== #
# Pydantic request models
# ================================================================== #

class SaveKPIRequest(BaseModel):
    name: str
    description: Optional[str] = None
    formula: Optional[str] = None
    sql_expression: Optional[str] = None
    columns_used: List[str] = []
    tables_used: List[str] = []
    category: Optional[str] = None
    current_value: Optional[Any] = None
    unit: Optional[str] = None
    usefulness_score: Optional[float] = None
    source: str = "manual"


class ManualKPIRequest(BaseModel):
    name: str
    description: Optional[str] = None
    formula: str
    columns_used: List[str] = []
    category: Optional[str] = None
    unit: Optional[str] = None


class AgentKPIRequest(BaseModel):
    context: str
    tables: Optional[List[str]] = None


# ================================================================== #
# Serialisation helpers
# ================================================================== #

def _parse_jsonb(val: Any) -> Any:
    if val is None:
        return val
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return val


def _row_to_dict(row, cols: List[str]) -> Dict[str, Any]:
    kpi = dict(zip(cols, row))
    kpi["id"] = str(kpi["id"])
    if kpi.get("created_at"):
        kpi["created_at"] = kpi["created_at"].isoformat()
    if kpi.get("updated_at"):
        kpi["updated_at"] = kpi["updated_at"].isoformat()
    for field in ("columns_used", "tables_used", "current_value"):
        kpi[field] = _parse_jsonb(kpi.get(field))
    return kpi


def _fmt_value(val: Any) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:,.2f}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


# ================================================================== #
# Endpoints
# ================================================================== #

@router.get("/functions")
def list_functions():
    """Return the formula builder function catalogue."""
    return {"functions": KPI_FUNCTIONS}


# ── Registry CRUD ─────────────────────────────────────────────────

@router.get("/registry")
def list_registry():
    """List all KPIs saved in the registry."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, description, formula, columns_used, tables_used,
                   category, current_value, unit, usefulness_score, source,
                   (expand_page IS NOT NULL) AS has_expand,
                   created_at
            FROM internal.kpi_registry
            ORDER BY created_at DESC
            """
        )
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        cur.close()
        conn.rollback()
    return {"kpis": [_row_to_dict(r, cols) for r in rows]}


def _update_expand_page_bg(kpi_id: str, kpi_dict: Dict[str, Any]) -> None:
    """Background task: generate expand page via LLM and write it to the registry row."""
    try:
        expand_page = _generate_expand_page(kpi_dict)
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE internal.kpi_registry SET expand_page = %s, updated_at = NOW() WHERE id = %s",
                (json.dumps(expand_page), kpi_id),
            )
            conn.commit()
            cur.close()
        logger.info("expand page generated for kpi %s", kpi_id)
    except Exception as exc:
        logger.warning("expand page background update failed for %s: %s", kpi_id, exc)


@router.post("/registry")
def save_to_registry(req: SaveKPIRequest, background_tasks: BackgroundTasks):
    """
    Save a KPI to the registry (e.g. from the auto-discovery results).
    The DB row is written immediately; the LLM expand-page is generated in the background.
    """
    kpi_id = str(uuid.uuid4())

    current_value = req.current_value
    if current_value is None and req.sql_expression:
        current_value = _execute_scalar(req.sql_expression)

    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO internal.kpi_registry
              (id, name, description, formula, sql_expression, columns_used, tables_used,
               category, current_value, unit, usefulness_score, source, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
            ON CONFLICT (name) DO UPDATE SET
              description      = EXCLUDED.description,
              formula          = EXCLUDED.formula,
              sql_expression   = EXCLUDED.sql_expression,
              columns_used     = EXCLUDED.columns_used,
              tables_used      = EXCLUDED.tables_used,
              category         = EXCLUDED.category,
              current_value    = EXCLUDED.current_value,
              unit             = EXCLUDED.unit,
              usefulness_score = EXCLUDED.usefulness_score,
              source           = EXCLUDED.source,
              updated_at       = NOW()
            RETURNING id
            """,
            (
                kpi_id, req.name, req.description, req.formula, req.sql_expression,
                json.dumps(req.columns_used), json.dumps(req.tables_used),
                req.category, json.dumps(current_value), req.unit,
                req.usefulness_score, req.source,
            ),
        )
        returned_id = str(cur.fetchone()[0])
        conn.commit()
        cur.close()

    # Generate expand page asynchronously so the save responds immediately
    kpi_dict = req.model_dump()
    kpi_dict["id"] = returned_id
    kpi_dict["current_value"] = current_value
    background_tasks.add_task(_update_expand_page_bg, returned_id, kpi_dict)

    return {
        "id": returned_id,
        "message": "KPI saved to registry",
        "has_expand_page": False,
    }


@router.get("/registry/{kpi_id}")
def get_registry_kpi(kpi_id: str):
    """
    Fetch a KPI and execute its cached expand-page SQL queries live
    so charts and stats always reflect the latest data.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, description, formula, sql_expression, columns_used, tables_used,
                   category, current_value, unit, usefulness_score, source, expand_page, created_at
            FROM internal.kpi_registry WHERE id = %s
            """,
            (kpi_id,),
        )
        row = cur.fetchone()
        cols = [d[0] for d in cur.description]
        cur.close()

    if not row:
        raise HTTPException(status_code=404, detail="KPI not found")

    kpi = _row_to_dict(row, cols)
    expand_raw = _parse_jsonb(kpi.pop("expand_page", None)) or {}

    # Execute stat queries — skip ones that return no value
    stats = []
    for sq in expand_raw.get("stat_queries", []):
        sql = sq.get("sql", "")
        if not sql:
            continue
        val = _execute_scalar(sql)
        if val is None:
            logger.debug("stat '%s' returned NULL — skipped", sq.get("label"))
            continue
        stats.append({"label": sq.get("label", ""), "value": _fmt_value(val)})

    # Execute chart queries — skip ones that return no rows
    charts = []
    for cc in expand_raw.get("chart_configs", []):
        sql = cc.get("sql", "")
        if not sql:
            continue
        data = _execute_rows(sql)
        if not data:
            logger.debug("chart '%s' returned no rows — skipped", cc.get("title"))
            continue
        chart: Dict[str, Any] = {
            "chart_type": cc.get("chart_type", "bar"),
            "title": cc.get("title", ""),
            "data": data,
        }
        if cc.get("axes"):
            chart["axes"] = cc["axes"]
        if cc.get("chart_type") == "pie":
            chart["category"] = cc.get("category", "label")
            chart["value"] = cc.get("value", "value")
        charts.append(chart)

    kpi["expand_detail"] = {
        "interpretation": expand_raw.get("interpretation", ""),
        "value_range": expand_raw.get("value_range", ""),
        "high_value_means": expand_raw.get("high_value_means", ""),
        "low_value_means": expand_raw.get("low_value_means", ""),
        "stats": stats,
        "charts": charts,
    }

    return kpi


@router.delete("/registry/{kpi_id}")
def delete_registry_kpi(kpi_id: str):
    """Remove a KPI from the registry."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM internal.kpi_registry WHERE id = %s RETURNING id", (kpi_id,))
        deleted = cur.fetchone()
        conn.commit()
        cur.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="KPI not found")
    return {"message": "KPI deleted"}


# ── Manual KPI creation ───────────────────────────────────────────

@router.post("/kpi/manual")
def create_manual_kpi(req: ManualKPIRequest):
    """
    Formula builder → SQL (via LLM) → execute → generate expand page → save to registry.
    """
    sql_result = _formula_to_sql(req.name, req.formula, req.columns_used)
    sql = sql_result.get("sql", "")
    columns = sql_result.get("columns_used", req.columns_used)
    tables = sql_result.get("tables_used", [])

    if not sql:
        raise HTTPException(status_code=422, detail="Could not convert formula to SQL. Check your formula and column names.")

    current_value = _execute_scalar(sql)
    if current_value is None:
        raise HTTPException(
            status_code=422,
            detail=f"The generated SQL returned no value (NULL or error). SQL was:\n\n{sql}\n\nCheck that the columns and table names are correct.",
        )

    kpi_dict: Dict[str, Any] = {
        "name": req.name,
        "description": req.description,
        "formula": req.formula,
        "sql_expression": sql,
        "columns_used": columns,
        "tables_used": tables,
        "category": req.category,
        "current_value": current_value,
        "unit": req.unit,
    }
    expand_page = _generate_expand_page(kpi_dict)

    kpi_id = str(uuid.uuid4())
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO internal.kpi_registry
              (id, name, description, formula, sql_expression, columns_used, tables_used,
               category, current_value, unit, source, expand_page, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'manual',%s,NOW())
            ON CONFLICT (name) DO UPDATE SET
              description    = EXCLUDED.description,
              formula        = EXCLUDED.formula,
              sql_expression = EXCLUDED.sql_expression,
              columns_used   = EXCLUDED.columns_used,
              tables_used    = EXCLUDED.tables_used,
              category       = EXCLUDED.category,
              current_value  = EXCLUDED.current_value,
              unit           = EXCLUDED.unit,
              expand_page    = EXCLUDED.expand_page,
              updated_at     = NOW()
            RETURNING id
            """,
            (
                kpi_id, req.name, req.description, req.formula, sql,
                json.dumps(columns), json.dumps(tables),
                req.category, json.dumps(current_value), req.unit,
                json.dumps(expand_page),
            ),
        )
        returned_id = str(cur.fetchone()[0])
        conn.commit()
        cur.close()

    return {
        "id": returned_id,
        "name": req.name,
        "sql": sql,
        "current_value": current_value,
        "unit": req.unit,
        "message": "KPI created and saved to registry",
    }


# ── Agent KPI creation ────────────────────────────────────────────

@router.post("/kpi/agent-create")
def agent_create_kpis(req: AgentKPIRequest):
    """
    AI agent generates multiple complex KPIs from a business context string.
    Each KPI is executed, has its expand page generated, and is saved to the registry.
    """
    schema_summary = _get_schema_summary()
    system = _AGENT_KPI_SYSTEM.format(schema=schema_summary)

    tables_hint = ""
    if req.tables:
        tables_hint = f"\n\nFocus primarily on these tables: {', '.join(req.tables)}"

    user_msg = (
        f"Business context: {req.context}{tables_hint}\n\n"
        "Generate meaningful complex KPIs for this context."
    )

    try:
        result = _call_llm_json(system, user_msg)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent KPI generation failed: {exc}")

    # LLM may return a bare list or a {"kpis": [...]} wrapper
    generated = result if isinstance(result, list) else result.get("kpis", [])
    saved: List[Dict[str, Any]] = []

    for kpi in generated:
        try:
            sql = kpi.get("sql_expression", "")
            if not sql:
                logger.warning("skipping agent KPI '%s': no SQL generated", kpi.get("name"))
                continue
            current_value = _execute_scalar(sql)
            if current_value is None:
                logger.warning(
                    "skipping agent KPI '%s': SQL returned no value. sql=%.200s",
                    kpi.get("name"), sql,
                )
                continue
            kpi["current_value"] = current_value

            expand_page = _generate_expand_page(kpi)

            kpi_id = str(uuid.uuid4())
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO internal.kpi_registry
                      (id, name, description, formula, sql_expression, columns_used, tables_used,
                       category, current_value, unit, source, expand_page, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'agent',%s,NOW())
                    ON CONFLICT (name) DO UPDATE SET
                      description    = EXCLUDED.description,
                      formula        = EXCLUDED.formula,
                      sql_expression = EXCLUDED.sql_expression,
                      columns_used   = EXCLUDED.columns_used,
                      tables_used    = EXCLUDED.tables_used,
                      category       = EXCLUDED.category,
                      current_value  = EXCLUDED.current_value,
                      unit           = EXCLUDED.unit,
                      source         = EXCLUDED.source,
                      expand_page    = EXCLUDED.expand_page,
                      updated_at     = NOW()
                    RETURNING id
                    """,
                    (
                        kpi_id,
                        kpi.get("name"), kpi.get("description"), kpi.get("formula"),
                        sql,
                        json.dumps(kpi.get("columns_used", [])),
                        json.dumps(kpi.get("tables_used", [])),
                        kpi.get("category"), json.dumps(current_value), kpi.get("unit"),
                        json.dumps(expand_page),
                    ),
                )
                returned_id = str(cur.fetchone()[0])
                conn.commit()
                cur.close()

            saved.append({
                "id": returned_id,
                "name": kpi.get("name"),
                "description": kpi.get("description"),
                "category": kpi.get("category"),
                "current_value": current_value,
                "unit": kpi.get("unit"),
                "formula": kpi.get("formula"),
            })
        except Exception as exc:
            logger.warning("failed to save agent KPI '%s': %s", kpi.get("name"), exc)

    return {
        "context": req.context,
        "kpis_created": len(saved),
        "kpis": saved,
    }
