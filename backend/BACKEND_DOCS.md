# Frammer AI Analytics — Backend Documentation

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | FastAPI 0.115.6 |
| Server | Uvicorn |
| Database | PostgreSQL (Supabase) |
| DB Driver | psycopg2 (connection pool) |
| LLM | Google Gemini (default) or OpenAI |

---

## Project Structure

```
ekta/backend/
├── api/
│   ├── main.py              # FastAPI app entry point
│   ├── deps.py              # DB connection pool
│   └── routes/
│       ├── dashboard.py     # Dashboard routes
│       ├── intelligence.py  # Insights, forecasts, KPI registry
│       ├── ingest.py        # Ingest placeholder (501)
│       └── nlq.py           # Natural language query
├── intelligence/
│   ├── nlq/                 # LLM → SQL pipeline (active)
│   │   ├── sql_rag.py       # Core NLQ orchestration logic
│   │   ├── llm.py           # Gemini / OpenAI abstraction
│   │   └── context.py       # Schema context + system prompt
│   ├── kpi_agent/           # Planned
│   ├── insight_narrator/    # Planned
│   ├── forecasting/         # Planned
│   └── recommendation/      # Planned
├── config.py                # Env var loading
├── schema.sql               # Full PostgreSQL schema
├── run_schema.py            # Executes schema.sql against DB
├── populate_dimensions.py   # Seeds dimension/lookup tables
├── ingest_data.py           # Bulk data ingestion
├── test_connection.py       # DB connectivity check
├── .env                     # Local env vars (never commit)
└── requirements.txt         # Python dependencies
```

---

## Environment Setup

Create a `.env` file in `ekta/backend/`:

```env
# Required
DATABASE_URL=postgresql://user:password@host:5432/dbname

# LLM provider — defaults to Gemini
LLM_PROVIDER=gemini          # "gemini" | "openai"
LLM_MODEL=gemini-2.0-flash   # or gpt-4o, gemini-1.5-pro, etc.

# API keys (only the one you use is required)
GOOGLE_API_KEY=your_google_api_key
OPENAI_API_KEY=your_openai_api_key
```

> The project currently uses **Supabase** as the PostgreSQL host.

---

## Initial Setup (First Time)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create .env with DATABASE_URL and API keys

# 3. Verify DB connection
python test_connection.py

# 4. Create all tables, views, and indexes
python run_schema.py

# 5. Seed dimension/lookup tables
python populate_dimensions.py

# 6. Ingest data
python ingest_data.py
```

---

## Starting the Server

Run from `ekta/backend/`:

```bash
# Development (auto-reload on file changes)
uvicorn api.main:app --reload

# Custom host and port
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Once running:
- **Swagger UI (interactive docs):** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## API Routes

### Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness check — returns `{"status": "ok"}` |

---

### Dashboard

#### `GET /filters/options`
Returns dropdown options for the dashboard UI.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `client_id` | int | `1` | Client to scope results |

**Response:**
```json
{
  "channels":    [{ "id": 1, "name": "Channel A", "code": "A" }],
  "input_types": [{ "id": 2, "name": "news bulletin", "category": "live" }],
  "languages":   [{ "id": 1, "code": "en", "name": "English" }],
  "date_range":  { "min": "2024-01-01T00:00:00", "max": "2025-12-31T00:00:00" }
}
```

---

#### `GET /kpis/summary`
Monthly KPI breakdown from `mv_monthly_kpis`. Supports full filtering.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `client_id` | int | `1` | Required |
| `channel_id` | int | — | Filter by channel |
| `input_type_id` | int | — | Filter by input type |
| `language_id` | int | — | Filter by language |
| `date_from` | string (ISO) | — | Start date |
| `date_to` | string (ISO) | — | End date |

**Response fields:** `month`, `channel_code`, `channel_name`, `input_type`, `output_type`, `language_code`, `created_count`, `published_count`, `total_uploaded_secs`, `total_created_secs`, `total_published_secs`, `publish_rate_pct`

---

#### `GET /kpis/totals`
Aggregate KPI totals for summary cards. Queries `fact_created_videos` directly.

**Query params:** `client_id`, `channel_id`, `date_from`, `date_to`

