"""
LLM-as-Judge for own-query evaluation (G-Eval style, 4 criteria).

Dimensions
----------
SQL:
  temporal_precision   — Did the SQL correctly capture every time constraint
                         implied by the question? (date filters, relative windows
                         like "this month", "last 7 days", quarter ranges, etc.)
                         Full score if the question has no temporal aspect.

  schema_alignment     — Are the right tables / columns / aggregations used for
                         the stated intent? Penalises hallucinated columns, wrong
                         joins, or aggregations that don't match the question.

Answer:
  faithfulness         — Is every factual claim in the answer directly supported
                         by the returned rows? (RAGAS-style: decompose claims,
                         check each against the data.) Penalises hallucination.

  completeness         — Does the answer address ALL parts of the question?
                         Penalises partial answers that ignore a sub-question.

Composite
---------
  llm_judge_score = 0.30 * temporal_precision
                  + 0.25 * schema_alignment
                  + 0.30 * faithfulness
                  + 0.15 * completeness

The weights reflect that temporal errors and hallucination are the most damaging
failure modes in production analytics.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evaluation.pipelines.base import EvalResult

_BACKEND = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

# Weights must sum to 1.0
_WEIGHTS = {
    "temporal_precision": 0.30,
    "schema_alignment":   0.25,
    "faithfulness":       0.30,
    "completeness":       0.15,
}

_JUDGE_SYSTEM = (
    "You are a senior data-analytics evaluator. "
    "You assess NLQ-to-SQL pipelines on four criteria. "
    "Always respond with a single JSON object — no markdown, no explanation outside the JSON."
)

_JUDGE_PROMPT = """\
You are evaluating an NLQ-to-SQL pipeline. Score the following four criteria.

=== QUESTION ===
{question}

=== DATABASE SCHEMA (available tables and columns) ===
{schema_hint}

=== GENERATED SQL ===
{sql}

=== RESULT ROWS (first 10) ===
{rows_json}

=== NATURAL LANGUAGE ANSWER ===
{answer}

---
Score each criterion from 0.0 to 1.0. For each, first write a one-sentence
chain-of-thought (key: "..._reason"), then the numeric score (key: "..._score").

Criteria:

1. temporal_precision
   Does the SQL correctly capture every time constraint implied by the question?
   (date filters, "this month", "last 7 days", quarter/year ranges, etc.)
   - 1.0  : all time constraints are correct, or the question has no temporal aspect
   - 0.5  : a time filter is present but partially wrong (wrong column, off-by-one period)
   - 0.0  : a required time filter is completely missing or uses the wrong date range

2. schema_alignment
   Are the right tables, columns and aggregations used for the stated intent?
   - 1.0  : tables/columns/aggregations match the question perfectly
   - 0.5  : mostly correct but one minor wrong column or unnecessary join
   - 0.0  : wrong table, hallucinated column, or aggregation that contradicts the question

3. faithfulness
   Is every factual claim in the answer directly supported by the returned rows?
   Decompose the answer into individual claims, then check each against the data.
   - 1.0  : every claim is grounded in the rows (or answer is empty / no rows returned)
   - 0.5  : most claims are grounded but one number or label is hallucinated
   - 0.0  : the answer invents facts not present in the rows

4. completeness
   Does the answer address ALL parts of the question?
   - 1.0  : all sub-questions / entities requested are answered
   - 0.5  : most parts answered but one sub-question is skipped
   - 0.0  : the answer is a non-answer or ignores the main request

