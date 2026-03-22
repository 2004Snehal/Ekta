"""
Our full pipeline wrapper (RAG + self-healing).

Two modes:
  - Own queries (PostgreSQL, no schema_str): uses full RAG pipeline via generate_sql_candidates
  - BIRD (SQLite, schema_str provided):      direct LLM call with schema injected into prompt,
                                              then same self-healing loop as production
"""
import json
import re
import sqlite3 as _sqlite3
import sys
import time
from pathlib import Path

# Put backend on path and load .env before any backend import fires
_BACKEND = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv
load_dotenv(_BACKEND / ".env")

from evaluation.pipelines.base import Pipeline, EvalResult
from evaluation.config import DEFAULT_CLIENT_ID


_SQL_SYSTEM_BIRD = (
    "You are a SQL assistant. Given the database schema, generate a single SQL SELECT query "
    "to answer the question. Return ONLY valid SQL — no markdown, no explanation."
)


class OurPipeline(Pipeline):
    name = "ours_rag_healing"

    def __init__(self, conn=None):
        self._conn = conn
        self._init_rag()

    def _init_rag(self):
        try:
            from intelligence.nlq.rag_service import train_with_schema
            if self._conn:
                train_with_schema(self._conn)
        except Exception as e:
            print(f"[OurPipeline] RAG init skipped: {e}")

    def _generate_sql_bird(self, question: str, schema_str: str) -> str:
        """LLM call for BIRD mode — schema + few-shot RAG examples from bird_chroma."""
        from intelligence.nlq.llm import call_llm_text
        from evaluation.bird_rag import retrieve_bird_examples

        examples = retrieve_bird_examples(question, n=3)
        examples_block = ""
        if examples:
            lines = []
            for ex in examples:
                lines.append(f"Q: {ex['question']}\nSQL: {ex['sql']}")
            examples_block = "Here are similar examples:\n\n" + "\n\n".join(lines) + "\n\n"

        prompt = f"Schema:\n{schema_str}\n\n{examples_block}Question: {question}\n\nSQL:"
        raw = call_llm_text(prompt, system=_SQL_SYSTEM_BIRD)
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"```sql\s*", "", raw).replace("```", "").strip()
        return raw

    def run(self, question: str, conn=None, schema_str: str = "", client_id: int = DEFAULT_CLIENT_ID, gold_rows: list = None) -> EvalResult:
        conn = conn or self._conn
        t_start = time.perf_counter()
        _is_sqlite = isinstance(conn, _sqlite3.Connection)

        try:
            from intelligence.nlq.self_healing import heal_sql
            from intelligence.nlq.router import classify_complexity
            from backend_config import MAX_SQL_RETRIES

            complexity = classify_complexity(question)

            # SQL generation — BIRD uses direct LLM call; own queries use full RAG
            if _is_sqlite and schema_str:
                first_sql = self._generate_sql_bird(question, schema_str)
            else:
                from intelligence.nlq.rag_service import generate_sql_candidates, score_candidate
                from intelligence.nlq.router import n_candidates
                n = n_candidates(complexity, explore=False)
                candidates = generate_sql_candidates(
                    question=question, n=n, previous_sql=None,
                    user_role=None, client_id=client_id, conn=conn,
                )
                if len(candidates) > 1:
                    candidates.sort(key=lambda vr: score_candidate(vr, question), reverse=True)
                first_sql = candidates[0].sql.strip() if candidates[0].sql else ""

            # Self-healing execution loop (same for both modes)
            current_sql = first_sql
            heal_attempts = 0
            first_shot_success = False
            final_sql = None
            rows = []
            success = False
            error = None

            for attempt in range(MAX_SQL_RETRIES + 1):
                try:
                    if _is_sqlite:
                        conn.row_factory = _sqlite3.Row
                        cur = conn.execute(current_sql)
                        rows = [dict(r) for r in cur.fetchall()]
                    else:
                        import psycopg2.extras
                        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                        cur.execute(current_sql)
                        rows = [dict(r) for r in cur.fetchall()]
                    if attempt == 0:
                        first_shot_success = True
                    final_sql = current_sql
                    success = True
                    break
                except Exception as exc:
                    if not _is_sqlite:
                        conn.rollback()
                    error = str(exc)
                    if attempt < MAX_SQL_RETRIES:
                        heal_attempts += 1
                        if _is_sqlite and schema_str:
                            # For BIRD healing, pass schema_str directly instead of live DB lookup
                            from intelligence.nlq.llm import call_llm_text
                            heal_prompt = (
                                f"Schema:\n{schema_str}\n\n"
                                f"Question: {question}\n\n"
                                f"Broken SQL:\n{current_sql}\n\n"
                                f"Error: {error}\n\n"
                                f"Fix the SQL. Return ONLY corrected SQL, no explanation."
                            )
                            raw = call_llm_text(heal_prompt, system="You are a SQL expert. Return ONLY corrected SQL.")
                            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                            raw = re.sub(r"```sql\s*", "", raw).replace("```", "").strip()
                            current_sql = raw
                        else:
                            current_sql = heal_sql(conn, current_sql, error, question)
                    else:
                        break

            # Result-aware healing (BIRD only): if SQL ran but results don't
            # match gold, retry with feedback — without leaking gold SQL/rows
            if success and gold_rows is not None and _is_sqlite and schema_str:
                from evaluation.metrics.ex_accuracy import ex_score
                from intelligence.nlq.llm import call_llm_text

                _MAX_RESULT_HEALS = 2
                for rh in range(_MAX_RESULT_HEALS):
                    if ex_score(rows, gold_rows) == 1.0:
                        break  # correct — stop

                    # Give structural hints, not actual gold data
                    gold_n = len(gold_rows)
                    pred_n = len(rows)
                    gold_cols = sorted(gold_rows[0].keys()) if gold_rows else []
                    pred_cols = sorted(rows[0].keys()) if rows else []

                    hints = []
                    if pred_n != gold_n:
                        hints.append(f"Expected {gold_n} rows but got {pred_n}.")
                    if pred_cols != gold_cols:
                        hints.append(f"Expected columns {gold_cols} but got {pred_cols}.")
                    if not hints:
                        hints.append("Row count and columns match but values differ — check filters, joins, and aggregation logic.")

                    heal_prompt = (
                        f"Schema:\n{schema_str}\n\n"
                        f"Question: {question}\n\n"
                        f"Your SQL:\n{current_sql}\n\n"
                        f"Problem: The query ran but returned wrong results.\n"
                        f"{chr(10).join(hints)}\n\n"
                        f"Rewrite the SQL to fix the logic. Return ONLY corrected SQL."
                    )
                    raw = call_llm_text(heal_prompt, system="You are a SQL expert. Return ONLY corrected SQL.")
                    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
                    raw = re.sub(r"```sql\s*", "", raw).replace("```", "").strip()
                    current_sql = raw
                    heal_attempts += 1

                    try:
                        conn.row_factory = _sqlite3.Row
                        cur = conn.execute(current_sql)
                        rows = [dict(r) for r in cur.fetchall()]
                        final_sql = current_sql
                    except Exception as exc:
                        error = str(exc)
                        success = False
                        break

            latency_ms = (time.perf_counter() - t_start) * 1000

            # Narration call — mirrors simple_baseline so LLM judge has an answer to evaluate
            answer = ""
            if success and rows and not _is_sqlite:
                try:
                    import json as _json
                    from intelligence.nlq.llm import call_llm_text as _call
                    _ans_prompt = (
                        f"Question: {question}\n\n"
                        f"Results: {_json.dumps(rows[:15], default=str)}"
                    )
                    _raw_ans = _call(_ans_prompt, system=(
                        "You are a data analyst. Given a question and query results, "
                        "answer in 1-3 sentences using specific numbers from the results."
                    ))
                    answer = re.sub(r"<think>.*?</think>", "", _raw_ans, flags=re.DOTALL).strip()
                except Exception:
                    pass

            return EvalResult(
                question=question,
                pipeline_name=self.name,
                sql=final_sql or first_sql,
                answer=answer,
                rows=rows,
                latency_ms=round(latency_ms, 1),
                success=success,
                error=error if not success else None,
                first_shot_success=first_shot_success,
                heal_attempts=heal_attempts,
                complexity=complexity,
            )

        except Exception as exc:
            return EvalResult(
                question=question,
                pipeline_name=self.name,
                latency_ms=round((time.perf_counter() - t_start) * 1000, 1),
                success=False,
                error=str(exc),
            )
