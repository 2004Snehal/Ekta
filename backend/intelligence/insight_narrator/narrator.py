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
from llm_config import QWEN_INSIGHT_MODEL, make_openai_client, LLM_MAX_TOKENS

from intelligence.insight_narrator.schemas import FlaggedMetric, InsightCard
from intelligence.shared.profiles import PROFILE_FRAMING

logger = logging.getLogger(__name__)


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

def _call_llm_json_array(user_message: str, system_prompt: str) -> list[dict]:
    return _openrouter_narrator(user_message, system_prompt=system_prompt)


def _openrouter_narrator(user_message: str, system_prompt: str) -> list[dict]:
    client = make_openai_client()
    response = _retry(lambda: client.chat.completions.create(
        model=QWEN_INSIGHT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
        max_tokens=LLM_MAX_TOKENS,
    ))
    raw = json.loads(response.choices[0].message.content)
    # json_object may wrap the array in a top-level key
    if isinstance(raw, list):
        return raw
    for val in raw.values():
        if isinstance(val, list):
            return val
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# Parallel narration across 3 signal batches
# ═══════════════════════════════════════════════════════════════════════════════

from concurrent.futures import ThreadPoolExecutor, as_completed
from intelligence.insight_narrator.prompts_v2 import (
    URGENT_PROMPT, ANALYTICAL_PROMPT, OPERATIONAL_PROMPT, DIGEST_PROMPT,
)


def _format_evidence_v2(metrics: list[FlaggedMetric]) -> str:
    """Format evidence with v2 fields (status, consecutive, suggested_action)."""
    lines = []
    for i, m in enumerate(metrics, 1):
        direction = "up" if m.delta_pct > 0 else "down"
        parts = [
            f"{i}. {m.entity_type.title()} «{m.entity_label}» — "
            f"{m.metric_name.replace('_', ' ')} {direction} {abs(m.delta_pct):.1f}% "
            f"(current: {m.current_value:.2f}, baseline: {m.reference_value:.2f}). "
            f"Severity: {m.severity}."
        ]
        if m.status and m.status != "new":
            parts.append(f" Status: {m.status}.")
        if m.consecutive_periods and m.consecutive_periods > 1:
            parts.append(f" Consecutive periods: {m.consecutive_periods}.")
        if m.root_cause_breakdown:
            drivers = "; ".join(
                f"{d.get('dimension','')}: {d.get('driver_label','')} ({d.get('contribution_pct',0):.0f}%)"
                for d in m.root_cause_breakdown[:2]
            )
            parts.append(f" Root cause breakdown: {drivers}.")
        if m.suggested_action:
            parts.append(f" Context: {m.suggested_action}")
        lines.append("".join(parts))
    return "\n".join(lines)


