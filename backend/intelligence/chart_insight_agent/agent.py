"""
Chart Insight Agent — on-demand LLM analysis of a single chart's data.

Receives the exact data rendered in a chart and returns:
  - summary: one-sentence headline
  - insights: 3–5 plain-English bullet points referencing actual numbers

Rules:
- LLM only sees the data passed in — no DB access, no external context.
- LLM must reference actual values, not generalise.
- No speculation beyond what the numbers show.
- Supports Gemini and OpenAI (same dual-provider pattern as narrator.py).
"""

from __future__ import annotations
import json
import logging
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import LLM_PROVIDER, GOOGLE_API_KEY, OPENAI_API_KEY

# Use Flash-Lite for chart insights — lightweight task, low latency needed
CHART_MODEL_GEMINI = "gemini-2.5-flash-lite"
CHART_MODEL_OPENAI = os.getenv("LLM_MODEL", "gpt-4o-mini")

from intelligence.chart_insight_agent.schemas import (
    ChartInsightRequest, ChartInsightResponse,
    ChartDescriptionRequest, ChartDescriptionResponse,
)

logger = logging.getLogger(__name__)


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a data analyst generating plain-English insights for a media operations dashboard.

You will receive the title, type, and raw data of a single chart.

RULES (non-negotiable):
1. Write exactly 3–5 bullet points under "insights". Each must be one sentence.
2. Reference actual numbers from the data (values, percentages, labels). Do not generalise.
3. Do not speculate about causes beyond what the data shows.
4. Do not use the word "significant".
5. Write a single "summary" sentence (max 15 words) capturing the most notable pattern.
6. Return ONLY valid JSON matching this exact schema — no markdown, no extra keys:
{
  "summary": string,
  "insights": [string, ...]
}
"""


# ── Data formatting ───────────────────────────────────────────────────────────

def _format_data(req: ChartInsightRequest) -> str:
    """Serialise the chart context into a compact text block for the LLM."""
    lines = [
        f"Chart title: {req.chart_title}",
        f"Chart type: {req.chart_type}",
    ]
    if req.x_label:
        lines.append(f"X axis: {req.x_label}")
    if req.y_label:
        lines.append(f"Y axis: {req.y_label}")

    lines.append(f"Data ({len(req.data)} rows):")

    # Cap at 100 rows to keep prompt size reasonable
    for row in req.data[:100]:
        lines.append("  " + ", ".join(f"{k}={v}" for k, v in row.items()))

    if len(req.data) > 100:
        lines.append(f"  ... ({len(req.data) - 100} more rows not shown)")

    return "\n".join(lines)


# ── LLM calls ─────────────────────────────────────────────────────────────────

def _call_gemini(user_message: str) -> dict[str, Any]:
    try:
        import google.genai as genai
        import google.genai.types as genai_types
    except ImportError:
        raise ImportError("google-genai is not installed. Run: pip install google-genai")

    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")

    schema = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={
            "summary":  genai_types.Schema(type=genai_types.Type.STRING),
            "insights": genai_types.Schema(
                type=genai_types.Type.ARRAY,
                items=genai_types.Schema(type=genai_types.Type.STRING),
            ),
        },
        required=["summary", "insights"],
    )

    client = genai.Client(api_key=GOOGLE_API_KEY)
    logger.debug("chart_insight_agent: calling Gemini (%s)", CHART_MODEL_GEMINI)
    response = client.models.generate_content(
        model=CHART_MODEL_GEMINI,
        contents=user_message,
        config={
            "system_instruction":  _SYSTEM_PROMPT,
            "response_mime_type":  "application/json",
            "response_schema":     schema,
        },
    )
    logger.debug("chart_insight_agent: Gemini responded (%d chars)", len(response.text))
    return json.loads(response.text)


def _call_openai(user_message: str) -> dict[str, Any]:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai is not installed. Run: pip install openai")

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=OPENAI_API_KEY)
    logger.debug("chart_insight_agent: calling OpenAI (%s)", CHART_MODEL_OPENAI)
    response = client.chat.completions.create(
        model=CHART_MODEL_OPENAI,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    logger.debug("chart_insight_agent: OpenAI responded")
    raw = json.loads(response.choices[0].message.content)
    # Normalise in case OpenAI wraps the array
    if isinstance(raw.get("insights"), list):
        return raw
    for val in raw.values():
        if isinstance(val, dict) and "insights" in val:
            return val
    return raw


# ── Description prompt ────────────────────────────────────────────────────────

_DESC_SYSTEM_PROMPT = """\
You are describing a data visualization for a media operations dashboard.