**Response:**
```json
{
  "total_uploads": 1200,
  "total_outputs": 3840,
  "total_published": 2100,
  "publish_rate_pct": 54.69
}
```

---

#### `GET /channels/health`
Per-channel health summary from `mv_channel_health`.

**Query params:** `client_id` (default `1`)

**Response fields:** `channel_id`, `channel_name`, `channel_code`, `primary_language`, `total_created`, `total_published`, `publish_rate_pct`, `active_users`, `last_activity`

---

#### `GET /users/performance`
Per-user performance stats from `mv_user_performance`.

**Query params:** `client_id`, `channel_id` (optional)

**Response fields:** `user_id`, `user_name`, `role`, `is_bot`, `channel_id`, `channel_name`, `channel_code`, `created_count`, `published_count`, `publish_rate_pct`, `total_uploaded_duration_secs`, `total_created_duration_secs`

---

### Intelligence

#### `GET /insights/`
AI-generated insights from `insight_log`.

**Query params:**
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `client_id` | int | `1` | |
| `insight_type` | string | — | `anomaly` \| `recommendation` \| `trend` \| `digest` |
| `is_read` | bool | — | Filter read/unread |
| `limit` | int | `50` | Max rows |

**Response fields:** `insight_id`, `insight_type`, `severity` (`info`/`warning`/`critical`), `title`, `body`, `dimensions` (JSONB), `metric_value`, `baseline_value`, `delta_pct`, `generated_at`, `is_read`

---

#### `GET /forecasts/`
Forward projections from `forecast_log`.

**Query params:** `client_id`, `channel_id` (optional), `metric_name` (optional)

**Response fields:** `forecast_id`, `channel_id`, `channel_name`, `channel_code`, `metric_name`, `forecast_month`, `predicted_value`, `lower_bound`, `upper_bound`, `model_used`, `generated_at`

---

#### `GET /kpis/registry`
All defined KPI formulas from `kpi_registry`.

**Query params:** `client_id`, `active_only` (default `true`)

**Response fields:** `kpi_id`, `client_id`, `kpi_name`, `kpi_description`, `sql_definition`, `dimensions`, `created_by`, `is_active`, `created_at`, `last_computed`

---

### NLQ — Natural Language Query

#### `POST /nlq/query`
Converts a plain-English question into SQL, executes it, and returns results with a chart specification.

**Request body:**
```json
{
  "question": "Which channel had the highest publish rate last month?",
  "client_id": 1
}
```

**Response (success):**
```json
{
  "question": "Which channel had the highest publish rate last month?",
  "sql": "SELECT dc.channel_name, ...",
  "chart_type": "bar",
  "title": "Publish Rate by Channel — Feb 2025",
  "x": "channel_name",
  "y": "publish_rate_pct",
  "description": "Bar chart showing publish rate per channel for February 2025.",
  "data": [...],
  "columns": ["channel_name", "publish_rate_pct"],
  "row_count": 3
}
```

**Response (error):**
```json
{
  "question": "...",
  "error": "reason for failure",
  "sql": null,
  "data": [],
  "row_count": 0
}
```

**Safety rules enforced by the backend:**
- Only `SELECT` statements are permitted — all others are blocked
- `LIMIT 500` is auto-injected if the LLM omits it
- Every query (success or failure) is logged to `query_log`

**NLQ Pipeline Flow:**
```
User question
  → build_system_prompt(client_id)    # full schema context injected
  → call_llm(system_prompt, question) # Gemini or OpenAI returns JSON
  → validate required JSON fields
  → block non-SELECT SQL
  → inject LIMIT 500 if missing
  → execute against PostgreSQL
  → log to query_log
  → return data + chart spec
```

**Switching LLM provider:**
```env
# Use OpenAI instead of Gemini
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o
OPENAI_API_KEY=your_key
```

---

### Ingest

#### `POST /ingest`
**Status: Not Implemented — returns HTTP 501**

Placeholder endpoint. Ingestion shape is TBD based on the upstream Frammer data source. Currently ingestion is done via the `ingest_data.py` script directly.

---

## Database Schema

### Dimension Tables

