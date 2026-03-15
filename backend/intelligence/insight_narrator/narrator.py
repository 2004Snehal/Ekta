"""
LLM Narrator — Step 4 of the Insight Narrator pipeline.

Receives a pre-flagged, pre-deduplicated list of FlaggedMetric objects
and calls the LLM to produce InsightCard objects (title + body + category).

Rules enforced by design:
- LLM does NOT detect anomalies (already done by detector.py)
- LLM does NOT assign severity (already done by detector.py)
- LLM only writes: title, body, category, root_cause_hint
- JSON enforcement via Gemini response_schema or OpenAI response_format
"""

from __future__ import annotations
import json
import logging
import os
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from backend_config import LLM_PROVIDER, LLM_MODEL, GOOGLE_API_KEY, OPENAI_API_KEY

from intelligence.insight_narrator.schemas import FlaggedMetric, InsightCard

logger = logging.getLogger(__name__)


# ── System prompt ─────────────────────────────────────────────────────────────

_NARRATOR_SYSTEM = """\
You are a media operations analyst generating insight cards for a media analytics platform.

You will receive a numbered list of pre-flagged metrics. For EACH metric write an insight card.

RULES (non-negotiable):
1. Do NOT change the severity — it is pre-assigned and read-only.
2. Do NOT invent patterns or causes not present in the evidence.
3. Do NOT use the word "significant".
4. Title: max 12 words, plain English.
5. Body: exactly 2–3 sentences, plain English, no jargon.
   - Reference the actual numbers (delta_pct, current_value, reference_value).
   - State what happened, then briefly why it matters.
6. category must be EXACTLY one of: anomaly | trend | comparison | milestone
   - anomaly   → single-period outlier vs historical baseline
   - trend     → multi-period directional movement (flag only if evidence spans 2+ periods)
   - comparison → cross-channel or cross-user relative gap
   - milestone  → first time a threshold was crossed
   For single-month data with no multi-period context, default to "anomaly".
7. root_cause_hint: one sentence max, or null if you cannot infer a plausible cause.
8. Return ONLY a JSON array. No preamble, no markdown, no extra keys.

Each element of the array must match:
{
  "title": string,
  "body": string,
  "category": "anomaly"|"trend"|"comparison"|"milestone",
  "root_cause_hint": string|null
}
"""


# ── Evidence formatting ───────────────────────────────────────────────────────

def _format_evidence(metrics: list[FlaggedMetric]) -> str:
    lines = []
    for i, m in enumerate(metrics, 1):
        direction = "up" if m.delta_pct > 0 else "down"
        lines.append(
            f"{i}. {m.entity_type.title()} «{m.entity_label}» — "
            f"{m.metric_name.replace('_', ' ')} {direction} {abs(m.delta_pct):.1f}% MoM "
            f"(current: {m.current_value:.2f}, 3m avg: {m.reference_value:.2f}). "
            f"Severity: {m.severity}."
            + (f" Z-score: {m.zscore:.1f}." if m.zscore is not None else "")
        )
    return "\n".join(lines)


# ── Retry helper ──────────────────────────────────────────────────────────────