def _make_template_card(m: FlaggedMetric) -> InsightCard:
    """
    Create a card from a signal WITHOUT any LLM call.
    Used as fallback when the API is unavailable or rate-limited.
    Produces clear, factual insight cards that are fully functional.
    """
    direction = "increased" if m.delta_pct > 0 else "decreased"
    abs_delta = abs(m.delta_pct)
    metric_label = m.metric_name.replace("_", " ")

    # --- Title (concise, factual) ---
    if m.insight_source == "consecutive":
        periods = m.consecutive_periods or 3
        dir_word = "rising" if m.delta_pct > 0 else "declining"
        title = f"{m.entity_label}: {metric_label} {dir_word} for {periods} months"
    elif m.insight_source == "milestone":
        title = f"{m.entity_label} reached a new record in {metric_label}"
    elif m.insight_source == "op_risk":
        if m.metric_name == "days_inactive":
            title = f"{m.entity_label} has been inactive for {int(m.current_value)} days"
        elif m.metric_name == "spof_output_type":
            title = f"{m.entity_label} is the sole producer of this content type"
        elif m.metric_name == "user_concentration":
            title = f"Fleet output is concentrated in top 2 users ({m.current_value:.0f}%)"
        else:
            title = f"Operational risk: {m.entity_label} — {metric_label}"
    elif m.insight_source == "funnel":
        title = f"{m.entity_label}: publish rate {abs_delta:.1f}% below fleet average"
    elif m.insight_source == "dq":
        title = f"Data quality issue: {metric_label} in {m.entity_label}"
    elif m.insight_source == "cross_dim":
        title = f"Unusual pattern detected: {m.entity_label} — {metric_label}"
    else:
        title = f"{m.entity_label}: {metric_label} {direction} {abs_delta:.1f}%"

    # Clamp title length
    if len(title) > 80:
        title = title[:77] + "..."

    # --- Body (2 factual sentences) ---
    body_parts: list[str] = []

    if m.insight_source in ("anomaly", "consecutive"):
        body_parts.append(
            f"The {metric_label} for {m.entity_label} {direction} by {abs_delta:.1f}% "
            f"compared to the 3-month average "
            f"(current: {m.current_value:.1f}, baseline: {m.reference_value:.1f})."
        )
        if m.insight_source == "consecutive":
            periods = m.consecutive_periods or 3
            body_parts.append(
                f"This directional movement has persisted for {periods} consecutive months, "
                f"indicating a structural shift rather than a one-off spike."
            )
        elif m.delta_pct > 0:
            body_parts.append(
                f"This rise is above the expected range and warrants investigation "
                f"into whether it reflects genuine growth or a data anomaly."
            )
        else:
            body_parts.append(
                f"This decline is outside the expected range and may require "
                f"editorial or operational intervention."
            )
    elif m.insight_source == "op_risk":
        if m.suggested_action:
            body_parts.append(m.suggested_action)
        else:
            body_parts.append(
                f"An operational risk was detected for {m.entity_label}. "
                f"This represents a structural vulnerability in your platform's workflow."
            )
            body_parts.append("Review team assignments and content distribution to reduce single points of failure.")
    elif m.insight_source == "funnel":
        body_parts.append(
            f"{m.entity_label} has a publish rate of {m.current_value:.1f}%, "
            f"compared to the fleet average of {m.reference_value:.1f}%."
        )
        body_parts.append(
            "Uploaded content is not completing the publish pipeline at the expected rate. "
            "Check for editorial backlogs or technical publish failures."
        )
    elif m.insight_source == "dq":
        body_parts.append(m.suggested_action or f"A data quality issue was detected in {m.entity_label}.")
        body_parts.append("Fixing this will improve the accuracy of all reports and AI-generated analysis.")
    elif m.insight_source == "milestone":
        body_parts.append(
            f"{m.entity_label} achieved a new record: {metric_label} reached {m.current_value:.1f}, "
            f"surpassing the previous best of {m.reference_value:.1f}."
        )
        body_parts.append("This positive milestone reflects sustained improvement and is worth recognising.")
    elif m.insight_source == "cross_dim":
        body_parts.append(
            f"An unusual combination was detected: {m.entity_label} shows a {metric_label} "
            f"of {m.current_value:.1f} — {abs_delta:.1f}% different from the expected baseline."
        )
        body_parts.append("This cross-dimension pattern may reveal an untapped opportunity or an emerging issue.")
    else:
        body_parts.append(
            f"The {metric_label} for {m.entity_label} {direction} by {abs_delta:.1f}% "
            f"(current: {m.current_value:.1f}, baseline: {m.reference_value:.1f})."
        )
        body_parts.append(m.suggested_action or "Review recent activity to understand the cause of this change.")

    # Category mapping
    category_map = {
        "anomaly": "anomaly", "consecutive": "trend", "cross_dim": "comparison",
        "milestone": "milestone", "funnel": "operational", "op_risk": "operational",
        "dq": "data_quality",
    }

    return InsightCard(
        title=title,
        body=" ".join(body_parts),
        category=category_map.get(m.insight_source, "anomaly"),
        severity=m.severity,
        metric_name=m.metric_name,
        entity_type=m.entity_type,
        entity_id=str(m.entity_id),
        current_value=m.current_value,
        reference_value=m.reference_value,
        delta_pct=m.delta_pct,
        period=m.period,
        confidence="statistical",
        root_cause_hint=None,
        status=m.status,
        suggested_action=m.suggested_action,
        insight_source=m.insight_source,
        tab_destination=getattr(m, "tab_destination", "watchlist"),
        consecutive_periods=m.consecutive_periods,
        root_cause_breakdown=m.root_cause_breakdown,
        actionability_score=m.actionability_score,
        nlq_query=getattr(m, "nlq_query", None),
    )