Return exactly this JSON (no other keys, no markdown):
{{
  "temporal_precision_reason": "<one sentence>",
  "temporal_precision_score":  <0.0-1.0>,
  "schema_alignment_reason":   "<one sentence>",
  "schema_alignment_score":    <0.0-1.0>,
  "faithfulness_reason":       "<one sentence>",
  "faithfulness_score":        <0.0-1.0>,
  "completeness_reason":       "<one sentence>",
  "completeness_score":        <0.0-1.0>
}}
"""


def _call_judge(prompt: str) -> dict:
    from intelligence.nlq.llm import call_llm_text
    raw = call_llm_text(prompt, system=_JUDGE_SYSTEM)
    # strip <think> blocks (Qwen CoT)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # strip markdown fences if present
    raw = re.sub(r"```(?:json)?\s*", "", raw).replace("```", "").strip()
    return json.loads(raw)


def judge_result(res: "EvalResult", schema_hint: str = "") -> dict:
    """
    Run the LLM judge on a single EvalResult.

    Returns a dict with:
      temporal_precision_score, temporal_precision_reason,
      schema_alignment_score,   schema_alignment_reason,
      faithfulness_score,       faithfulness_reason,
      completeness_score,       completeness_reason,
      llm_judge_score           (weighted composite)

    On any failure returns all scores as None and sets judge_error.
    """
    if not res.success or not res.sql:
        return _null_judgment("SQL did not execute successfully")

    rows_sample = (res.rows or [])[:10]
    rows_json   = json.dumps(rows_sample, default=str, indent=2)
    answer      = getattr(res, "answer", "") or ""

    prompt = _JUDGE_PROMPT.format(
        question=res.question,
        schema_hint=schema_hint or "(schema not provided)",
        sql=res.sql,
        rows_json=rows_json,
        answer=answer if answer else "(no answer generated)",
    )

    try:
        parsed = _call_judge(prompt)
    except Exception as e:
        return _null_judgment(f"Judge LLM call failed: {e}")

    try:
        tp = float(parsed["temporal_precision_score"])
        sa = float(parsed["schema_alignment_score"])
        fa = float(parsed["faithfulness_score"])
        co = float(parsed["completeness_score"])

        composite = round(
            _WEIGHTS["temporal_precision"] * tp
            + _WEIGHTS["schema_alignment"]  * sa
            + _WEIGHTS["faithfulness"]      * fa
            + _WEIGHTS["completeness"]      * co,
            4,
        )

        return {
            "temporal_precision_score":  round(tp, 4),
            "temporal_precision_reason": parsed.get("temporal_precision_reason", ""),
            "schema_alignment_score":    round(sa, 4),
            "schema_alignment_reason":   parsed.get("schema_alignment_reason", ""),
            "faithfulness_score":        round(fa, 4),
            "faithfulness_reason":       parsed.get("faithfulness_reason", ""),
            "completeness_score":        round(co, 4),
            "completeness_reason":       parsed.get("completeness_reason", ""),
            "llm_judge_score":           composite,
            "judge_error":               None,
        }

    except (KeyError, TypeError, ValueError) as e:
        return _null_judgment(f"Score parsing failed: {e} | raw={parsed}")


def _null_judgment(reason: str) -> dict:
    return {
        "temporal_precision_score":  None,
        "temporal_precision_reason": "",
        "schema_alignment_score":    None,
        "schema_alignment_reason":   "",
        "faithfulness_score":        None,
        "faithfulness_reason":       "",
        "completeness_score":        None,
        "completeness_reason":       "",
        "llm_judge_score":           None,
        "judge_error":               reason,
    }


def aggregate_judge_scores(judge_results: list[dict]) -> dict:
    """Aggregate per-query judge dicts into summary statistics."""
    def _mean(key: str) -> float | None:
        vals = [r[key] for r in judge_results if r.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    return {
        "mean_llm_judge_score":        _mean("llm_judge_score"),
        "mean_temporal_precision":     _mean("temporal_precision_score"),
        "mean_schema_alignment":       _mean("schema_alignment_score"),
        "mean_faithfulness":           _mean("faithfulness_score"),
        "mean_completeness":           _mean("completeness_score"),
        "n_judged":                    sum(1 for r in judge_results if r.get("llm_judge_score") is not None),
        "n_judge_errors":              sum(1 for r in judge_results if r.get("judge_error")),
    }
