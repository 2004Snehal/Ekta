"""
NLQ pipeline orchestrator — full 7-step RAG+LIDA flow.

Step 1: Load session context          (follow-up query support)
Step 2: ChromaDB RAG → SQL + chart spec + answer_strategy
Step 3: Self-healing SQL execution    (auto-corrects on failure)
Step 4: Optional LIDA insights        (explore=True only)
Step 5: Statistical pre-summarization + LLM answer narration
Step 6: Store verified Q→SQL in ChromaDB knowledge base
Step 7: Update session context
"""

import logging
import re
import time
from datetime import datetime

from intelligence.nlq.rag_service import generate_sql_candidates, store_successful_query, score_candidate
from intelligence.nlq.router import classify_complexity, n_candidates
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
) -> dict:
    """
    Execute the full NLQ pipeline.
    Returns a structured dict ready to send as an API response.
    """
    effective_role = user_role

    t_start = time.perf_counter()
    log.info(_SEP)
    log.info('[NLQ] ← "%s"  (client=%s, role=%s, explore=%s)', question, client_id, effective_role or "none", explore)

    def _ms():
        return round((time.perf_counter() - t_start) * 1000, 1)

    # ── Step 1: Load session context ──────────────────────────────────────────
    session = get_session(session_id)
    previous_sql = session.last_sql
    log.info("[1/7] Session loaded (follow-up=%s) — %.0f ms", previous_sql is not None, _ms())

    # ── Step 2: ChromaDB RAG → SQL candidates (complexity-aware) ─────────────
    complexity = classify_complexity(question)
    n = n_candidates(complexity, explore=explore)
    t2 = time.perf_counter()
    try:
        candidates = generate_sql_candidates(
            question=question,
            n=n,
            previous_sql=previous_sql,
            user_role=effective_role,
            client_id=client_id,
            conn=conn,
        )
    except Exception as exc:
        log.error("[2/7] RAG generation failed (%.2fs): %s", time.perf_counter() - t2, exc)
        return _error(str(exc), question)

    # Score and rank candidates — best structural match executes first
    if len(candidates) > 1:
        candidates.sort(key=lambda vr: score_candidate(vr, question), reverse=True)
        log.info("[2/7] %d candidates generated and ranked (complexity=%s) — %.0f ms",
                 len(candidates), complexity, _ms())
    else:
        log.info("[2/7] SQL generated (complexity=%s) — %.0f ms", complexity, _ms())

    vr = candidates[0]

    # ── Step 2a: Router — allow RAG to signal no-SQL path ────────────────────
    routing = vr.routing or {}
    requires_sql = routing.get("requires_sql")
    if requires_sql is False:
        direct_answer = routing.get("direct_answer") or "I cannot answer this from the analytics database."
        log.info("[NLQ] Router: requires_sql=False — returning direct answer only.")
        total_ms = _ms()
        log.info("[7/7] Session updated — total %.0f ms", total_ms)
        log.info(_SEP)
        return {
            "question":           question,
            "answer":             direct_answer,
            "sql":                None,
            "chart_type":         vr.chart_type or "table",
            "title":              vr.title or "",
            "x":                  vr.x_column or "",
            "y":                  vr.y_column or "",
            "description":        direct_answer,
            "data":               [],
            "columns":            [],
            "row_count":          0,
            "insights":           [],
            "thinking":           vr.thinking,
            "complexity":         complexity,
            "processing_time_ms": total_ms,
        }

    # ── Step 3: Secure + execute candidates (best-scored first, fallback to rest) ─
    t3 = time.perf_counter()
    final_sql, rows = None, None

    for i, candidate in enumerate(candidates):
        ok, err_msg, secured = _secure_sql(candidate.sql.strip(), client_id)
        if not ok:
            log.warning("[NLQ] Candidate %d/%d blocked: %s\n  SQL was: %s",
                        i + 1, len(candidates), err_msg, candidate.sql.strip()[:400])
            if i == len(candidates) - 1:
                return _error(err_msg, question)
            continue

        try:
            final_sql, rows = run_sql_with_healing(conn, secured, question)
            vr = candidate   # adopt metadata from the winning candidate
            log.info("[3/7] Candidate %d/%d succeeded — %d rows — %.0f ms",
                     i + 1, len(candidates), len(rows), _ms())
            break
        except Exception as exc:
            log.warning("[3/7] Candidate %d/%d failed: %s", i + 1, len(candidates), exc)
            conn.rollback()
            if i == len(candidates) - 1:
                log.error("[3/7] All candidates exhausted (%.2fs)", time.perf_counter() - t3)
                _log_query(conn, client_id, question, secured, success=False, row_count=0)
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
    answer = generate_answer(question, summary, strategy.get("focus", []), user_role=effective_role)
    log.info("[5/7] Answer generated (%.2fs) — %.0f ms", time.perf_counter() - t5, _ms())

    # ── Step 6: Store Q→SQL in ChromaDB knowledge base ───────────────────────
    store_successful_query(question, final_sql)
    log.info("[6/7] RAG KB updated — %.0f ms", _ms())

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
        "thinking":           vr.thinking,
        "complexity":         complexity,
        "processing_time_ms": total_ms,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _secure_sql(sql: str, client_id: int) -> tuple:
    """
    Validate and harden a SQL string.
    Returns (ok: bool, error_msg: str, secured_sql: str).
    """
    if not re.match(r"^\s*(WITH|SELECT)\b", sql, re.IGNORECASE):
        return False, "Generated a non-SELECT statement — blocked.", sql

    for forbidden in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER",
                      "TRUNCATE", "CREATE", "GRANT", "REVOKE"):
        if re.search(rf"\b{forbidden}\b", sql, re.IGNORECASE):
            return False, f"Generated SQL containing {forbidden} — blocked.", sql

    # Enforce client_id isolation on the raw fact table
    if "fact_created_videos" in sql.lower() and "client_id" not in sql.lower():
        sql = f"SELECT * FROM ({sql.rstrip(';')}) _nlq WHERE client_id = {int(client_id)}"

    # Cap row count
    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        sql = sql.rstrip(";") + " LIMIT 500"

    return True, "", sql