def _narrate_batch(
    metrics: list[FlaggedMetric],
    system_prompt: str,
    profile: str | None = None,
) -> list[InsightCard]:
    """
    Narrate a single batch of signals.
    Tries LLM first; falls back to template cards if the API fails.
    """

    if not metrics:
        return []

    if profile and profile in PROFILE_FRAMING:
        effective = PROFILE_FRAMING[profile] + "\n\n" + system_prompt
    else:
        effective = system_prompt

    evidence = _format_evidence_v2(metrics)

    try:
        raw_cards = _call_llm_json_array(evidence, system_prompt=effective)
    except Exception as e:
        logger.warning("v2 narrate batch LLM failed — using template cards: %s", e)
        return [_make_template_card(m) for m in metrics]

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
                severity         = m.severity,
                metric_name      = m.metric_name,
                entity_type      = m.entity_type,
                entity_id        = m.entity_id,
                current_value    = m.current_value,
                reference_value  = m.reference_value,
                delta_pct        = m.delta_pct,
                period           = m.period,
                confidence       = "statistical",
                root_cause_hint  = raw.get("root_cause_hint"),
                # v2 fields
                status           = m.status,
                suggested_action = raw.get("suggested_action") or m.suggested_action,
                insight_source   = m.insight_source,
                tab_destination  = getattr(m, "tab_destination", "watchlist"),
                consecutive_periods = m.consecutive_periods,
                root_cause_breakdown = m.root_cause_breakdown,
                actionability_score = m.actionability_score,
                nlq_query        = getattr(m, "nlq_query", None),
            )
            cards.append(card)
        except Exception as e:
            logger.warning("v2 parse card %d failed: %s", i, e)

    return cards


def narrate_v2(
    routed: dict,
    profile: str | None = None,
) -> tuple[list[InsightCard], str | None]:
    """
    Narrate signals in 3 parallel batches + 1 digest call.

    Args:
        routed: output of signal_router.route_signals()
        profile: user profile for tone framing

    Returns (all_cards, digest_text)
    """

    # Build the 3 batches from routed signals
    urgent_signals: list[FlaggedMetric] = []
    analytical_signals: list[FlaggedMetric] = []
    operational_signals: list[FlaggedMetric] = []

    # Urgent: flagged anomalies (high/medium) + worsening follow-ups
    for sig in routed.get("watchlist", {}).get("flagged_metrics", []):
        if hasattr(sig, "severity"):
            urgent_signals.append(sig)
    for sig in routed.get("follow_ups", []):
        if hasattr(sig, "status") and sig.status == "worsening":
            urgent_signals.append(sig)

    # Analytical: trends + cross-dim + milestones
    for key in ["consecutive_trends", "cross_dimension", "milestones"]:
        for sig in routed.get("watchlist", {}).get(key, []):
            analytical_signals.append(sig)

    # Operational: funnel gaps + op risks + DQ
    for key in ["funnel_gaps", "operational_risks", "stalled_content"]:
        for sig in routed.get("pipeline", {}).get(key, []):
            operational_signals.append(sig)
    for sig in routed.get("data_governance", {}).get("dq_issues", []):
        operational_signals.append(sig)

    # Fire 3 calls in parallel
    all_cards: list[InsightCard] = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {}
        if urgent_signals:
            futures[pool.submit(_narrate_batch, urgent_signals, URGENT_PROMPT, profile)] = "urgent"
        if analytical_signals:
            futures[pool.submit(_narrate_batch, analytical_signals, ANALYTICAL_PROMPT, profile)] = "analytical"
        if operational_signals:
            futures[pool.submit(_narrate_batch, operational_signals, OPERATIONAL_PROMPT, profile)] = "operational"

        for future in as_completed(futures):
            label = futures[future]
            try:
                cards = future.result()
                all_cards.extend(cards)
                logger.info(f"v2 narrate [{label}]: {len(cards)} cards")
            except Exception as e:
                logger.error(f"v2 narrate [{label}] failed: {e}")

    # Resolved signals → template strings, no LLM
    for sig in routed.get("resolved", []):
        all_cards.append(InsightCard(
            title=f"Resolved: {sig.entity_label} {sig.metric_name.replace('_', ' ')}",
            body=f"Previously flagged issue has recovered. This was tracked for {sig.consecutive_periods or 1} period(s).",
            category="milestone",
            severity="low",
            metric_name=sig.metric_name,
            entity_type=sig.entity_type,
            entity_id=sig.entity_id,
            current_value=sig.current_value,
            reference_value=sig.reference_value,
            delta_pct=sig.delta_pct,
            period=sig.period,
            status="resolved",
            insight_source=sig.insight_source,
            tab_destination="pulse",
        ))

    # Digest call (sequential, after narration)
    all_metrics = urgent_signals + analytical_signals + operational_signals
    period = all_metrics[0].period if all_metrics else ""
    digest = _generate_digest_v2(all_metrics, period)

    logger.info(f"v2 narrate total: {len(all_cards)} cards, digest={'yes' if digest else 'no'}")
    return all_cards, digest


