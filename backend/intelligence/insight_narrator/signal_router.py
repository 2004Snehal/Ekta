"""
Phase 4 — Signal Router.

Routes each signal to its tab destination and dashboard integration layer.
Also generates NLQ pre-filled queries for each signal.
"""

import logging
from intelligence.insight_narrator.schemas import FlaggedMetric

log = logging.getLogger("narrator.router")

# Maps insight_source → tab_destination
SOURCE_TO_TAB = {
    "anomaly":      "watchlist",
    "consecutive":  "watchlist",
    "cross_dim":    "watchlist",
    "milestone":    "watchlist",
    "funnel":       "pipeline",
    "op_risk":      "pipeline",
    "dq":           "data_governance",
}

# Metrics that map to dashboard KPIs
KPI_METRICS = {
    "publish_rate", "output_count", "upload_count",
    "created_count", "published_count", "avg_duration_secs",
}


def route_signals(
    signals: list[FlaggedMetric],
    resolved: list[FlaggedMetric],
) -> dict:
    """
    Route signals to their destinations.

    Returns dict with keys:
      watchlist, pipeline, data_governance — tab-routed signals
      kpi_insights — for dashboard SparkKPI dots
      dashboard_banner — top 3 for InsightBanner
      follow_ups — ongoing/worsening signals
      resolved — recovered signals
      top_signals — top 5 across all
    """

    routed = {
        "watchlist": {"flagged_metrics": [], "consecutive_trends": [],
                      "cross_dimension": [], "milestones": []},
        "pipeline": {"funnel_gaps": [], "operational_risks": [], "stalled_content": []},
        "data_governance": {"dq_issues": []},
        "kpi_insights": [],
        "dashboard_banner": [],
        "follow_ups": [],
        "top_signals": [],
    }

    severity_order = {"high": 3, "medium": 2, "low": 1}
    all_for_ranking: list[FlaggedMetric] = []

    for sig in signals:
        # Set tab destination
        sig.tab_destination = SOURCE_TO_TAB.get(sig.insight_source, "watchlist")

        # Generate NLQ query
        sig.nlq_query = _build_nlq_query(sig)

        # Route to tab sub-section
        if sig.insight_source == "anomaly":
            routed["watchlist"]["flagged_metrics"].append(sig)
        elif sig.insight_source == "consecutive":
            routed["watchlist"]["consecutive_trends"].append(sig)
        elif sig.insight_source == "cross_dim":
            routed["watchlist"]["cross_dimension"].append(sig)
        elif sig.insight_source == "milestone":
            routed["watchlist"]["milestones"].append(sig)
        elif sig.insight_source == "funnel":
            routed["pipeline"]["funnel_gaps"].append(sig)
        elif sig.insight_source == "op_risk":
            routed["pipeline"]["operational_risks"].append(sig)
        elif sig.insight_source == "dq":
            routed["data_governance"]["dq_issues"].append(sig)

        # Route to KPI layer (dashboard SparkKPI dots)
        if sig.metric_name in KPI_METRICS and sig.severity in ("high", "medium"):
            routed["kpi_insights"].append(sig)

        # Follow-ups
        if sig.status in ("ongoing", "worsening"):
            routed["follow_ups"].append(sig)

        # Track for ranking
        all_for_ranking.append(sig)

    # Top 5 across all signals (by severity then |delta|)
    all_for_ranking.sort(
        key=lambda s: (severity_order.get(s.severity, 0), abs(s.delta_pct)),
        reverse=True,
    )
    routed["top_signals"] = all_for_ranking[:5]

    # Dashboard banner: top 3 (highest severity, exclude milestones)
    banner_candidates = [
        s for s in all_for_ranking if s.insight_source != "milestone"
    ]
    routed["dashboard_banner"] = banner_candidates[:3]

    # Resolved signals
    for r in resolved:
        r.tab_destination = "pulse"
        r.nlq_query = _build_nlq_query(r)
    routed["resolved"] = resolved

    _log_routing(routed)
    return routed


def _build_nlq_query(sig: FlaggedMetric) -> str:
    """Build a pre-filled NLQ question from a signal."""

    entity = sig.entity_label
    metric = sig.metric_name.replace("_", " ")

    if sig.entity_type == "fleet":
        return f"Show me the overall {metric} trend for the last 6 months"

    if sig.insight_source == "cross_dim":
        dims = sig.dimensions or []
        if len(dims) >= 2:
            return f"Show me {dims[0]} by {dims[1]} breakdown for the last 3 months"

    if sig.insight_source == "funnel":
        return f"What is the publish conversion rate for {entity} by output type?"

    if sig.insight_source == "consecutive":
        return f"Show me {entity}'s {metric} trend for the last 6 months"

    return f"Show me {entity}'s {metric} for the last 6 months"


def _log_routing(routed: dict):
    counts = {
        "watchlist": sum(len(v) for v in routed["watchlist"].values()),
        "pipeline": sum(len(v) for v in routed["pipeline"].values()),
        "dq": len(routed["data_governance"]["dq_issues"]),
        "kpi": len(routed["kpi_insights"]),
        "banner": len(routed["dashboard_banner"]),
        "follow_ups": len(routed["follow_ups"]),
        "resolved": len(routed["resolved"]),
        "top": len(routed["top_signals"]),
    }
    log.info(f"[ROUTER] {counts}")
