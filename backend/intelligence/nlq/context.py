"""
Semantic context loader for the NLQ system prompt.

Loads metric and dimension definitions from MetricFlow YAML files at runtime,
so the prompt stays in sync with the semantic layer without manual edits.
Falls back gracefully if YAMLs are unavailable.
"""

import yaml
from pathlib import Path

SEMANTIC_DIR  = Path(__file__).resolve().parent.parent.parent / "semantic"
_METRICS_FILE = SEMANTIC_DIR / "models" / "semantic" / "_metrics.yml"
_SEMANTIC_FILE = SEMANTIC_DIR / "models" / "semantic" / "_semantic__created_videos.yml"

# ── Raw SQL schema — used only for the SQL fallback path ──────────────────────
_RAW_SCHEMA = """
DATABASE: PostgreSQL — Frammer AI media operations analytics platform.

=== FACT TABLE ===
fact_created_videos  (one row per created video output)
  id, video_id, client_id, channel_id, user_id, team_id,
  input_type_id, output_type_id, language_id,
  headline, source_url,
  uploaded_duration_secs, created_duration_secs, published_duration_secs,
  uploaded_at, published_flag, published_platform_id, published_url

=== DIMENSION TABLES ===
dim_client:      client_id, client_name, plan_type, industry, region, is_active
dim_channel:     channel_id, client_id, channel_name, channel_code, primary_language, is_active
dim_user:        user_id, client_id, user_name, role ('editor'/'auto'), is_bot
dim_team:        team_id, client_id, team_name
dim_input_type:  input_type_id, type_name, category
                 -- type_name: interview, news bulletin, speech, special reports,
                 --   debate, press conference, discussion-show, sports show, podcast, drama, in-brief
dim_output_type: output_type_id, type_name, is_short_form
                 -- type_name: Full package, Key moments, My Key moments, Chapters, Summary
dim_language:    language_id, language_code, language_name
                 -- codes: en, hi, mix, es, ar, mr
dim_platform:    platform_id, platform_name
                 -- names: YouTube, Reels, Shorts, Instagram, Facebook, LinkedIn, X, Threads
user_channel_map: user_id, channel_id

=== MATERIALIZED VIEWS (prefer for aggregate SQL queries) ===
mv_monthly_kpis:      client_id, channel_id, input_type_id, output_type_id, language_id,
                      month (DATE), created_count, total_uploaded_duration_secs,
                      total_created_duration_secs, published_count, publish_rate_pct
mv_channel_health:    client_id, channel_id, total_created, total_published,
                      publish_rate_pct, active_users, last_activity
mv_user_performance:  client_id, channel_id, user_id, created_count, published_count,
                      total_uploaded_duration_secs, total_created_duration_secs, publish_rate_pct

=== KEY METRIC DEFINITIONS ===
- "uploads" / "source videos"   = COUNT(DISTINCT video_id)
- "created outputs"             = COUNT(*) from fact_created_videos
- "published"                   = published_flag = TRUE
- "publish rate"                = published_count / created_count * 100
- "output multiplier"           = COUNT(*) / COUNT(DISTINCT video_id)
"""


def _load_metrics() -> list[dict]:
    """Load metric definitions from _metrics.yml."""
    try:
        with open(_METRICS_FILE) as f:
            data = yaml.safe_load(f)
        return [
            {
                "name": m["name"],
                "type": m.get("type", ""),
                "description": str(m.get("description", "")).strip(),
            }
            for m in data.get("metrics", [])
        ]
    except FileNotFoundError:
        return []


def _load_dimensions() -> list[dict]:
    """Load dimension definitions from the semantic model YAML."""
    try:
        with open(_SEMANTIC_FILE) as f:
            data = yaml.safe_load(f)
        dims = []
        for sm in data.get("semantic_models", []):
            for d in sm.get("dimensions", []):
                dims.append({
                    "name": d["name"],
                    "type": d.get("type", "categorical"),
                    "description": d.get("description", ""),
                })
        return dims
    except FileNotFoundError:
        return []