def _generate_digest_v2(metrics: list[FlaggedMetric], period: str) -> str | None:
    """Generate period digest with v2 context."""
    if not metrics:
        return None

    by_source = {}
    for m in metrics:
        by_source.setdefault(m.insight_source, []).append(m)

    summary_lines = [f"Period: {period}"]
    summary_lines.append(f"Total signals: {len(metrics)}")
    for source, sigs in by_source.items():
        high = sum(1 for s in sigs if s.severity == "high")
        summary_lines.append(f"  {source}: {len(sigs)} ({high} high severity)")

    for m in metrics[:7]:
        direction = "up" if m.delta_pct > 0 else "down"
        status_str = f" [{m.status}]" if m.status != "new" else ""
        summary_lines.append(
            f"- {m.entity_label}: {m.metric_name.replace('_', ' ')} "
            f"{direction} {abs(m.delta_pct):.1f}%{status_str}"
        )

    try:
        client = make_openai_client()
        resp = _retry(lambda: client.chat.completions.create(
            model=QWEN_INSIGHT_MODEL,
            messages=[
                {"role": "system", "content": DIGEST_PROMPT},
                {"role": "user",   "content": "\n".join(summary_lines)},
            ],
        ))
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.warning("v2 digest LLM failed — using template digest: %s", e)
        return _make_template_digest(metrics, period)


def _make_template_digest(metrics: list[FlaggedMetric], period: str) -> str:
    """Generate a plain-English digest without LLM."""
    if not metrics:
        return f"No significant signals detected for {period}. All monitored metrics are within expected ranges."

    total = len(metrics)
    high = [m for m in metrics if m.severity == "high"]
    medium = [m for m in metrics if m.severity == "medium"]

    by_source: dict[str, int] = {}
    for m in metrics:
        by_source[m.insight_source] = by_source.get(m.insight_source, 0) + 1

    parts = [
        f"The platform recorded {total} signal{'s' if total != 1 else ''} during {period}."
    ]

    if high:
        top_entities = list(dict.fromkeys(m.entity_label for m in high))[:3]
        parts.append(
            f"{len(high)} high-severity issue{'s' if len(high) != 1 else ''} "
            f"{'were' if len(high) != 1 else 'was'} detected, "
            f"affecting {', '.join(top_entities)}."
        )

    if medium:
        parts.append(
            f"An additional {len(medium)} medium-severity pattern{'s' if len(medium) != 1 else ''} "
            f"{'are' if len(medium) != 1 else 'is'} worth monitoring."
        )

    source_phrases = {
        "anomaly": "metric anomalies", "consecutive": "multi-month trends",
        "funnel": "funnel gaps", "op_risk": "operational risks",
        "dq": "data quality issues", "milestone": "positive milestones",
        "cross_dim": "cross-dimension patterns",
    }
    detected_types = [source_phrases.get(k, k) for k in by_source if k != "anomaly"]
    if detected_types:
        parts.append(f"The analysis also identified {', '.join(detected_types[:3])}.")

    return " ".join(parts)