def _retry(fn, retries: int = 3, backoff: float = 5.0):
    """Call fn(), retrying up to `retries` times on 429 / rate-limit errors."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            msg = str(e)
            is_rate_limit = "429" in msg or "RESOURCE_EXHAUSTED" in msg or "rate" in msg.lower()
            if is_rate_limit and attempt < retries - 1:
                wait = backoff * (2 ** attempt)
                logger.warning("rate limit hit — retrying in %.0fs (attempt %d/%d)", wait, attempt + 1, retries)
                time.sleep(wait)
            else:
                raise


# ── LLM call (JSON array) ─────────────────────────────────────────────────────

def _call_llm_json_array(user_message: str) -> list[dict]:
    if LLM_PROVIDER == "gemini":
        return _gemini_narrator(user_message)
    elif LLM_PROVIDER == "openai":
        return _openai_narrator(user_message)
    raise ValueError(f"Unknown LLM_PROVIDER '{LLM_PROVIDER}'")


def _gemini_narrator(user_message: str) -> list[dict]:
    try:
        import google.genai as genai
        import google.genai.types as genai_types
    except ImportError:
        raise ImportError("google-genai is not installed. Run: pip install google-genai")

    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY is not set in .env")

    # Enforce JSON array schema at the API level
    insight_schema = genai_types.Schema(
        type=genai_types.Type.ARRAY,
        items=genai_types.Schema(
            type=genai_types.Type.OBJECT,
            properties={
                "title":            genai_types.Schema(type=genai_types.Type.STRING),
                "body":             genai_types.Schema(type=genai_types.Type.STRING),
                "category":         genai_types.Schema(type=genai_types.Type.STRING),
                "root_cause_hint":  genai_types.Schema(type=genai_types.Type.STRING),
            },
            required=["title", "body", "category"],
        ),
    )

    client = genai.Client(api_key=GOOGLE_API_KEY)
    response = _retry(lambda: client.models.generate_content(
        model=LLM_MODEL,
        contents=user_message,
        config={
            "system_instruction": _NARRATOR_SYSTEM,
            "response_mime_type": "application/json",
            "response_schema":    insight_schema,
        },
    ))
    return json.loads(response.text)


def _openai_narrator(user_message: str) -> list[dict]:
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai is not installed. Run: pip install openai")

    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _NARRATOR_SYSTEM},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    raw = json.loads(response.choices[0].message.content)
    # OpenAI json_object wraps in a top-level key when returning arrays
    if isinstance(raw, list):
        return raw
    for val in raw.values():
        if isinstance(val, list):
            return val
    return []


# ── Digest generation ─────────────────────────────────────────────────────────

_DIGEST_SYSTEM = """\
You are a media operations analyst. Write a single paragraph (3–5 sentences) summarising
the platform's overall performance for the period described. Be factual, reference numbers,
and state what is notable. Do not use the word "significant". Return plain text only.
"""


def _generate_digest(metrics: list[FlaggedMetric], period: str) -> Optional[str]:
    if not metrics:
        return None

    high   = [m for m in metrics if m.severity == "high"]
    medium = [m for m in metrics if m.severity == "medium"]
    summary_lines = [
        f"Period: {period}",
        f"Total anomalies flagged: {len(metrics)} "
        f"({len(high)} high severity, {len(medium)} medium).",
    ]
    for m in metrics[:5]:
        direction = "up" if m.delta_pct > 0 else "down"
        summary_lines.append(
            f"- {m.entity_label} {m.metric_name.replace('_', ' ')} {direction} "
            f"{abs(m.delta_pct):.1f}%."
        )
    user_message = "\n".join(summary_lines)

    try:
        if LLM_PROVIDER == "gemini":
            import google.genai as genai
            client = genai.Client(api_key=GOOGLE_API_KEY)
            resp = _retry(lambda: client.models.generate_content(
                model=LLM_MODEL,
                contents=user_message,
                config={"system_instruction": _DIGEST_SYSTEM},
            ))
            return resp.text.strip()
        elif LLM_PROVIDER == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[
                    {"role": "system", "content": _DIGEST_SYSTEM},
                    {"role": "user",   "content": user_message},
                ],
            )
            return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("digest generation failed: %s", e)
    return None


# ── Public entry point ────────────────────────────────────────────────────────

def narrate(
    metrics: list[FlaggedMetric],
    include_digest: bool = True,
) -> tuple[list[InsightCard], Optional[str]]:
    """
    Calls the LLM to produce InsightCard objects for each FlaggedMetric.

    Returns (insight_cards, digest_text).
    On LLM failure, logs the error and returns empty lists — the pipeline
    will serve the previous cache rather than surfacing broken data.
    """
    if not metrics:
        return [], None

    evidence     = _format_evidence(metrics)
    period       = metrics[0].period
    digest_text  = _generate_digest(metrics, period) if include_digest else None

    try:
        raw_cards = _call_llm_json_array(evidence)
    except Exception as e:
        logger.error("narrator LLM call failed: %s", e)
        return [], digest_text

    cards: list[InsightCard] = []
    for i, raw in enumerate(raw_cards):
        if i >= len(metrics):
            break
        m = metrics[i]
        try:
            card = InsightCard(
                title            = raw.get("title", "Untitled insight"),
                body             = raw.get("body", ""),
                category         = raw.get("category", "anomaly"),
                severity         = m.severity,         # Python-owned, not LLM
                metric_name      = m.metric_name,
                entity_type      = m.entity_type,
                entity_id        = m.entity_id,
                current_value    = m.current_value,
                reference_value  = m.reference_value,
                delta_pct        = m.delta_pct,
                period           = m.period,
                confidence       = "statistical",
                root_cause_hint  = raw.get("root_cause_hint") or None,
            )
            cards.append(card)
        except Exception as e:
            logger.warning("failed to parse card %d: %s — raw: %s", i, e, raw)

    logger.info("narrator: produced %d insight cards", len(cards))
    return cards, digest_text