_ID_SUFFIXES = ("_id", "_key", "_code", "_num", "_number")


def _is_id_col(col: str) -> bool:
    """Return True if a column looks like an identifier rather than a metric."""
    c = col.lower()
    return c == "id" or any(c.endswith(s) for s in _ID_SUFFIXES)


def _fill_chart_meta(vr, rows: list, question: str) -> None:
    """Infer missing chart metadata from actual result columns."""
    if not rows:
        if not vr.chart_type:
            vr.chart_type = "table"
        return

    first = rows[0]
    cols = list(first.keys())

    # Metric columns: numeric but NOT identifiers
    metric_cols = [
        c for c in cols
        if isinstance(first.get(c), (int, float)) and not _is_id_col(c)
    ]
    text_cols = [c for c in cols if not isinstance(first.get(c), (int, float))]

    # Force table when no real metric column exists (only IDs or only text)
    if not metric_cols:
        vr.chart_type = "table"
        return

    if not vr.x_column:
        vr.x_column = text_cols[0] if text_cols else (metric_cols[0] if metric_cols else None)
    if not vr.y_column:
        candidates = [c for c in metric_cols if c != vr.x_column]
        vr.y_column = candidates[0] if candidates else (metric_cols[0] if metric_cols else None)

    def _best_chart_type(n_rows, n_metrics, x_lower):
        time_kws = ("month", "date", "year", "week", "day", "time", "period")
        if any(kw in x_lower for kw in time_kws):
            return "line"
        if n_metrics >= 3 and n_rows <= 10:
            return "radar"
        if n_rows <= 8 and n_metrics == 1:
            return "pie"
        if n_rows > 8 and n_metrics == 1:
            return "horizontal_bar"
        if n_rows > 8:
            return "horizontal_bar"
        return "bar"

    x_lower = (vr.x_column or "").lower()

    # Auto-suggest scatter when both x and y are numeric duration/views columns
    if not vr.chart_type and len(metric_cols) >= 2:
        dur_view_kws = ("duration", "views", "secs", "seconds", "hours", "mins")
        if sum(1 for c in metric_cols[:2] if any(kw in c.lower() for kw in dur_view_kws)) >= 2:
            vr.chart_type = "scatter"

    if not vr.chart_type:
        if text_cols and metric_cols:
            vr.chart_type = _best_chart_type(len(rows), len(metric_cols), x_lower)
        else:
            vr.chart_type = "table"
    else:
        # Validate / correct the LLM's choice against the actual data shape
        if not metric_cols:
            vr.chart_type = "table"
        elif vr.chart_type == "scatter":
            pass  # always preserve LLM-specified scatter
        elif vr.chart_type in ("bar", "horizontal_bar") and text_cols and metric_cols:
            correct = _best_chart_type(len(rows), len(metric_cols), x_lower)
            # Only override bar→pie or bar→horizontal_bar — don't second-guess line/radar/etc.
            if correct in ("pie", "horizontal_bar", "line"):
                vr.chart_type = correct

    # Leave vr.title empty if LLM didn't provide one — avoids repeating the question as title


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
