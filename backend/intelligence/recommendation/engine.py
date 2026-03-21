"""
Recommendation engine — orchestrates:
  expand context → format for LLM → call LLM → parse → cache → return
"""

import json
import logging
import re
import time
from datetime import datetime, timezone

from intelligence.recommendation.models import (
    DashboardContext,
    ExpandedContext,
    Recommendation,
    RecommendationResponse,
)
from intelligence.recommendation.context_expander import expand_context
from intelligence.recommendation.prompts import build_recommendation_prompt
import intelligence.recommendation.cache as rec_cache
from intelligence.shared.stats_summary import summarize_rows

# Reuse the LLM abstraction from the NLQ module
from intelligence.nlq.llm import call_llm_text as call_llm
from llm_config import QWEN_INSIGHT_MODEL

log = logging.getLogger("recommendation.engine")
_SEP = "─" * 52


def _extract_json(text: str) -> dict:
    """
    Robustly extract a JSON object from an LLM response that may contain
    conversational text, markdown code fences, or Qwen3 thinking tags.
    Priority: fenced block → brace scan.
    """
    # 1. Try ```json ... ``` or ``` ... ``` fences
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        return json.loads(fence.group(1))

    # 2. Scan for the outermost { ... } block
    start = text.find("{")
    if start != -1:
        end = text.rfind("}")
        if end > start:
            return json.loads(text[start:end + 1])

    raise ValueError(f"No JSON object found in LLM response: {text[:200]!r}")


def expand_only(ctx: DashboardContext, conn) -> tuple[ExpandedContext, bool]:
    """
    Phase 1 (needs DB): cache check + context expansion.
    Returns (expanded_context, cache_hit).  If cache_hit is True the caller
    can skip the LLM phase entirely.
    """
    cached = rec_cache.get(ctx)
    if cached:
        return cached, True  # type: ignore[return-value]

    t0 = time.perf_counter()
    expanded = expand_context(ctx, conn)
    log.info(f"[REC] Context expand  {time.perf_counter()-t0:.2f}s")
    return expanded, False


def get_recommendations(ctx: DashboardContext, expanded: ExpandedContext) -> RecommendationResponse:
    """
    Phase 2 (no DB needed): LLM call + response build.
    Accepts the pre-expanded context so the caller can release the DB conn first.
    """
    log.info(_SEP)
    log.info(f"[REC] view={ctx.view}  entity={ctx.entity_name}  role={ctx.user_role}")
    t_start = time.perf_counter()

    # ── 1. Build prompts (no DB needed) ────────────────────────────────────
    system_prompt = build_recommendation_prompt(ctx)
    user_message = _format_context(expanded)

    # ── 2. LLM call (slow — no DB conn held) ──────────────────────────────
    t1 = time.perf_counter()
    try:
        raw_text = call_llm(user_message, system_prompt, model=QWEN_INSIGHT_MODEL)
        # Strip Qwen3 thinking-mode tags before parsing
        cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
        llm_response = _extract_json(cleaned)
    except Exception as e:
        log.error(f"[REC] LLM call failed  ({time.perf_counter()-t1:.2f}s): {e}")
        llm_response = {"recommendations": [{
            "title": "AI Insight Generation Failed",
            "action": "Consider checking context length or API connection limits.",
            "rationale": "The configured insight model failed to process the statistical dashboard payload, returning an empty response.",
            "priority": "high",
            "scope": "network",
            "supporting_metrics": {}
        }]}

    log.info(f"[REC] LLM call  {time.perf_counter()-t1:.2f}s")

    # ── 3. Parse recommendations ──────────────────────────────────────────────
    recs = _parse_recommendations(llm_response)

    # ── 4. Build response, cache, return ─────────────────────────────────────
    response = RecommendationResponse(
        recommendations=recs,
        context_view=ctx.view,
        entity_name=ctx.entity_name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        cached=False,
    )

    rec_cache.set(ctx, response)

    total = time.perf_counter() - t_start
    log.info(f"[REC] Done  {total:.2f}s  → {len(recs)} recommendations")
    log.info(_SEP)

    return response


# ── helpers ────────────────────────────────────────────────────────────────────

def _format_context(expanded: ExpandedContext) -> str:
    """
    Serialize the 4 data sections into statistical summaries for the LLM.
    Each section is summarized with min/max/mean/std, categorical distributions,
    time-series trend, and top/bottom N rows — rather than raw row dumps.
    """
    parts = []

    # Benchmark may contain nested sub-sections (e.g. this_channel vs network_wide)
    def _benchmark_summary(rows: list[dict]) -> str:
        if not rows:
            return "### BENCHMARK\n(no data)\n"
        if rows and "section" in rows[0]:
            lines = ["### BENCHMARK"]
            for block in rows:
                sub = block.get("rows", [])
                lines.append(summarize_rows(sub, label=block.get("section", "").upper()))
            return "\n".join(lines) + "\n"
        return summarize_rows(rows, label="BENCHMARK")

    parts.append(summarize_rows(expanded.entity_profile, label="ENTITY PROFILE"))
    parts.append(summarize_rows(expanded.peer_comparison, label="PEER COMPARISON"))
    parts.append(summarize_rows(expanded.related_actors,  label="RELATED ACTORS"))
    parts.append(_benchmark_summary(expanded.benchmark))

    return "\n".join(parts)


def _parse_recommendations(llm_response: dict) -> list[Recommendation]:
    """
    Parse the LLM JSON response into Recommendation objects.
    Tolerates minor shape variations (list at root vs nested under 'recommendations').
    """
    raw = llm_response
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = raw.get("recommendations", [])
        if not items:
            # Some models wrap under a different key
            for v in raw.values():
                if isinstance(v, list):
                    items = v
                    break
    else:
        items = []

    recs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            recs.append(Recommendation(
                title=item.get("title", "Untitled"),
                action=item.get("action", ""),
                rationale=item.get("rationale", ""),
                priority=item.get("priority", "medium"),
                scope=item.get("scope", "network"),
                supporting_metrics=item.get("supporting_metrics", {}),
            ))
        except Exception as e:
            log.warning(f"[REC] Skipping malformed rec item: {e}")

    return recs
