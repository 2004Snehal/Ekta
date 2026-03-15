"""
SQL RAG core logic.
Flow: question → LLM (generates SQL + chart spec) → validate → execute → log → return.
"""

import re
from datetime import datetime
from intelligence.nlq.context import build_system_prompt
from intelligence.nlq.llm import call_llm, generate_answer

REQUIRED_KEYS = {"sql", "chart_type", "title", "x", "y"}


def run_nlq_query(question: str, client_id: int, conn) -> dict:
    """
    Execute an NLQ query end-to-end.
    Returns a dict ready to send as API response.
    """
    system_prompt = build_system_prompt(client_id, conn)

    # 1. Call LLM
    try:
        llm_response = call_llm(system_prompt, question)
    except Exception as e:
        return _error(str(e), question)

    # 2. Validate LLM response shape
    missing = REQUIRED_KEYS - set(llm_response.keys())
    if missing:
        return _error(f"LLM response missing fields: {missing}", question)

    sql = llm_response["sql"].strip()

    # 3. Safety: only allow SELECT
    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        return _error("LLM generated a non-SELECT statement — blocked.", question)

    # 4. Inject LIMIT if missing (safety cap)
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 500"

    # 5. Execute
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        data = [dict(zip(columns, row)) for row in rows]
        # Serialize non-JSON-safe types
        data = _serialize(data)
        success = True
        error_msg = None
    except Exception as e:
        conn.rollback()
        success = False
        error_msg = str(e)
        data = []
        columns = []

    # 6. Log to query_log
    _log_query(conn, client_id, question, sql, success, len(data))

    if not success:
        return _error(f"SQL execution failed: {error_msg}", question)

    # 7. Generate answer from real data (second lightweight LLM call)
    answer = generate_answer(question, data)

    return {
        "question": question,
        "answer": answer,
        "sql": sql,
        "chart_type": llm_response.get("chart_type", "table"),
        "title": llm_response.get("title", ""),
        "x": llm_response.get("x", columns[0] if columns else ""),
        "y": llm_response.get("y", columns[1] if len(columns) > 1 else ""),
        "description": llm_response.get("description", ""),
        "data": data,
        "columns": columns,
        "row_count": len(data),
    }


def _serialize(data: list) -> list:
    """Convert dates/decimals to JSON-safe types."""
    import decimal
    result = []
    for row in data:
        clean = {}
        for k, v in row.items():
            if isinstance(v, datetime):
                clean[k] = v.isoformat()
            elif hasattr(v, "date"):  # date objects
                clean[k] = str(v)
            elif isinstance(v, decimal.Decimal):
                clean[k] = float(v)
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
        conn.rollback()  # don't fail the request if logging fails


def _error(message: str, question: str) -> dict:
    return {
        "question": question,
        "error": message,
        "sql": None,
        "chart_type": "table",
        "title": "Error",
        "x": "",
        "y": "",
        "description": "",
        "data": [],
        "columns": [],
        "row_count": 0,
    }
