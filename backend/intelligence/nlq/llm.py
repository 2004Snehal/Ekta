"""
LLM abstraction layer — Qwen via OpenRouter.
To switch models: edit llm_config.py.
"""

import json
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from llm_config import QWEN_CODER_MODEL, make_openai_client, LLM_MAX_TOKENS, LLM_TEMPERATURE

logger = logging.getLogger("nlq.llm")


# ── Retry helper ──────────────────────────────────────────────────────────────

def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "rate limit" in msg or "resource_exhausted" in msg


def _parse_retry_delay(exc: Exception, fallback: float = 5.0) -> float:
    import re
    match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+(?:\.\d+)?)', str(exc))
    return float(match.group(1)) + 1.0 if match else fallback


# ── Plain-text LLM call ───────────────────────────────────────────────────────

def call_llm_text(prompt: str, system: str = None, model: str = None) -> str:
    """
    Send a prompt to Qwen (via OpenRouter) and return plain text.
    Used by self-healing (SQL correction) and answer generation.
    Automatically retries on quota errors.
    """
    return _call_with_retry(_call_openrouter_text, prompt, system, model)


def _call_with_retry(fn, prompt: str, system: str = None, model: str = None, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            return fn(prompt, system, model)
        except Exception as exc:
            if _is_quota_error(exc) and attempt < max_retries - 1:
                wait = _parse_retry_delay(exc, fallback=5.0 * (2 ** attempt))
                logger.warning("LLM quota error (attempt %d/%d) — retrying in %.1fs.", attempt + 1, max_retries, wait)
                time.sleep(wait)
            else:
                raise


def _call_openrouter_text(prompt: str, system: str = None, model: str = None) -> str:
    client = make_openai_client()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=model or QWEN_CODER_MODEL,
        messages=messages,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )
    return response.choices[0].message.content.strip()


# ── Statistical pre-summarization (Python, no LLM) ───────────────────────────

def build_summary(data: list, x_col: str, y_col: str, strategy: dict) -> dict:
    """
    Compute a compact statistical summary from the full result set.
    strategy dict comes from Call 1's answer_strategy JSON field.
    No LLM involved — pure Python, runs in microseconds.
    """
    if not data:
        return {}

    # Normalise column identifiers so they are always hashable keys.
    # Vanna metadata can occasionally send lists or other structures here.
    if isinstance(x_col, list):
        x_col = x_col[0] if x_col else ""
    if isinstance(y_col, list):
        y_col = y_col[0] if y_col else ""

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
        return {"total_rows": n, "sample_rows": data[:10]}


# ── Answer generation (Call 2) ────────────────────────────────────────────────

_ANSWER_SYSTEM_PROMPT = """You are a media analytics assistant for Frammer AI — a video content production platform.
Your job is to answer a user's question directly using the statistical summary provided.

RULES:
- Be concise: 1–4 sentences. Lead with the most important number or finding.
- Use specific names, numbers, and percentages from the summary — never be vague.
- Never say "based on the data", "the query shows", "the results indicate", or similar meta-phrases.
  Just state the answer as a fact.
- For "which X is best/highest/lowest/worst": name the winner and its value.
  If the summary has multiple ranked entities, mention the runner-up for context.
- For trend questions: state direction, peak or trough, and the change value.
- For comparisons: highlight the most notable contrast with real numbers.
- For totals/counts: give the exact number plus one useful piece of context.
- For distribution/mix: name the top 1–2 categories and their share or count.
- Row count rule: if the summary has a `total_rows` field, that is the actual record count.
  NEVER count the items in `sample_rows` and report that as the total.
- If summary is empty or has no data: say "No data was found for this query."
- Do NOT repeat the question. Do NOT describe the chart. Do NOT explain concepts.
- Domain context: channels are content production channels, publish rate means % of created
  videos that were published, uploaded_at is when a video entered the system.
"""


def generate_answer(question: str, summary: dict, focus: list, user_role: str = None) -> str:
    """
    Call 2: given a compact statistical summary, produce a plain-English answer.
    summary is pre-computed by build_summary() — no raw row slicing here.
    """
    if not summary:
        return "No data was found for this query."

    system = _ANSWER_SYSTEM_PROMPT

    # Inject role-specific answer persona if available
    if user_role:
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from intelligence.nlq.role_config import get_role_config
            role_cfg = get_role_config(user_role)
            if role_cfg and role_cfg.answer_persona:
                system = role_cfg.answer_persona + "\n\n" + _ANSWER_SYSTEM_PROMPT
        except Exception:
            pass

    focus_hint = ", ".join(focus) if focus else "key numbers and trends"
    user_message = (
        f"Question: {question}\n\n"
        f"Data summary:\n{json.dumps(summary, default=str)}\n\n"
        f"Focus on: {focus_hint}"
    )

    try:
        return call_llm_text(user_message, system=system)
    except Exception:
        return ""
