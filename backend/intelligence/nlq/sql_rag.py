"""
SQL RAG core logic — Hybrid MetricFlow + direct SQL execution.

Flow:
  question
    → LLM (routing + query params)          [logged: LLM routing]
    → MetricFlow path: mf query --explain   [logged: MF compile]
      OR SQL path: validate raw SQL
    → execute SQL                           [logged: SQL execute]
    → generate_answer()                     [logged: Answer gen]
    → unified response                      [logged: Total time]
"""

import logging
import re
import time
from datetime import datetime

from intelligence.nlq.context import build_system_prompt
from intelligence.nlq.llm import call_llm, generate_answer

log = logging.getLogger("nlq")

REQUIRED_KEYS_MF  = {"path", "metrics", "group_by", "chart_type", "title", "x", "y"}
REQUIRED_KEYS_SQL = {"path", "sql", "chart_type", "title", "x", "y"}

_SEP = "─" * 52


def run_nlq_query(question: str, client_id: int, conn, profile: str = "operations") -> dict:
    """
    Execute an NLQ query end-to-end.
    Returns a dict ready to send as API response.

    ``profile`` is one of: "founder" | "client_success" | "operations" |
    "editorial" | "tech_product". It biases the system prompt toward the
    user's area of responsibility.
    """
    t_start = time.perf_counter()
    log.info(_SEP)
    log.info(f'[NLQ] ← "{question}"  (client={client_id}, profile={profile})')

    system_prompt = build_system_prompt(client_id, conn, profile=profile)

    # ── Step 1: LLM routing + query generation ────────────────────────────────
    t0 = time.perf_counter()
    try:
        llm_response = call_llm(system_prompt, question)
    except Exception as e:
        log.error(f"[NLQ] LLM call failed  ({time.perf_counter()-t0:.2f}s): {e}")
        return _error(str(e), question)

    path = llm_response.get("path", "sql")
    t1 = time.perf_counter()
    log.info(f"[NLQ] LLM routing    {t1-t0:>6.2f}s  → path={path}")

    # ── Step 2: Dispatch to execution path ────────────────────────────────────
    if path == "metricflow":
        result = _run_metricflow_path(question, client_id, llm_response, conn, t_start)
    else:
        result = _run_sql_path(question, client_id, llm_response, conn, t_start)

    total = time.perf_counter() - t_start
    log.info(f"[NLQ] Total          {total:>6.2f}s  → {result.get('row_count', 0)} rows")
    log.info(_SEP)

    result["query_time_ms"] = round(total * 1000)
    return result


# ── MetricFlow path ────────────────────────────────────────────────────────────

def _run_metricflow_path(
    question: str, client_id: int, llm_response: dict, conn, t_start: float
) -> dict:
    missing = REQUIRED_KEYS_MF - set(llm_response.keys())
    if missing:
        return _error(f"LLM response missing fields for MetricFlow path: {missing}", question)

    metrics  = llm_response["metrics"]
    group_by = llm_response["group_by"]
    log.info(f"[NLQ] MF params      metrics={metrics}  group_by={group_by}")

    from intelligence.nlq.metricflow_client import run_metricflow_query

    t0 = time.perf_counter()
    try:
        sql = run_metricflow_query(
            metrics=metrics,
            group_by=group_by,
            where=llm_response.get("where"),
            order_by=llm_response.get("order_by"),
            limit=llm_response.get("limit"),
            start_time=llm_response.get("start_time"),
            end_time=llm_response.get("end_time"),
        )
    except RuntimeError as e:
        log.warning(f"[NLQ] MF compile     {time.perf_counter()-t0:>6.2f}s  ✗ {e}")
        return _error(f"MetricFlow compilation failed — try rephrasing: {e}", question)

    log.info(f"[NLQ] MF compile     {time.perf_counter()-t0:>6.2f}s  ✓")

    return _execute_and_respond(
        question, client_id, sql, llm_response, conn, path="metricflow"
    )


# ── SQL path ───────────────────────────────────────────────────────────────────

def _run_sql_path(
    question: str, client_id: int, llm_response: dict, conn, t_start: float
) -> dict:
    missing = REQUIRED_KEYS_SQL - set(llm_response.keys())
    if missing:
        return _error(f"LLM response missing fields for SQL path: {missing}", question)

    sql = llm_response["sql"].strip()

    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        log.warning("[NLQ] SQL path       ✗ non-SELECT blocked")
        return _error("LLM generated a non-SELECT statement — blocked.", question)

    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 500"

    log.info("[NLQ] SQL path       raw SQL generated")
    return _execute_and_respond(
        question, client_id, sql, llm_response, conn, path="sql"
    )


# ── Shared execution ───────────────────────────────────────────────────────────

def _execute_and_respond(
    question: str,
    client_id: int,
    sql: str,
    llm_response: dict,
    conn,
    path: str,
) -> dict:
    # ── SQL execution ─────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        rows    = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        data    = _serialize([dict(zip(columns, row)) for row in rows])
        success = True
        error_msg = None
    except Exception as e:
        conn.rollback()
        success   = False
        error_msg = str(e)
        data      = []
        columns   = []

    t1 = time.perf_counter()
    if success:
        log.info(f"[NLQ] SQL execute    {t1-t0:>6.2f}s  → {len(data)} rows")
    else:
        log.warning(f"[NLQ] SQL execute    {t1-t0:>6.2f}s  ✗ {error_msg}")

    _log_query(conn, client_id, question, sql, success, len(data))

    if not success:
        return _error(f"SQL execution failed: {error_msg}", question)

    # ── Answer generation ─────────────────────────────────────────────────────
    t2 = time.perf_counter()
    answer = generate_answer(question, data)
    log.info(f"[NLQ] Answer gen     {time.perf_counter()-t2:>6.2f}s")

    return {
        "question":    question,
        "answer":      answer,
        "path":        path,
        "sql":         sql,
        "chart_type":  llm_response.get("chart_type", "table"),
        "title":       llm_response.get("title", ""),
        "x":           llm_response.get("x", columns[0] if columns else ""),
        "y":           llm_response.get("y", columns[1] if len(columns) > 1 else ""),
        "description": llm_response.get("description", ""),
        "data":        data,
        "columns":     columns,
        "row_count":   len(data),
    }


# ── helpers ────────────────────────────────────────────────────────────────────

def _serialize(data: list) -> list:
    """Convert dates/decimals to JSON-safe types."""
    import decimal
    result = []
    for row in data:
        clean = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                clean[k] = v.isoformat()
            elif hasattr(v, "date"):
                clean[k] = str(v)
            elif isinstance(v, decimal.Decimal):
                clean[k] = float(v)
            else:
                clean[k] = v
        result.append(clean)
    return result


def _log_query(
    conn, client_id: int, question: str, sql: str, success: bool, row_count: int
):
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
    log.warning(f"[NLQ] ERROR: {message}")
    return {
        "question":      question,
        "error":         message,
        "path":          "error",
        "sql":           None,
        "chart_type":    "table",
        "title":         "Error",
        "x":             "",
        "y":             "",
        "description":   "",
        "answer":        "",
        "data":          [],
        "columns":       [],
        "row_count":     0,
        "query_time_ms": 0,
    }
