"""
Recommendation engine — orchestrates:
  expand context → format for LLM → call LLM → parse → cache → return
"""

import json
import logging
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

# Reuse the LLM abstraction from the NLQ module
from intelligence.nlq.llm import call_llm_text as call_llm

log = logging.getLogger("recommendation.engine")
_SEP = "─" * 52


def get_recommendations(ctx: DashboardContext, conn) -> RecommendationResponse:
    log.info(_SEP)
    log.info(f"[REC] view={ctx.view}  entity={ctx.entity_name}  role={ctx.user_role}")
    t_start = time.perf_counter()

    # ── 1. Cache check ────────────────────────────────────────────────────────
    cached = rec_cache.get(ctx)
    if cached:
        log.info(f"[REC] Cache hit  ({time.perf_counter()-t_start:.2f}s)")
        result = cached.model_copy()
        result.cached = True
        return result

    # ── 2. Context expansion (SQL queries) ────────────────────────────────────
    t0 = time.perf_counter()
    expanded = expand_context(ctx, conn)
    log.info(f"[REC] Context expand  {time.perf_counter()-t0:.2f}s")

    # ── 3. Build system prompt ────────────────────────────────────────────────
    system_prompt = build_recommendation_prompt(ctx)

    # ── 4. Format expanded context as the user message ────────────────────────
    user_message = _format_context(expanded)

    # ── 5. LLM call ───────────────────────────────────────────────────────────
    t1 = time.perf_counter()
    try:
        raw_text = call_llm(user_message, system_prompt)
        llm_response = json.loads(raw_text.strip().removeprefix("```json").removesuffix("```").strip())
    except Exception as e:
        log.error(f"[REC] LLM call failed  ({time.perf_counter()-t1:.2f}s): {e}")
        raise

    log.info(f"[REC] LLM call  {time.perf_counter()-t1:.2f}s")

    # ── 6. Parse recommendations ──────────────────────────────────────────────
    recs = _parse_recommendations(llm_response)

    # ── 7. Build response, cache, return ─────────────────────────────────────
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
    Serialize the 4 data sections into labelled text blocks.
    Keeps total context under ~2000 tokens by capping rows per section.
    """
    parts = []

    def _section(label: str, rows: list[dict], limit: int = 10) -> str:
        if not rows:
            return f"## {label}\n(no data)\n"
        sample = rows[:limit]
        # Special case: benchmark can be a list of dicts with nested "rows"
        if sample and "section" in sample[0]:
            lines = [f"## {label}"]
            for block in sample:
                lines.append(f"### {block.get('section', '').upper()}")
                sub = block.get("rows", [])[:limit]
                if sub:
                    lines.append(" | ".join(str(k) for k in sub[0].keys()))
                    for r in sub:
                        lines.append(" | ".join(str(v) for v in r.values()))
                else:
                    lines.append("(no data)")
            return "\n".join(lines) + "\n"

        header = " | ".join(str(k) for k in sample[0].keys())
        data_rows = "\n".join(
            " | ".join(str(v) for v in row.values()) for row in sample
        )
        return f"## {label}\n{header}\n{data_rows}\n"

    parts.append(_section("ENTITY PROFILE",  expanded.entity_profile))
    parts.append(_section("PEER COMPARISON",  expanded.peer_comparison))
    parts.append(_section("RELATED ACTORS",   expanded.related_actors))
    parts.append(_section("BENCHMARK",        expanded.benchmark))

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
