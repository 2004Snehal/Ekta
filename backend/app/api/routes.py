"""
FastAPI route definitions.

Single endpoint: POST /query
Orchestrates the full NLQ pipeline:
  1. Retrieve session context (follow-up query support)
  2. Vanna RAG → SQL + chart metadata
  3. Self-healing SQL execution on PostgreSQL
  4. Optional LIDA insight generation
  5. LLM natural language answer
  6. Store Q→SQL pair in Vanna knowledge base
  7. Update session context
"""

import numbers as _numbers
import time

from fastapi import APIRouter, HTTPException, status

from app.models.request_models import QueryRequest
from app.models.response_models import QueryResponse
from app.services import (
    lida_service,
    session_service,
    sql_executor,
    vanna_service,
)
from app.services.llm_service import generate_answer
from app.utils.logger import get_logger

logger = get_logger("nlq.routes")

router = APIRouter()


def _flatten_rows(rows: list) -> list:
    """
    Serialize any nested dict/list values (e.g. jsonb columns) to JSON strings
    so the response is always a flat list of primitives the frontend can display.
    """
    import json as _json
    flat = []
    for row in rows:
        flat.append({
            k: (_json.dumps(v) if isinstance(v, (dict, list)) else v)
            for k, v in row.items()
        })
    return flat


def _fill_chart_meta(vr, rows: list, question: str) -> None:
    """Infer missing chart metadata from actual result rows when Vanna didn't supply it."""
    if not rows:
        if not vr.chart_type:
            vr.chart_type = "table"
        return

    first = rows[0]
    cols = list(first.keys())
    numeric_cols = [c for c in cols if isinstance(first.get(c), _numbers.Number)]
    text_cols = [c for c in cols if c not in numeric_cols]

    if not vr.x_column:
        vr.x_column = text_cols[0] if text_cols else (numeric_cols[0] if numeric_cols else None)
    if not vr.y_column:
        y_candidates = [c for c in numeric_cols if c != vr.x_column]
        vr.y_column = y_candidates[0] if y_candidates else (numeric_cols[0] if numeric_cols else None)

    if not vr.chart_type:
        if text_cols and numeric_cols:
            x_lower = (vr.x_column or "").lower()
            time_kws = ("month", "date", "year", "week", "day", "time", "period")
            if any(kw in x_lower for kw in time_kws):
                vr.chart_type = "line"
            elif len(rows) <= 8 and len(numeric_cols) == 1:
                vr.chart_type = "pie"
            else:
                vr.chart_type = "bar"
        else:
            vr.chart_type = "table"

    if not vr.title:
        vr.title = question[:80]


@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Natural Language Query",
    description="Convert a plain-English analytics question into SQL, execute it, and return a structured result with optional LIDA insights.",
)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    t_start = time.perf_counter()

    def _elapsed() -> float:
        return (time.perf_counter() - t_start) * 1000  # ms

    logger.info(
        "Received query | session=%s | explore=%s | role=%s | question='%s'",
        request.session_id,
        request.explore,
        request.user_role or "none",
        request.question,
    )

    # ── Step 1: Load session context ──────────────────────────────────────────
    t1 = time.perf_counter()
    session = session_service.get_session(request.session_id)
    previous_sql = session.last_sql  # None if first turn
    logger.info("[Step 1/6] Session loaded in %.0f ms (follow-up=%s)", (time.perf_counter() - t1) * 1000, previous_sql is not None)

    # ── Step 2: Vanna RAG → SQL + chart spec ─────────────────────────────────
    t2 = time.perf_counter()
    logger.info("[Step 2/6] Generating SQL via Vanna RAG…")
    try:
        vanna_result = vanna_service.generate_sql(
            question=request.question,
            previous_sql=previous_sql,
            user_role=request.user_role,
        )
    except Exception as exc:
        logger.error("Vanna SQL generation failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"SQL generation failed: {exc}",
        )
    logger.info("[Step 2/6] SQL generated in %.0f ms → %s", (time.perf_counter() - t2) * 1000, vanna_result.sql[:120].replace("\n", " "))

    # ── Step 3: Self-healing SQL execution ────────────────────────────────────
    t3 = time.perf_counter()
    logger.info("[Step 3/6] Executing SQL on PostgreSQL…")
    try:
        final_sql, rows, df = sql_executor.execute(
            sql=vanna_result.sql,
            question=request.question,
        )
    except Exception as exc:
        logger.error("SQL execution failed after retries: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"SQL execution failed: {exc}",
        )
    logger.info("[Step 3/6] SQL executed in %.0f ms → %d rows returned", (time.perf_counter() - t3) * 1000, len(rows))

    # Flatten any nested dicts/lists (e.g. jsonb columns) to strings so JSON serialisation never breaks
    rows = _flatten_rows(rows)

    # Fill any missing chart metadata from actual result data
    _fill_chart_meta(vanna_result, rows, request.question)

    # ── Step 4: Optional LIDA insights ───────────────────────────────────────
    insights = []
    if request.explore:
        t4 = time.perf_counter()
        logger.info("[Step 4/6] explore=true — invoking LIDA insight engine…")
        insights = lida_service.generate_insights(df=df, question=request.question, user_role=request.user_role)
        logger.info("[Step 4/6] LIDA generated %d insights in %.0f ms", len(insights), (time.perf_counter() - t4) * 1000)
    else:
        logger.info("[Step 4/6] Skipped LIDA (explore=false)")

    # ── Step 5: Natural language answer ──────────────────────────────────────
    t5 = time.perf_counter()
    logger.info("[Step 5/6] Generating natural language answer…")
    try:
        answer = generate_answer(
            question=request.question,
            sql=final_sql,
            data=rows,
            user_role=request.user_role,
        )
    except Exception as exc:
        logger.warning("LLM answer generation failed: %s — using fallback.", exc)
        answer = f"Query returned {len(rows)} rows."
    logger.info("[Step 5/6] Answer generated in %.0f ms", (time.perf_counter() - t5) * 1000)

    # ── Step 6: Store Q→SQL in Vanna knowledge base ───────────────────────────
    t6 = time.perf_counter()
    vanna_service.store_successful_query(
        question=request.question,
        sql=final_sql,
    )
    logger.info("[Step 6/6] Vanna KB updated in %.0f ms", (time.perf_counter() - t6) * 1000)

    # ── Step 7: Update session context ────────────────────────────────────────
    session_service.update_session(
        session_id=request.session_id,
        question=request.question,
        sql=final_sql,
    )

    total_ms = _elapsed()
    logger.info(
        "Query complete | session=%s | rows=%d | chart=%s | total=%.0f ms",
        request.session_id,
        len(rows),
        vanna_result.chart_type,
        total_ms,
    )

    columns = list(rows[0].keys()) if rows else []

    return QueryResponse(
        question=request.question,
        sql=final_sql,
        description=answer,
        chart_type=vanna_result.chart_type,
        x=vanna_result.x_column,
        y=vanna_result.y_column,
        title=vanna_result.title,
        data=rows,
        columns=columns,
        row_count=len(rows),
        insights=insights,
        processing_time_ms=round(total_ms, 1),
    )


@router.get("/health", summary="Health check")
async def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


@router.get("/roles", summary="Available user roles")
async def get_roles() -> dict:
    """Return all supported user roles with display names and suggested questions."""
    from app.services.role_config import get_all_roles
    return {"roles": get_all_roles()}