def build_system_prompt(client_id: int) -> str:
    """
    Build the full NLQ system prompt with:
    - Raw SQL schema (for SQL path)
    - MetricFlow metric + dimension listings (for MetricFlow path)
    - Routing rules
    - Dual output format
    """
    metrics    = _load_metrics()
    dimensions = _load_dimensions()

    metric_lines = "\n".join(
        f"  - {m['name']} ({m['type']}): {m['description']}"
        for m in metrics
    )
    metric_names = ", ".join(m["name"] for m in metrics)

    dim_lines = "\n".join(
        f"  - {d['name']} ({d['type']})"
        + (f" — {d['description']}" if d["description"] else "")
        for d in dimensions
        if d["name"] != "created_at"  # excluded, shown separately below
    )
    dim_names = ", ".join(
        d["name"] for d in dimensions if d["name"] != "created_at"
    )

    return f"""You are an analytics query router for Frammer AI, a media video processing platform.
Your job is to pick the right execution path and generate the correct query parameters.

{_RAW_SCHEMA}

=== METRICFLOW SEMANTIC LAYER ===

Available metrics (use these exact names):
{metric_lines}

Available dimensions (use EXACTLY these names in group_by — all prefixed with video_output__):
  - metric_time                       (time)       — use for ALL time/trend breakdowns
  - video_output__channel_name        (categorical)
  - video_output__channel_code        (categorical)
  - video_output__channel_content_focus (categorical)
  - video_output__user_name           (categorical)
  - video_output__user_role           (categorical) — 'editor' or 'auto'
  - video_output__is_bot              (categorical) — TRUE for Auto Upload users
  - video_output__team_name           (categorical)
  - video_output__input_type_name     (categorical) — interview, news bulletin, speech, debate, etc.
  - video_output__input_type_category (categorical) — live, recorded, scripted
  - video_output__output_type_name    (categorical) — Full package, Key moments, Chapters, Summary
  - video_output__is_short_form       (categorical) — TRUE if Reels/Shorts eligible
  - video_output__language_name       (categorical)
  - video_output__language_code       (categorical) — en, hi, mix, es, ar, mr
  - video_output__platform_name       (categorical) — YouTube, Reels, Shorts, Instagram, etc.
  - video_output__platform_type       (categorical)
  - video_output__published_flag      (categorical)
  - video_output__client_id           (categorical) — use this in where filters

=== ROUTING RULES ===

Choose path = "metricflow" when:
- The question involves any defined metric: {metric_names}
- The question asks for trends, aggregations, KPIs, publish rates, counts, durations
- The question compares channels, users, teams, languages, input/output types by a metric
- The question asks for monthly/quarterly/yearly breakdowns

Choose path = "sql" when:
- The question asks for specific records or lists ("show me all...", "find...", "list...")
- The question involves text/keyword search on headline or source_url
- The question requires window functions, rankings across time, complex subqueries
- The question involves things NOT covered by the defined metrics above

=== OUTPUT FORMAT — respond with ONLY valid JSON, no markdown ===

If path = "metricflow":
{{
  "path": "metricflow",
  "metrics": ["<metric_name>"],
  "group_by": ["<video_output__dimension_name>"],
  "where": ["{{{{ Dimension('video_output__client_id') }}}} = '{client_id}'"],
  "order_by": ["-<metric_name>"],
  "limit": 20,
  "start_time": "<ISO date YYYY-MM-DD or null>",
  "end_time": "<ISO date YYYY-MM-DD or null>",
  "chart_type": "bar | line | pie | table | stacked_bar",
  "title": "<concise chart title>",
  "x": "<dimension name to use as x-axis>",
  "y": "<metric name to use as y-axis>",
  "description": "<one sentence describing what the chart shows>"
}}

If path = "sql":
{{
  "path": "sql",
  "sql": "<valid PostgreSQL SELECT statement>",
  "chart_type": "bar | line | pie | table | stacked_bar",
  "title": "<concise chart title>",
  "x": "<column alias for x-axis>",
  "y": "<column alias for y-axis>",
  "description": "<one sentence describing what the chart shows>"
}}

=== METRICFLOW PATH RULES ===
1. ALWAYS include where: ["{{{{ Dimension('video_output__client_id') }}}} = '{client_id}'"]
2. For time trends, include "metric_time" in group_by — MetricFlow handles granularity automatically
3. Use ONLY the exact metric and dimension names from the lists above — including the video_output__ prefix
4. Prefix "-" on order_by values means descending (e.g. "-publish_rate")
5. For multi-metric charts use stacked_bar; for time series use line
6. For time filtering use start_time / end_time (ISO dates: YYYY-MM-DD), NOT a where clause on metric_time
   - "last month"    → start_time = first day of last month, end_time = last day of last month
   - "last 30 days"  → start_time = today minus 30 days, end_time = today
   - "last quarter"  → start_time = first day of last quarter, end_time = last day of last quarter
   - "this year"     → start_time = Jan 1 of current year, end_time = today
   - Today's date is available — compute exact ISO dates, never put time ranges in the where clause

=== SQL PATH RULES ===
1. ONLY write SELECT statements — never INSERT, UPDATE, DELETE, DROP
2. ALWAYS filter by client_id = {client_id}
3. Prefer materialized views (mv_monthly_kpis, mv_channel_health, mv_user_performance) for aggregates
4. Add LIMIT 500 unless the result will have fewer rows
5. Format month as TO_CHAR(month, 'Mon YYYY') for readable x-axis labels

=== CHART TYPE GUIDELINES ===
- "line"        → time series / trends over months
- "bar"         → comparisons across categories (channels, users, types)
- "pie"         → distributions / proportions (use only when ≤ 10 categories)
- "stacked_bar" → multi-metric category comparisons
- "table"       → detailed row-level data or many columns
"""
