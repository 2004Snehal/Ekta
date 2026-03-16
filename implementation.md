# Frammer AI Analytics Platform — Implementation Summary

## Architecture

```
Frontend (Next.js)          Backend (FastAPI)            Database (PostgreSQL)
─────────────────          ────────────────            ──────────────────────
TopNav + ProfileProvider    /profiles                   data.fact_created_videos
  5 Dashboard Sections      /analytics/*                data.dim_channel
  NLQ Chat                  /recommendations/*          data.dim_user
  Insight Narrator          /nlq/*                      data.dim_input_type
                            /narrator/*                 data.mv_channel_health
                            /dashboard                  data.mv_monthly_kpis
```

---

## Five User Profiles

Every intelligence feature adapts to the selected profile.

| Profile | Who It's For | Default View | Focus |
|---|---|---|---|
| **Founders / Leadership** | Executives, founders | Executive Summary | Strategic growth, revenue impact, portfolio-level patterns |
| **Client Success** | Account managers | Drill-Down Analysis | Client health signals, adoption, retention, churn risk |
| **Operations** | Ops leads, team managers | Usage & Trends | Throughput, bottlenecks, team efficiency, workloads |
| **Editorial / Production** | Editors, producers | Funnel & Type Mix | Content types, format trends, editorial pipeline |
| **Tech / Product** | Engineers, PMs | Video Explorer | Data quality, platform coverage, system metrics |

Profile selection persists in localStorage and affects:
- Which KPIs appear first on the dashboard
- Recommendation tone and focus
- NLQ query interpretation defaults
- Insight narrator framing

---

## Pages & Routes

### `/dashboard` — Executive Summary

The main landing page. Shows a high-level overview of the entire operation.

- **KPI strip** with sparklines and period-over-period deltas (uploaded, processed, published, publish rate, avg duration)
- **Trend charts** — video count over time, distribution breakdowns
- **Insight banner** — top 2-3 alerts pulled from the Narrator pipeline
- **Recommendations panel** — 3-5 cross-dimensional, profile-aware recommendations from the LLM
- **Filters** — date range (7D/30D/90D/ALL), client, channel, user, language, type, platform

### `/dashboard/usage` — Usage & Trends

Time-series analytics for understanding volume and growth patterns.

- **Granularity selector** — Day / Week / Month toggles
- **Video count line chart** — primary metric over time
- **Period comparison table** — current vs previous period with delta percentages
- **Cumulative duration chart** — total hours processed over time
- Fetches from `/analytics/time-series` and `/analytics/period-compare`

### `/dashboard/analysis` — Drill-Down Analysis

Multi-dimension cross-tabulation for deep exploration.

- **Dimension picker** — select any two dimensions (Channel, User, Language, Input Type, Output Type, Platform) and a metric
- **Cross-tab chart** — stacked bar or horizontal bar visualization of the intersection
- **Breakdown table** — sortable detail rows with all metrics
- **Grand total bar** — aggregate counts, duration, published, publish rate
- Fetches from `POST /analytics/multi-dim`

### `/dashboard/funnel` — Funnel & Type Mix

Publishing pipeline analysis and content type distribution.

- **Publishing funnel** — horizontal bars showing Uploaded -> Processed -> Published with conversion rates at each step
- **Group-by selector** — slice the funnel by Channel, User, Input Type, or Language
- **Input type pie chart** — content type distribution
- **Publish rate bar chart** — conversion rate ranked by group
- Fetches from `/analytics/funnel` and `POST /analytics/multi-dim`

### `/dashboard/explorer` — Video Explorer

Record-level data table for detailed inspection.

- **Data quality bar** — total records, unique videos, duplicate warnings, missing publish URLs, per-field null percentages
- **Searchable table** — filter across all columns with free text
- **Sortable columns** — click any header to sort ascending/descending
- **CSV export** — download filtered data as CSV
- **Pagination** — 50 rows per page with prev/next navigation
- Fetches from `/dashboard` (records) and `/analytics/data-quality`

### `/query` — Natural Language Query

Ask questions in plain English, get SQL + charts.

- **Chat interface** with session history sidebar
- **Profile-aware** — NLQ prompt preamble adapts to selected profile
- **SQL preview** panel shows generated query
- **Auto-visualization** — results rendered as charts based on LLM chart type selection
- **Session persistence** — conversations saved and restorable via URL
- Posts to `/nlq/query` with `{question, client_id, profile}`

