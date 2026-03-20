"""
Role-aware system prompt builder for the recommendation agent.
"""

from intelligence.recommendation.models import DashboardContext
from intelligence.shared.profiles import ROLE_IDENTITIES, ROLE_COMPAT

_METRIC_LABELS = {
    "publish_rate_pct":   "publish rate (%)",
    "created_count":      "outputs created",
    "published_count":    "outputs published",
    "output_multiplier":  "output multiplier (outputs per upload)",
}

_VIEW_LABELS = {
    "channel_detail":    "channel performance detail",
    "user_detail":       "user performance detail",
    "content_mix":       "content mix breakdown",
    "executive_summary": "executive network overview",
    "trend_view":        "trend analysis",
}


def build_recommendation_prompt(ctx: DashboardContext) -> str:
    # Resolve backward-compat aliases before looking up the identity
    resolved_role = ROLE_COMPAT.get(ctx.user_role, ctx.user_role)
    role_text     = ROLE_IDENTITIES.get(resolved_role, ROLE_IDENTITIES["operations"])
    metric_label = _METRIC_LABELS.get(ctx.metric_in_focus, ctx.metric_in_focus)
    view_label   = _VIEW_LABELS.get(ctx.view, ctx.view)

    value_str = (
        f"{ctx.current_value:.1f}" if ctx.current_value is not None else "unknown"
    )

    return f"""{role_text}

The user is currently viewing the {view_label} for "{ctx.entity_name}".
The metric in focus is {metric_label}, currently at {value_str}.

You have been given 4 data sections pulled from a live analytics database:

  1. ENTITY PROFILE   — Full metrics for the entity currently in focus.
  2. PEER COMPARISON  — Up to 5 similar entities ranked by the focus metric.
  3. RELATED ACTORS   — People or entities connected to the focus (e.g. users on a channel, channels a user works on).
  4. BENCHMARK        — Top performers or content breakdown for reference.

─────────────────────────────────────────────────────────
INSTRUCTIONS
─────────────────────────────────────────────────────────
Generate 3 to 5 recommendations.

Each recommendation MUST:
  • Reference at least 2 data points from DIFFERENT sections.
    Good: entity profile metric + peer comparison rank + related actor gap.
    Bad: "Publish rate is low." (single metric, no cross-section reasoning)
  • Include a concrete, specific action — not "investigate further" or "look into this".
    Good: "Reassign one of Channel B's editors to CNN Hindi's interview queue."
    Bad: "Consider reviewing the QC process."
  • Name real entities (channels, users, content types) and real numbers from the data.
  • Set priority based on deviation from peer average:
      high   → delta > 30 percentage points from peer avg
      medium → delta 15–30 pp
      low    → delta < 15 pp or a growth opportunity with no urgency

Output a JSON object with a single key "recommendations" containing an array.
Each element must have exactly these keys:
  title              — short headline (max 12 words)
  action             — the specific next step (1–2 sentences)
  rationale          — the cross-dimensional reasoning with real numbers (2–4 sentences)
  priority           — "high" | "medium" | "low"
  scope              — "channel" | "user" | "content" | "network"
  supporting_metrics — dict of the 2–4 key metric values that drove this recommendation

Example element:
{{
  "title": "CNN Hindi publish rate 40pp below peer average",
  "action": "Review the QC handoff stage for CNN Hindi — specifically why 3 assigned users have 0 published outputs this month.",
  "rationale": "CNN Hindi's publish rate is 21.9% vs a peer average of 61.0% (PEER COMPARISON). Of the 4 users assigned to this channel, 3 have published 0 outputs despite creating 80+ (RELATED ACTORS). The network's top channel, IBN7, runs the same content volume with a 78% rate using 2 fewer users (BENCHMARK). The bottleneck is post-creation — not content volume.",
  "priority": "high",
  "scope": "channel",
  "supporting_metrics": {{"cnn_hindi_publish_rate": 21.9, "peer_avg_publish_rate": 61.0, "users_with_zero_published": 3, "ibn7_publish_rate": 78.0}}
}}
"""
