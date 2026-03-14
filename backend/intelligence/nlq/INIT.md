# NLQ Hybrid MetricFlow Implementation — Init Plan

## Status: in progress

## Problem with current implementation
- Schema context is a hardcoded string in `context.py` — no semantic meaning
- LLM writes raw SQL for every query, including for well-defined metrics like `publish_rate`
- One wrong join or column alias = silent wrong answer
- Adding a new metric means editing prompt strings, not a source-of-truth definition

## Solution: Hybrid SQL RAG + MetricFlow Semantic Layer

Two execution paths, one entry point (`run_nlq_query`):

```
User question
      │
      ▼
 Intent classifier (LLM step 1)
      │
      ├─── "metric"  ──► MetricFlow path
      │                   LLM picks: metrics[], group_by[], where[], limit
      │                   → mf query --explain → compiled SQL
      │                   → execute → results
      │
      └─── "exploratory" ─► SQL path (current, enhanced)
                            LLM writes raw SQL
                            prompt now includes YAML-loaded semantic context
                            → validate → execute → results
      │
      ▼
  generate_answer() (unchanged)
  return unified response shape (unchanged)
```

---

## New LLM Output Schemas

### MetricFlow path output
```json
{
  "path": "metricflow",
  "metrics": ["publish_rate"],
  "group_by": ["channel__channel_name", "metric_time__month"],
  "where": ["{{ Dimension('channel__client_id') }} = '1'"],
  "order_by": ["-publish_rate"],
  "limit": 20,
  "chart_type": "line",
  "title": "Publish Rate by Channel — Monthly Trend",
  "x": "metric_time__month",
  "y": "publish_rate",
  "description": "Monthly publish rate per channel for the selected client"
}
```

### SQL path output
```json
{
  "path": "sql",
  "sql": "SELECT ...",
  "chart_type": "table",
  "title": "Videos matching 'cricket' in headline",
  "x": "channel_name",
  "y": "created_count",
  "description": "Row-level results for keyword search"
}
```

---

## Files to Create / Modify

### NEW: `backend/semantic/` (dbt project)
- `dbt_project.yml` — project config
- `profiles.yml` — reads DATABASE_URL from env
- `models/staging/stg_fact_created_videos.sql` — thin view
- `models/semantic/_semantic__created_videos.yml` — semantic model
- `models/semantic/_metrics.yml` — all metric definitions

### NEW: `backend/intelligence/nlq/metricflow_client.py`
- `get_available_metrics() -> list[dict]` — parses _metrics.yml, returns names + descriptions
- `get_available_dimensions() -> list[dict]` — parses semantic model YAML
- `run_metricflow_query(metrics, group_by, where, order_by, limit) -> str` — calls `mf query --explain`, returns compiled SQL

### MODIFIED: `backend/intelligence/nlq/context.py`
- Remove hardcoded `SCHEMA_CONTEXT` string
- Add `load_semantic_context()` — reads both YAML files, builds structured context string
- Context now includes: metric names + formulas + descriptions, dimension names + types, entity join paths
- `build_system_prompt(client_id)` uses this loaded context

### MODIFIED: `backend/intelligence/nlq/llm.py`
- New system prompt teaches LLM about both paths and when to use each
- LLM output schema updated to include `"path": "metricflow" | "sql"`
- `call_llm()` returns dict with `path` key — router in `sql_rag.py` dispatches accordingly
- `generate_answer()` unchanged

### MODIFIED: `backend/intelligence/nlq/sql_rag.py`
- `run_nlq_query()` reads `path` from LLM response
- If `"metricflow"`: call `metricflow_client.run_metricflow_query()` → get SQL → execute
- If `"sql"`: existing validate → execute flow
- Both paths converge at `generate_answer()` and return same response shape

---

## Metrics to Define in YAML

| Metric name | Type | Formula |
|---|---|---|
| `created_count` | simple | COUNT(*) on fact_created_videos |
| `published_count` | simple | SUM(CASE WHEN published_flag THEN 1 ELSE 0 END) |
| `upload_count` | simple | COUNT(DISTINCT video_id) |
| `publish_rate` | ratio | published_count / created_count * 100 |
| `output_multiplier` | ratio | created_count / upload_count |
| `total_uploaded_duration_secs` | simple | SUM(uploaded_duration_secs) |
| `total_created_duration_secs` | simple | SUM(created_duration_secs) |

## Dimensions to Define

| Dimension | Type | Entity scope |
|---|---|---|
| `metric_time` | time | created_videos (uploaded_at) |
| `channel__channel_name` | categorical | channel |
| `channel__channel_code` | categorical | channel |
| `user__user_name` | categorical | user |
| `user__role` | categorical | user |
| `team__team_name` | categorical | team |
| `input_type__type_name` | categorical | input_type |
| `output_type__type_name` | categorical | output_type |
| `language__language_name` | categorical | language |
| `platform__platform_name` | categorical | platform |
| `published_flag` | categorical | created_videos |

---

## Dependencies to Add (requirements.txt)
```
dbt-core>=1.8
dbt-postgres>=1.8
dbt-metricflow>=1.8
pyyaml
```

---

## Query routing heuristics (for system prompt)

Use **MetricFlow path** when:
- Question involves named metrics: publish rate, output multiplier, created count, published count, durations
- Question asks for trends over time (monthly, quarterly, yearly)
- Question compares channels, users, teams, input types, output types by a metric
- Question asks for aggregated KPIs

Use **SQL path** when:
- Question asks for specific rows, records, or lists
- Question involves text/keyword search (headline, source_url)
- Question asks for things not covered by defined metrics
- Question involves window functions, rankings, or complex subqueries
- Question is exploratory ("show me all...", "find videos where...")