### `/narrator` — Insight Narrator

Automatically surfaced anomalies and trends.

- **Digest summary** — LLM-generated paragraph summarizing the period
- **Insight cards** — individual anomalies with severity (high/medium/low), category, and root cause hints
- **Severity summary** — count of high/medium/low insights
- **Manual trigger** — "Run Now" button to force pipeline execution
- **Profile context** — displayed in header for awareness
- Fetches from `/narrator/insights`

---

## Backend API Endpoints

### Profiles
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/profiles` | Returns all 5 profile definitions |
| `GET` | `/profiles/{key}` | Returns a single profile |

### Analytics
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/analytics/multi-dim` | Cross-tabulate any two dimensions with metric selection |
| `GET` | `/analytics/period-compare` | Compare current vs previous week/month/quarter |
| `GET` | `/analytics/funnel` | Publishing funnel (uploaded -> processed -> published) by any dimension |
| `GET` | `/analytics/data-quality` | Null audit, duplicate detection, field completeness |
| `GET` | `/analytics/time-series` | Flexible time-series with day/week/month granularity and optional grouping |

### Intelligence
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/recommendations/contextual` | Profile-aware, context-aware recommendations from LLM |
| `POST` | `/nlq/query` | Natural language to SQL with profile preamble |
| `GET` | `/narrator/insights` | Cached insight cards from anomaly detection pipeline |
| `POST` | `/narrator/run` | Trigger narrator pipeline manually |

### Dashboard
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/dashboard` | Full record set for a date range |
| `GET/POST` | `/dashboard/state` | Persist and restore dashboard filter state |

---

## Shared Frontend Components

| Component | Used On | Purpose |
|---|---|---|
| `TopNav` | All pages | Profile selector + 5 section tabs + NLQ/Insights links + LIVE indicator |
| `SparkKPI` | Executive Summary | KPI card with inline sparkline and delta % |
| `GlobalFilters` | Dashboard sections | Shared filter bar with optional granularity control |
| `DimensionPicker` | Analysis | Dim1 x Dim2 x Metric selector |
| `PeriodComparison` | Usage & Trends | Current vs previous period table with deltas |
| `FunnelChart` | Funnel | Horizontal funnel bars with conversion rates |
| `CrossTabChart` | Analysis | Stacked/grouped bar chart for multi-dim data |
| `DataTable` | Explorer, Analysis | Sortable, searchable, paginated table with CSV export |
| `InsightBanner` | Executive Summary | Inline severity-colored alert strips |
| `RecommendationsPanel` | All dashboard sections | Collapsible LLM recommendations, context-aware by page |
| `ChartRenderer` | All pages | Universal chart renderer (line, bar, pie, scatter, stacked, table) |

---

## How Intelligence Adapts to Profiles

**Recommendations** — The LLM system prompt changes identity per profile. An operations user gets bottleneck-focused advice; a founder gets strategic portfolio recommendations. The view context also changes based on which dashboard section the user is on.

**NLQ** — The system prompt includes a profile preamble that biases the LLM toward relevant query patterns. An editorial user asking "show me trends" gets content type breakdowns by default; an operations user gets throughput metrics.

**Narrator** — Insight cards are framed for the audience. The same anomaly might be described as "revenue risk" for founders or "QC bottleneck" for operations.

---

## Data Flow

```
User selects profile -> stored in localStorage -> ProfileProvider context
    |
    v
User navigates to /dashboard/analysis
    |
    v
DimensionPicker: user picks Channel x Language, metric=count
    |
    v
POST /analytics/multi-dim { client_id:1, dim1:"channel", dim2:"language", metric:"count" }
    |
    v
Backend: SQL against fact_created_videos + dim joins -> aggregated rows
    |
    v
Frontend: CrossTabChart renders stacked bar + DataTable shows breakdown
    |
    v
RecommendationsPanel detects pathname="/dashboard/analysis" -> sets view="channel_detail"
    |
    v
POST /recommendations/contextual { view:"channel_detail", user_role:"operations", ... }
    |
    v
Backend: 4 SQL context queries -> LLM generates 3-5 recommendations
    |
    v
Frontend: renders priority-colored recommendation cards in right panel
```
