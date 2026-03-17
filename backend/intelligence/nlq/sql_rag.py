"""
NLQ pipeline orchestrator — full 7-step Vanna+LIDA flow.

Step 1: Load session context          (follow-up query support)
Step 2: Vanna RAG → SQL + chart spec + answer_strategy
Step 3: Self-healing SQL execution    (auto-corrects on failure)
Step 4: Optional LIDA insights        (explore=True only)
Step 5: Statistical pre-summarization + LLM answer narration
Step 6: Store verified Q→SQL in Vanna knowledge base
Step 7: Update session context
"""

import logging
import numbers as _numbers
import re
import time
from datetime import datetime

from intelligence.nlq.vanna_service import generate_sql, store_successful_query
from intelligence.nlq.self_healing import run_sql_with_healing
from intelligence.nlq.session_service import get_session, update_session
from intelligence.nlq.llm import build_summary, generate_answer

log = logging.getLogger("nlq")
_SEP = "─" * 52


def run_nlq_query(
    question: str,
    client_id: int,
    conn,
    session_id: str = "default",
    explore: bool = False,
    user_role: str = None,
    profile: str = None,          # kept for backwards-compat; maps to user_role if set
) -> dict:
    """
    Execute the full NLQ pipeline.
    Returns a structured dict ready to send as an API response.
    """
    # profile is the old arg name; user_role takes precedence
    effective_role = user_role or profile

    t_start = time.perf_counter()
    log.info(_SEP)
    log.info('[NLQ] ← "%s"  (client=%s, role=%s, explore=%s)', question, client_id, effective_role or "none", explore)

    def _ms():
        return round((time.perf_counter() - t_start) * 1000, 1)

    # ── Step 1: Load session context ──────────────────────────────────────────
    session = get_session(session_id)
    previous_sql = session.last_sql
    log.info("[1/7] Session loaded (follow-up=%s) — %.0f ms", previous_sql is not None, _ms())

    # ── Step 2: Vanna RAG → SQL + chart spec + answer_strategy ───────────────
    t2 = time.perf_counter()
    try:
        vr = generate_sql(
            question=question,
            previous_sql=previous_sql,
            user_role=effective_role,
            client_id=client_id,
        )
    except Exception as exc:
        log.error("[2/7] Vanna SQL generation failed (%.2fs): %s", time.perf_counter() - t2, exc)
        return _error(str(exc), question)
    log.info("[2/7] SQL generated — %.0f ms", _ms())

    sql = vr.sql.strip()

    # ── Security: only allow SELECT ───────────────────────────────────────────
    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        log.warning("[NLQ] Non-SELECT blocked")
        return _error("Generated a non-SELECT statement — blocked.", question)

    sql_upper = sql.upper()
    for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE", "GRANT", "REVOKE"):
        if forbidden in sql_upper:
            log.warning("[NLQ] %s statement blocked", forbidden)
            return _error(f"Generated SQL containing {forbidden} — blocked.", question)

    # Enforce client_id isolation on the fact table
    if "fact_created_videos" in sql.lower() and "client_id" not in sql.lower():
        log.warning("[NLQ] Missing client_id filter — injecting wrapper")
        sql = f"SELECT * FROM ({sql.rstrip(';')}) _nlq WHERE client_id = {int(client_id)}"

    if "LIMIT" not in sql_upper:
        sql = sql.rstrip(";") + " LIMIT 500"

    # ── Step 3: Self-healing SQL execution ────────────────────────────────────
    t3 = time.perf_counter()
    try:
        final_sql, rows = run_sql_with_healing(conn, sql, question)
    except Exception as exc:
        log.error("[3/7] SQL execution failed after retries (%.2fs): %s", time.perf_counter() - t3, exc)
        _log_query(conn, client_id, question, sql, success=False, row_count=0)
        return _error(f"SQL execution failed: {exc}", question)

    data = _serialize(rows)
    columns = list(data[0].keys()) if data else []
    log.info("[3/7] SQL executed — %d rows — %.0f ms", len(data), _ms())

    _log_query(conn, client_id, question, final_sql, success=True, row_count=len(data))

    # Fill any missing chart metadata from actual result shape
    _fill_chart_meta(vr, data, question)

    # ── Step 4: Optional LIDA insight generation ──────────────────────────────
    insights = []
    if explore:
        t4 = time.perf_counter()
        try:
            import pandas as pd
            from intelligence.nlq.lida_service import generate_insights
            df = pd.DataFrame(data)
            insights = generate_insights(df=df, question=question, user_role=effective_role)
            log.info("[4/7] LIDA generated %d insights — %.0f ms", len(insights), _ms())
        except Exception as exc:
            log.warning("[4/7] LIDA failed (non-fatal, %.2fs): %s", time.perf_counter() - t4, exc)
    else:
        log.info("[4/7] LIDA skipped (explore=False)")

    # ── Step 5: Statistical summary + LLM answer narration ───────────────────
    t5 = time.perf_counter()
    strategy = vr.answer_strategy or {"type": "detail_sample", "focus": []}
    x_col = vr.x_column or (columns[0] if columns else "")
    y_col = vr.y_column or (columns[1] if len(columns) > 1 else "")

    summary = build_summary(data, x_col, y_col, strategy)
    answer = generate_answer(question, summary, strategy.get("focus", []))
    log.info("[5/7] Answer generated (%.2fs) — %.0f ms", time.perf_counter() - t5, _ms())

    # ── Step 6: Store Q→SQL in Vanna knowledge base ───────────────────────────
    store_successful_query(question, final_sql)
    log.info("[6/7] Vanna KB updated — %.0f ms", _ms())

    # ── Step 7: Update session context ────────────────────────────────────────
    update_session(session_id, question, final_sql)
    total_ms = _ms()
    log.info("[7/7] Session updated — total %.0f ms", total_ms)
    log.info(_SEP)

    return {
        "question":           question,
        "answer":             answer,
        "sql":                final_sql,
        "chart_type":         vr.chart_type or "table",
        "title":              vr.title or "",
        "x":                  vr.x_column or "",
        "y":                  vr.y_column or "",
        "description":        answer,
        "data":               data,
        "columns":            columns,
        "row_count":          len(data),
        "insights":           insights,
        "processing_time_ms": total_ms,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fill_chart_meta(vr, rows: list, question: str) -> None:
    """Infer missing chart metadata from actual result columns."""
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
        candidates = [c for c in numeric_cols if c != vr.x_column]
        vr.y_column = candidates[0] if candidates else (numeric_cols[0] if numeric_cols else None)

    if not vr.chart_type:
        if text_cols and numeric_cols:
            x_lower = (vr.x_column or "").lower()
            time_kws = ("month", "date", "year", "week", "day", "time", "period")
            vr.chart_type = "line" if any(kw in x_lower for kw in time_kws) else (
                "pie" if len(rows) <= 8 and len(numeric_cols) == 1 else "bar"
            )
        else:
            vr.chart_type = "table"

    if not vr.title:
        vr.title = question[:80]


def _serialize(rows: list) -> list:
    """Coerce dates, decimals, and nested objects to JSON-safe types."""
    import decimal
    import json as _json
    result = []
    for row in rows:
        clean = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                clean[k] = v.isoformat()
            elif hasattr(v, "date") and callable(v.date):
                clean[k] = str(v)
            elif isinstance(v, decimal.Decimal):
                clean[k] = float(v)
            elif isinstance(v, (dict, list)):
                clean[k] = _json.dumps(v)
            else:
                clean[k] = v
        result.append(clean)
    return result


def _log_query(conn, client_id: int, question: str, sql: str, success: bool, row_count: int):
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO internal.query_log (natural_lang, generated_sql, success, row_count)
            VALUES (%s, %s, %s, %s)
            """,
            (question, sql, success, row_count),
        )
        conn.commit()
    except Exception:
        conn.rollback()


def _error(message: str, question: str) -> dict:
    log.warning("[NLQ] ERROR: %s", message)
    return {
        "question":           question,
        "error":              message,
        "answer":             "",
        "sql":                None,
        "chart_type":         "table",
        "title":              "Error",
        "x":                  "",
        "y":                  "",
        "description":        "",
        "data":               [],
        "columns":            [],
        "row_count":          0,
        "insights":           [],
        "processing_time_ms": 0.0,
    }
