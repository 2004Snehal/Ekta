"""
LLM abstraction layer.
Switching providers: set LLM_PROVIDER=openai (or gemini) in .env.
Switching models:    set LLM_MODEL=<model_name> in .env.
"""

import json
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import LLM_PROVIDER, LLM_MODEL, GOOGLE_API_KEY, OPENAI_API_KEY

logger = logging.getLogger("nlq.llm")


# ── Retry helper ──────────────────────────────────────────────────────────────

def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg


def _parse_retry_delay(exc: Exception, fallback: float = 5.0) -> float:
    import re
    match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+(?:\.\d+)?)', str(exc))
    return float(match.group(1)) + 1.0 if match else fallback


def _retry(fn, *args, max_retries: int = 3, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if _is_quota_error(exc) and attempt < max_retries - 1:
                wait = _parse_retry_delay(exc, fallback=5.0 * (2 ** attempt))
                logger.warning("LLM quota error (attempt %d/%d) — retrying in %.1fs.", attempt + 1, max_retries, wait)
                time.sleep(wait)
            else:
                raise


# ── Plain-text LLM call (used by self-healing and answer generation) ──────────

def call_llm_text(prompt: str, system: str = None) -> str:
    """
    Send a prompt to the configured LLM and return plain text.
    Used by self-healing (SQL correction) and answer generation.
    """
    if LLM_PROVIDER == "gemini":
        return _retry(_call_gemini_text, prompt, system)
    elif LLM_PROVIDER == "openai":
        return _retry(_call_openai_text, prompt, system)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'.")


# ── Statistical pre-summarization (Python, no LLM) ───────────────────────────

def build_summary(data: list, x_col: str, y_col: str, strategy: dict) -> dict:
    """
    Compute a compact statistical summary from the full result set.
    strategy dict comes from Call 1's answer_strategy JSON field.
    No LLM involved — pure Python, runs in microseconds.
    """
    if not data:
        return {}

    stype = strategy.get("type", "detail_sample")
    n = len(data)

    if stype == "time_series_trend":
        pairs = [(r.get(x_col), r.get(y_col)) for r in data if r.get(y_col) is not None]
        if not pairs:
            return {"total_periods": n, "rows": data[:5]}
        vals = [v for _, v in pairs]
        first_val, last_val = vals[0], vals[-1]
        peak = max(pairs, key=lambda t: t[1])
        trough = min(pairs, key=lambda t: t[1])
        change_pct = round((last_val - first_val) / first_val * 100, 1) if first_val else None
        return {
            "total_periods": n,
            "first":  {x_col: pairs[0][0],  y_col: first_val},
            "last":   {x_col: pairs[-1][0], y_col: last_val},
            "peak":   {x_col: peak[0],   y_col: peak[1]},
            "trough": {x_col: trough[0], y_col: trough[1]},
            "mean":   round(sum(vals) / len(vals), 2),
            "trend":  "upward" if last_val > first_val else "downward" if last_val < first_val else "flat",
            "change_pct": change_pct,
        }

    elif stype == "top_n_ranked":
        sorted_desc = sorted(data, key=lambda r: r.get(y_col, 0) or 0, reverse=True)
        total = sum((r.get(y_col, 0) or 0) for r in data)
        top1_val = sorted_desc[0].get(y_col, 0) if sorted_desc else 0
        return {
            "total_rows": n,
            "top_5":    sorted_desc[:5],
            "bottom_3": sorted_desc[-3:] if n > 5 else [],
            "total":    total,
            "top1_share_pct": round(top1_val / total * 100, 1) if total else None,
        }

    elif stype == "distribution":
        total = sum((r.get(y_col, 0) or 0) for r in data) or 1
        enriched = sorted(
            [{**r, "_share_pct": round((r.get(y_col, 0) or 0) / total * 100, 1)} for r in data],
            key=lambda r: r.get(y_col, 0) or 0,
            reverse=True,
        )
        return {"slices": enriched, "total": total, "slice_count": n}

    elif stype == "single_aggregate":
        return {"result": data[0]}

    else:  # detail_sample
        return {"rows": data[:15], "total_rows": n}


# ── Answer generation (Call 2) ────────────────────────────────────────────────

_ANSWER_SYSTEM_PROMPT = """You are a media analytics assistant. Your job is to answer a user's question
directly and concisely using the statistical summary of query results provided.

RULES:
- Answer in 1–3 sentences maximum.
- Use specific names, numbers, and percentages from the summary — never be vague.
- Never say "based on the data", "the query shows", "the results indicate", or similar meta-phrases.
  Just state the answer as a fact.
- For "which X is highest/lowest" questions: name the winner and its value, then optionally mention second place.
- For trend questions: describe the direction and the key turning point or peak/trough with its value.
- For comparison questions: highlight the most notable contrast with real numbers.
- For totals/counts: give the exact number and any useful context from the summary.
- For distribution/mix questions: name the top 1–2 categories and their share or count.
- If the summary is empty or has no data, say "No data was found for this query."
- Do NOT repeat the question back. Do NOT describe the chart. Do NOT explain what the numbers mean conceptually.
"""


def generate_answer(question: str, summary: dict, focus: list) -> str:
    """
    Call 2: given a compact statistical summary, produce a plain-English answer.
    summary is pre-computed by build_summary() — no raw row slicing here.
    """
    if not summary:
        return "No data was found for this query."

    focus_hint = ", ".join(focus) if focus else "key numbers and trends"
    user_message = (
        f"Question: {question}\n\n"
        f"Data summary:\n{json.dumps(summary, default=str)}\n\n"
        f"Focus on: {focus_hint}"
    )

    try:
        return call_llm_text(user_message, system=_ANSWER_SYSTEM_PROMPT)
    except Exception:
        return ""


# ── Gemini ────────────────────────────────────────────────────────────────────

def _call_gemini_text(prompt: str, system: str = None) -> str:
    import google.genai as genai
    client = genai.Client(api_key=GOOGLE_API_KEY)
    config = {}
    if system:
        config["system_instruction"] = system
    response = client.models.generate_content(
        model=LLM_MODEL,
        contents=prompt,
        config=config or None,
    )
    return response.text.strip()


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _call_openai_text(prompt: str, system: str = None) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()
