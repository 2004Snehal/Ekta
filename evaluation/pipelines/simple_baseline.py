"""
Simple baseline pipeline — 2 LLM calls, minimal system prompt, no RAG, no healing.
Mirrors the trying_merge_recommendations branch approach but with a deliberately
stripped-down system prompt (raw DDL only, no business rules, no examples).
"""
import json
import re
import time

from evaluation.pipelines.base import Pipeline, EvalResult
from evaluation.config import SQL_MODEL, LLM_TEMPERATURE, LLM_MAX_TOKENS


_SQL_SYSTEM = (
    "You are a SQL assistant. Given the database schema, generate a SQL SELECT query "
    "to answer the user's question. Return ONLY the raw SQL query. "
    "No explanation, no markdown fences, no JSON wrapper."
)

_ANSWER_SYSTEM = (
    "You are a data analyst. Given a question and query results, answer in 1-3 sentences "
    "using specific numbers. No meta-phrases like 'based on the data'."
)


class SimpleBaselinePipeline(Pipeline):
    name = "simple_baseline"

    def __init__(self):
        import sys
        sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent.parent / "backend"))
        from llm_config import make_openai_client
        self._client = make_openai_client()

    def _call(self, system: str, user: str) -> str:
        resp = self._client.chat.completions.create(
            model=SQL_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user",   "content": user}],
            temperature=LLM_TEMPERATURE,
            max_tokens=LLM_MAX_TOKENS,
        )
        return resp.choices[0].message.content.strip()

    def run(self, question: str, conn, schema_str: str, client_id: int = 1, **kwargs) -> EvalResult:
        t_start = time.perf_counter()

        # Call 1: SQL generation — bare schema, nothing else
        user_msg = f"Schema:\n{schema_str}\n\nQuestion: {question}"
        try:
            raw = self._call(_SQL_SYSTEM, user_msg)
            # Strip think blocks if present
            raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
            # Strip markdown fences
            raw = re.sub(r"```(?:sql)?\s*", "", raw).replace("```", "").strip()
            # If model returned JSON anyway, try to extract sql key
            if raw.startswith("{"):
                try:
                    parsed = json.loads(raw)
                    sql = parsed.get("sql", "").strip()
                except (json.JSONDecodeError, ValueError):
                    sql = raw
            else:
                sql = raw
        except Exception as e:
            return EvalResult(
                question=question, pipeline_name=self.name,
                latency_ms=round((time.perf_counter() - t_start) * 1000, 1),
                success=False, error=f"SQL generation failed: {e}",
            )

        if not sql or not re.match(r"^\s*(WITH|SELECT)\b", sql, re.IGNORECASE):
            return EvalResult(
                question=question, pipeline_name=self.name,
                sql=sql, latency_ms=round((time.perf_counter() - t_start) * 1000, 1),
                success=False, error=f"No valid SELECT generated",
            )

        # Execute SQL — no retry, no healing
        rows = []
        success = False
        error = None
        try:
            import sqlite3
            if isinstance(conn, sqlite3.Connection):
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
            else:
                import psycopg2.extras
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                cur.execute(sql)
                rows = [dict(r) for r in cur.fetchall()]
            success = True
        except Exception as e:
            error = str(e)
            try:
                conn.rollback()
            except Exception:
                pass

        latency_ms = round((time.perf_counter() - t_start) * 1000, 1)

        # Call 2: answer narration (only if SQL succeeded)
        answer = ""
        if success and rows:
            try:
                sample = rows[:15]
                ans_user = f"Question: {question}\n\nResults: {json.dumps(sample, default=str)}"
                answer = self._call(_ANSWER_SYSTEM, ans_user)
                answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()
            except Exception:
                pass

        return EvalResult(
            question=question,
            pipeline_name=self.name,
            sql=sql,
            answer=answer,
            rows=rows,
            latency_ms=latency_ms,
            success=success,
            error=error,
            first_shot_success=success,
            heal_attempts=0,
        )