| Table | Key Columns |
|-------|------------|
| `dim_client` | `client_id`, `client_name`, `plan_type`, `industry`, `region`, `is_active` |
| `dim_channel` | `channel_id`, `client_id`, `channel_name`, `channel_code`, `primary_language`, `is_active` |
| `dim_user` | `user_id`, `client_id`, `user_name`, `role`, `is_bot`, `is_active` |
| `dim_team` | `team_id`, `client_id`, `channel_id`, `team_name` |
| `dim_input_type` | `input_type_id`, `type_name`, `category` |
| `dim_output_type` | `output_type_id`, `type_name`, `is_short_form` |
| `dim_language` | `language_id`, `language_code`, `language_name` |
| `dim_platform` | `platform_id`, `platform_name`, `platform_type` |
| `user_channel_map` | `user_id`, `channel_id` (many-to-many bridge) |

### Fact Table

**`fact_created_videos`** — one row per created video output (1 source → ~3.2 outputs avg)

| Column | Type | Notes |
|--------|------|-------|
| `id` | BIGSERIAL | Primary key |
| `video_id` | VARCHAR | Source video ID (shared across outputs) |
| `client_id` | INT | FK → dim_client |
| `channel_id` | INT | FK → dim_channel |
| `user_id` | INT | FK → dim_user |
| `team_id` | INT | FK → dim_team (nullable) |
| `input_type_id` | INT | FK → dim_input_type |
| `output_type_id` | INT | FK → dim_output_type |
| `language_id` | INT | FK → dim_language |
| `uploaded_duration_secs` | INT | Source video length |
| `created_duration_secs` | INT | Output clip length |
| `published_duration_secs` | INT | Published clip length |
| `uploaded_at` | TIMESTAMPTZ | |
| `published_flag` | BOOLEAN | Whether the output was published |
| `published_platform_id` | INT | FK → dim_platform |

### Operational Tables

| Table | Written By | Purpose |
|-------|-----------|---------|
| `kpi_registry` | KPI Agent | Stores metric SQL definitions |
| `insight_log` | Insight Narrator | AI-generated insights & anomalies |
| `forecast_log` | Forecasting Agent | Time-series predictions |
| `quality_log` | Ingest pipeline | Data quality issues |
| `query_log` | NLQ route | Logs every NLQ request |

### Materialized Views

| View | Description |
|------|-------------|
| `mv_monthly_kpis` | Monthly rollup by channel, input type, output type, language |
| `mv_channel_health` | Total created/published, publish rate, active users per channel |
| `mv_user_performance` | Created/published counts and rates per user per channel |

> These views are pre-computed. Refresh them after bulk ingestion with:
> ```sql
> REFRESH MATERIALIZED VIEW mv_monthly_kpis;
> REFRESH MATERIALIZED VIEW mv_channel_health;
> REFRESH MATERIALIZED VIEW mv_user_performance;
> ```

### Key Metric Definitions

| Metric | SQL Definition |
|--------|---------------|
| Uploads / Source videos | `COUNT(DISTINCT video_id)` |
| Created outputs | `COUNT(*)` from fact table |
| Published | `published_flag = TRUE` |
| Publish rate | `published_count / created_count * 100` |
| Output multiplier | `COUNT(*) / COUNT(DISTINCT video_id)` |

---

## Reference Data

### Input Types (`dim_input_type`)
`interview`, `news bulletin`, `speech`, `special reports`, `debate`, `press conference`, `discussion-show`, `sports show`, `podcast`, `drama`, `in-brief`

### Output Types (`dim_output_type`)
`Full package`, `Key moments`, `My Key moments`, `Chapters`, `Summary`

### Languages (`dim_language`)
`en` (English), `hi` (Hindi), `mix` (Mixed), `es` (Spanish), `ar` (Arabic), `mr` (Marathi)

### Platforms (`dim_platform`)
`YouTube`, `Reels`, `Shorts`, `Instagram`, `Facebook`, `Facebook-Reels`, `LinkedIn`, `X`, `Threads`

---

## CORS

Currently set to `allow_origins=["*"]` in development. Tighten this in production inside `api/main.py`.

---

## Dependencies (`requirements.txt`)

```
fastapi==0.115.6
uvicorn[standard]==0.32.1
psycopg2-binary==2.9.10
python-dotenv==1.0.1
google-generativeai==0.8.3
openai==1.58.1
python-multipart==0.0.20
```
