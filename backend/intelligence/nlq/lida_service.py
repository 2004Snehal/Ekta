"""
Explore insight engine — optional Step 4, runs when explore=True.

Analyses the query DataFrame and generates additional chart suggestions
using a single LLM call. Each suggestion uses the frontend's native
chart format (chart_type / x / y / title) so ChartRenderer can display
it directly — no Vega-Lite dependency needed.
"""

import json
import logging
import re
import sys
import os
from typing import List

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import LIDA_MAX_GOALS
from llm_config import QWEN_CODER_MODEL, make_openai_client

logger = logging.getLogger("nlq.explore")

VALID_CHART_TYPES = {"bar", "horizontal_bar", "line", "pie", "scatter", "stacked_bar", "table"}


def generate_insights(df: pd.DataFrame, question: str, user_role: str = None) -> List[dict]:
    """
    Generate additional chart suggestions from a query result DataFrame.

    Returns a list of dicts, each with:
        title      — what the chart shows
        chart_spec — {chart_type, title, x, y, data}  (ChartRenderer-compatible)

    Returns [] on empty data or any error — never raises.
    """
    if df.empty or len(df.columns) < 2:
        logger.info("Explore skipped — insufficient data (%d rows, %d cols).", len(df), len(df.columns))
        return []

    try:
        return _generate(df, question, user_role)
    except Exception as exc:
        logger.error("Explore insight generation failed: %s", exc, exc_info=True)
        return []


def _generate(df: pd.DataFrame, question: str, user_role: str = None) -> List[dict]:
    # ── Build a compact data summary for the LLM ────────────────────────────
    col_info = []
    for c in df.columns:
        dtype = str(df[c].dtype)
        nunique = int(df[c].nunique())
        sample = df[c].dropna().head(3).tolist()
        col_info.append(f"  - {c} ({dtype}, {nunique} unique): {sample}")

    schema_block = "\n".join(col_info)

    # ── Persona from role config ────────────────────────────────────────────
    persona_hint = ""
    try:
        from intelligence.nlq.role_config import get_role_config
        role_cfg = get_role_config(user_role)
        if role_cfg:
            persona_hint = (
                f"\nThe user is a {role_cfg.display_name}. "
                f"{role_cfg.lida_context}\n"
            )
    except Exception:
        pass

    valid_types = ", ".join(sorted(VALID_CHART_TYPES))

    prompt = f"""You are a data analyst. The user asked: "{question}"

The query returned {len(df)} rows with these columns:
{schema_block}
{persona_hint}
Suggest exactly {LIDA_MAX_GOALS} additional visualizations that reveal
different angles of this data. Each must use a DIFFERENT chart type or
axis combination from the others.

For each, pick the best chart type from: {valid_types}
Choose x and y from the actual column names listed above.

Respond ONLY with a JSON array (no markdown fences, no explanation):
[
  {{"chart_type": "...", "title": "...", "x": "...", "y": "..."}},
  ...
]"""

    client = make_openai_client()
    response = client.chat.completions.create(
        model=QWEN_CODER_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    raw = response.choices[0].message.content.strip()
    logger.debug("Explore LLM raw response: %s", raw[:500])

    # ── Parse — strip markdown fences + trailing commas ─────────────────────
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL)
    text = fenced.group(1) if fenced else raw
    text = re.sub(r",\s*([}\]])", r"\1", text)

    suggestions = json.loads(text)
    if not isinstance(suggestions, list):
        suggestions = [suggestions]

    # ── Convert to ChartRenderer-compatible specs ───────────────────────────
    columns = set(df.columns)
    records = json.loads(df.to_json(orient="records", default_handler=str))

    insights = []
    for s in suggestions:
        ct = s.get("chart_type", "").lower()
        x = s.get("x", "")
        y = s.get("y", "")
        title = s.get("title", "")

        if ct not in VALID_CHART_TYPES:
            ct = "bar"
        if x not in columns or y not in columns:
            logger.warning("Explore: skipping suggestion with unknown columns x=%s y=%s", x, y)
            continue

        insights.append({
            "title": title,
            "chart_spec": {
                "chart_type": ct,
                "title": title,
                "x": x,
                "y": y,
                "data": records,
            },
        })

    logger.info("Explore generated %d insights (1 LLM call).", len(insights))
    return insights