Given the chart's title, type, and axis labels, write 1–2 sentences that explain:
1. What metric or dimension this chart tracks.
2. What analytical question it helps answer.

RULES (non-negotiable):
1. Max 35 words total.
2. Do not reference specific data values or time periods.
3. Focus on purpose, not content.
4. Return ONLY valid JSON — no markdown, no extra keys:
{"description": string}
"""


def _call_gemini_description(user_message: str) -> dict:
    try:
        import google.genai as genai
        import google.genai.types as genai_types
    except ImportError:
        raise ImportError("google-genai is not installed.")

    schema = genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={"description": genai_types.Schema(type=genai_types.Type.STRING)},
        required=["description"],
    )
    client = genai.Client(api_key=GOOGLE_API_KEY)
    response = client.models.generate_content(
        model=CHART_MODEL_GEMINI,
        contents=user_message,
        config={
            "system_instruction": _DESC_SYSTEM_PROMPT,
            "response_mime_type": "application/json",
            "response_schema": schema,
        },
    )
    return json.loads(response.text)


def _call_openai_description(user_message: str) -> dict:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai is not installed.")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=CHART_MODEL_OPENAI,
        messages=[
            {"role": "system", "content": _DESC_SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content)


def generate_chart_description(req: ChartDescriptionRequest) -> ChartDescriptionResponse:
    """
    Generate a static 1–2 sentence description of what a chart depicts.
    No data required — only uses chart metadata (title, type, axes).
    """
    parts = [
        f"Chart title: {req.chart_title}",
        f"Chart type: {req.chart_type}",
    ]
    if req.x_label:
        parts.append(f"X axis: {req.x_label}")
    if req.y_label:
        parts.append(f"Y axis: {req.y_label}")
    user_message = "\n".join(parts)

    logger.info("chart_insight_agent: generating description for '%s'", req.chart_title)

    if LLM_PROVIDER == "gemini":
        raw = _call_gemini_description(user_message)
    elif LLM_PROVIDER == "openai":
        raw = _call_openai_description(user_message)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'")

    return ChartDescriptionResponse(description=raw.get("description", ""))


# ── Public entry point ────────────────────────────────────────────────────────

def generate_chart_insights(req: ChartInsightRequest) -> ChartInsightResponse:
    """
    Call the LLM with the chart's data and return structured insights.
    Raises on LLM failure — caller should handle and return a 500.
    """
    if not req.data:
        logger.warning("chart_insight_agent: received empty data for chart '%s' — skipping LLM call", req.chart_title)
        return ChartInsightResponse(
            summary="No data available for this chart.",
            insights=["This chart currently has no data to analyse."],
        )

    model_name = CHART_MODEL_GEMINI if LLM_PROVIDER == "gemini" else CHART_MODEL_OPENAI
    logger.info(
        "chart_insight_agent: generating insights for '%s' (%s, %d rows) via %s/%s",
        req.chart_title, req.chart_type, len(req.data), LLM_PROVIDER, model_name,
    )

    user_message = _format_data(req)

    if LLM_PROVIDER == "gemini":
        raw = _call_gemini(user_message)
    elif LLM_PROVIDER == "openai":
        raw = _call_openai(user_message)
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'")

    n_insights = len(raw.get("insights", []))
    logger.info("chart_insight_agent: produced %d insight(s) for '%s'", n_insights, req.chart_title)

    return ChartInsightResponse(
        summary=raw.get("summary", ""),
        insights=raw.get("insights", []),
    )
