"""
Metricflow branch pipeline wrapper (rishit_sql_rag_metricflow).
Dynamically extracts sql_rag.py and llm.py from the git branch into a temp directory,
then imports and runs the SQL path (MetricFlow disabled — not applicable outside Frammer).
"""
import importlib.util
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from evaluation.pipelines.base import Pipeline, EvalResult
from evaluation.config import METRICFLOW_BRANCH, BACKEND_ROOT


_BRANCH_MODULES = {}   # cache: branch_name -> imported module dict


def _load_branch_module(branch: str, rel_path: str):
    """Use git show to read a file from a branch and import it as a module."""
    key = f"{branch}:{rel_path}"
    if key in _BRANCH_MODULES:
        return _BRANCH_MODULES[key]

    result = subprocess.run(
        ["git", "show", f"{branch}:{rel_path}"],
        capture_output=True, text=True,
        cwd=str(BACKEND_ROOT.parent),
    )
    if result.returncode != 0:
        raise RuntimeError(f"git show failed for {key}: {result.stderr}")

    module_name = f"_metricflow_{rel_path.replace('/', '_').replace('.py', '')}"

    # Patch old 'config' import -> current backend_config/llm_config equivalents
    # so we never touch the backend folder of the current branch
    source = result.stdout
    source = source.replace(
        "from config import LLM_PROVIDER, LLM_MODEL, GOOGLE_API_KEY, OPENAI_API_KEY",
        # Inject current-branch equivalents; normalise provider to 'openai'
        # (OpenRouter is OpenAI-compatible — metricflow branch only handles 'gemini'/'openai')
        "from backend_config import OPENAI_API_KEY, GOOGLE_API_KEY\n"
        "from llm_config import QWEN_CODER_MODEL as LLM_MODEL, LLM_BASE_URL, make_openai_client\n"
        "LLM_PROVIDER = 'openai'",
    )
    # Also patch the raw OpenAI() call in _call_openai to use make_openai_client
    source = source.replace(
        "client = OpenAI(api_key=OPENAI_API_KEY)",
        "client = make_openai_client()",
    )

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(source)
        tmp_path = f.name

    spec = importlib.util.spec_from_file_location(module_name, tmp_path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    _BRANCH_MODULES[key] = mod
    return mod


class MetricflowPipeline(Pipeline):
    name = "metricflow"

    def __init__(self):
        sys.path.insert(0, str(BACKEND_ROOT))
        try:
            self._llm = _load_branch_module(METRICFLOW_BRANCH, "backend/intelligence/nlq/llm.py")
        except Exception as e:
            print(f"[MetricflowPipeline] Could not load llm module: {e}")
            self._llm = None

    def _build_schema_prompt(self, schema_str: str, client_id: int) -> str:
        return (
            f"You are a PostgreSQL analytics expert for a video content platform.\n"
            f"Convert the user's natural language question into a SQL SELECT query.\n\n"
            f"{schema_str}\n\n"
            f"RULES:\n"
            f"1. Only SELECT statements. Always prefix tables with data.\n"
            f"2. Filter WHERE client_id = {client_id} unless comparing clients.\n"
            f"3. Add LIMIT 500 to row-level queries.\n\n"
            f'Return JSON: {{"path": "sql", "sql": "...", "chart_type": "bar", '
            f'"title": "...", "x": "col", "y": "col"}}'
        )

    def run(self, question: str, conn, schema_str: str, client_id: int = 1, **kwargs) -> EvalResult:
        t_start = time.perf_counter()

        if self._llm is None:
            return EvalResult(
                question=question, pipeline_name=self.name,
                success=False, error="Metricflow LLM module failed to load",
            )

        system_prompt = self._build_schema_prompt(schema_str, client_id)

        try:
            llm_response = self._llm.call_llm(system_prompt, question)
        except Exception as e:
            return EvalResult(
                question=question, pipeline_name=self.name,
                latency_ms=round((time.perf_counter() - t_start) * 1000, 1),
                success=False, error=f"LLM call failed: {e}",
            )

        sql = llm_response.get("sql", "").strip()
        sql = re.sub(r"<think>.*?</think>", "", sql, flags=re.DOTALL).strip()

        if not sql or not re.match(r"^\s*(WITH|SELECT)\b", sql, re.IGNORECASE):
            return EvalResult(
                question=question, pipeline_name=self.name,
                latency_ms=round((time.perf_counter() - t_start) * 1000, 1),
                success=False, error="No valid SELECT generated",
            )

        # Execute — no healing in metricflow branch
        rows = []
        success = False
        error = None
        try:
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

        # Answer (Call 2)
        answer = ""
        if success and rows:
            try:
                answer = self._llm.generate_answer(question, rows[:15])
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
