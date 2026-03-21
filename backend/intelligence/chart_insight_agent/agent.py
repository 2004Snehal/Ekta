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
from llm_config import QWEN_CHART_INSIGHT_MODEL, make_openai_client, LLM_MAX_TOKENS

from intelligence.chart_insight_agent.schemas import (
    ChartInsightRequest, ChartInsightResponse,
    ChartDescriptionRequest, ChartDescriptionResponse,
)
from intelligence.shared.stats_summary import summarize_rows
from intelligence.shared.profiles import PROFILE_FRAMING

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
7. IMPORTANT: Ensure all strings use properly escaped quotes and avoid unescaped characters.
"""


# ── Data formatting ───────────────────────────────────────────────────────────

def _format_data(req: ChartInsightRequest) -> str:
    """
    Serialise the chart context into a statistical summary for the LLM.
    Replaces raw row dumps with computed min/max/mean/std, categorical
    distributions, time-series trend, and top/bottom N rows.
    """
    lines = [
        f"Chart title: {req.chart_title}",
        f"Chart type: {req.chart_type}",
    ]
    if req.x_label:
        lines.append(f"X axis: {req.x_label}")
    if req.y_label:
        lines.append(f"Y axis: {req.y_label}")

    lines.append(summarize_rows(req.data, label="Data"))

    return "\n".join(lines)


# ── LLM calls ─────────────────────────────────────────────────────────────────

def _call_openrouter(user_message: str, system_prompt: str = _SYSTEM_PROMPT) -> dict[str, Any]:
    client = make_openai_client()
    logger.debug("chart_insight_agent: calling OpenRouter (%s)", QWEN_CHART_INSIGHT_MODEL)
    response = client.chat.completions.create(
        model=QWEN_CHART_INSIGHT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
        max_tokens=LLM_MAX_TOKENS,
    )
    logger.debug("chart_insight_agent: OpenRouter responded")
    content = response.choices[0].message.content
    if not content:
        finish = response.choices[0].finish_reason
        raise ValueError(f"LLM returned empty content (finish_reason={finish!r})")
    
    # Clean markdown blocks if present (common with smaller/instruct models)
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        # find the first newline to skip ```json
        first_newline = cleaned_content.find("\\n")
        if first_newline != -1:
            cleaned_content = cleaned_content[first_newline+1:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3].strip()
            
    try:
        raw = json.loads(cleaned_content)
    except Exception as e:
        logger.warning("LLM JSON decode failed. Error: %s. Content: %s", e, cleaned_content)
        # Fallback to prevent 500 error on the frontend
        return {
            "summary": "Model output formatting issue detected.",
            "insights": [
                "The Llama 3.2 3B model returned a malformed response.",
                "Smaller models occasionally struggle with strict JSON formatting on complex charts.",
                "Please retry or switch to a larger reasoning model."
            ]
        }
        
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


def _call_openrouter_description(user_message: str) -> dict:
    client = make_openai_client()
    response = client.chat.completions.create(
        model=QWEN_CHART_INSIGHT_MODEL,
        messages=[
            {"role": "system", "content": _DESC_SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    if not content:
        finish = response.choices[0].finish_reason
        raise ValueError(f"LLM returned empty content for description (finish_reason={finish!r})")
    
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        first_newline = cleaned_content.find("\\n")
        if first_newline != -1:
            cleaned_content = cleaned_content[first_newline+1:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3].strip()
            
    return json.loads(cleaned_content)


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

    raw = _call_openrouter_description(user_message)

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

    # Build role-aware system prompt
    effective_prompt = _SYSTEM_PROMPT
    if req.user_role and req.user_role in PROFILE_FRAMING:
        effective_prompt = PROFILE_FRAMING[req.user_role] + "\n\n" + _SYSTEM_PROMPT

    logger.info(
        "chart_insight_agent: generating insights for '%s' (%s, %d rows) via %s",
        req.chart_title, req.chart_type, len(req.data), QWEN_CHART_INSIGHT_MODEL,
    )

    user_message = _format_data(req)
    try:
        raw = _call_openrouter(user_message, system_prompt=effective_prompt)
    except Exception as e:
        logger.error("OpenRouter API error in chart_insight_agent: %s", e)
        return ChartInsightResponse(
            summary="AI Insights temporarily unavailable.",
            insights=[
                "The AI model failed to generate insights (API or billing error).",
                str(e).split('\n')[0][:100] + "..."
            ]
        )
    n_insights = len(raw.get("insights", []))
    logger.info("chart_insight_agent: produced %d insight(s) for '%s'", n_insights, req.chart_title)

    return ChartInsightResponse(
        summary=raw.get("summary", ""),
        insights=raw.get("insights", []),
    )
