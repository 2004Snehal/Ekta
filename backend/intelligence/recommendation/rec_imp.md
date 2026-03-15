# Recommendation Agent — Implementation Summary

## What was built

A context-aware recommendation agent that fires on user navigation, not on a schedule.
The frontend sends a small payload describing what the user is looking at; the backend
expands that context with targeted SQL, passes it to an LLM, and returns 3–5
cross-dimensional recommendations.

---

## Files

| File | Purpose |
|---|---|
| `models.py` | Pydantic schemas: `DashboardContext` (input), `ExpandedContext` (internal), `Recommendation`, `RecommendationResponse` (output) |
| `cache.py` | In-memory TTL cache (5 min). Key = `client_id:entity_type:entity_id:metric:time_range:view`. No Redis needed. |
| `context_expander.py` | Dispatches to a view-specific handler, each running 4 SQL queries against materialized views |
| `prompts.py` | Role-aware system prompt builder (ops_lead / editor / exec). Includes the "2+ sections" constraint. |
| `engine.py` | Orchestrator: cache check → expand → format → LLM → parse → cache → return |
| `api/routes/recommendations.py` | `POST /recommendations/contextual` route |

---

## API

### `POST /recommendations/contextual`

**Request**
```json
{
  "client_id":      1,
  "view":           "channel_detail",
  "entity_type":    "channel",
  "entity_id":      2,
  "entity_name":    "CNN Hindi",
  "metric_in_focus": "publish_rate_pct",
  "current_value":  21.9,
  "time_range":     null,
  "user_role":      "ops_lead"
}
```

`view` options: `channel_detail` | `user_detail` | `content_mix` | `executive_summary` | `trend_view`
`user_role` options: `ops_lead` | `editor` | `exec`

**Response**
```json
{
  "recommendations": [
    {
      "title":    "Publish rate 40pp below peer average",
      "action":   "Review QC handoff stage for CNN Hindi — 3 assigned users have 0 published outputs this month.",
      "rationale": "CNN Hindi's publish rate is 21.9% vs peer avg 61.0%. Of 4 users assigned, 3 published 0 outputs despite creating 80+. IBN7 runs same volume at 78% with 2 fewer users.",
      "priority": "high",
      "scope":    "channel",
      "supporting_metrics": {
        "cnn_hindi_publish_rate": 21.9,
        "peer_avg_publish_rate":  61.0,
        "users_with_zero_published": 3
      }
    }
  ],
  "context_view":  "channel_detail",
  "entity_name":   "CNN Hindi",
  "generated_at":  "2024-12-01T10:00:00Z",
  "cached":        false
}
```

---

## Context Expander — view types and their 4 queries

Each view type runs 4 queries, all against materialized views (no fact table scans).

### `channel_detail`
| Section | Source | What it fetches |
|---|---|---|
| entity_profile | `mv_channel_health` + `mv_monthly_kpis` | Channel totals + last 6 months trend |
| peer_comparison | `mv_channel_health` | Other channels ranked by publish_rate_pct |
| related_actors | `mv_user_performance` + `dim_user` | Users on this channel |
| benchmark | `mv_monthly_kpis` + `dim_input_type` | Input type mix: this channel vs network |

### `user_detail`
| Section | Source | What it fetches |
|---|---|---|
| entity_profile | `mv_user_performance` + `dim_channel` | This user's metrics per channel |
| peer_comparison | `mv_user_performance` + `dim_user` | Peers on same channel, ranked |
| related_actors | `user_channel_map` + `dim_channel` | Channels this user works on |
| benchmark | `mv_user_performance` | Top 3 users in same channel |

### `content_mix`
| Section | Source | What it fetches |
|---|---|---|
| entity_profile | `mv_monthly_kpis` filtered by input_type_id | This content type's monthly trend |
| peer_comparison | `mv_monthly_kpis` all input types | All input types ranked by metric |
| related_actors | `mv_monthly_kpis` grouped by channel | Which channels use this type most/least |
| benchmark | `mv_monthly_kpis` + `dim_channel` | Best channel for this content type |

### `executive_summary`
| Section | Source | What it fetches |
|---|---|---|
| entity_profile | `mv_channel_health` | All channels ranked by publish rate |
| peer_comparison | `mv_monthly_kpis` | Current vs previous month MoM deltas |
| related_actors | `mv_user_performance` | Bottom 5 users by publish rate |
| benchmark | `mv_monthly_kpis` + `dim_input_type` | Best and worst content types |

### `trend_view`
| Section | Source | What it fetches |
|---|---|---|
| entity_profile | `mv_monthly_kpis` | Full monthly series for this channel |
| peer_comparison | `mv_monthly_kpis` | Same metric trend for peer channels |
| related_actors | `mv_monthly_kpis` + window fn | Top 3 anomalous MoM delta months |
| benchmark | `mv_channel_health` | Current network leader |

---

## Prompt architecture

Three-section system prompt:

1. **Role identity** — different persona per `user_role`:
   - `ops_lead`: operations consultant, focused on workflows and team assignments
   - `editor`: production advisor, focused on content types and individual output
   - `exec`: strategic advisor, focused on cross-channel patterns and resource allocation

2. **Context framing** — injects `view`, `entity_name`, `metric_in_focus`, `current_value`

3. **Output rules** — the key constraint:
   > Each recommendation MUST reference at least 2 data points from DIFFERENT sections.
   > Single-metric observations are not recommendations.

---

## Why this is better than a batch agent

| Batch agent | Context-aware agent |
|---|---|
| Runs on schedule | Fires on user navigation |
| Sees current state only | Sees what the user is focused on |
| Generic "channel X has low rate" | "CNN Hindi hasn't produced interviews — interviews are the best input type network-wide" |
| Can't cross-reference | Fetches peers, users, and benchmarks in parallel |
| Same recs for everyone | Role-aware: exec vs ops lead get different framing |

---

## Caching

Cache key: `{client_id}:{entity_type}:{entity_id}:{metric_in_focus}:{time_range}:{view}`
TTL: 5 minutes. Two users clicking the same chart within 5 min share one LLM call.
Response includes `"cached": true` when served from cache.
