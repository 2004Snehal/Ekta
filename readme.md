# Frammer AI Analytics Platform

Real-time video processing and publishing analytics with LLM-powered insights, recommendations, and natural language querying.

## Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL database (Supabase or local)
- LLM API key (Google Gemini or OpenAI)

## Setup

### 1. Environment Variables

Create `backend/.env`:

```
DATABASE_URL=postgresql://user:pass@host:5432/dbname
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GOOGLE_API_KEY=your-key
```

Create `dashboard_frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2. Backend

```bash
cd backend
pip install -r ../requirements.txt
uvicorn api.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd dashboard_frontend
npm install
npm run dev
```

Opens on http://localhost:3000

## API Endpoints

| Group | Endpoint | Method |
|---|---|---|
| Dashboard | `/dashboard` | GET |
| Analytics | `/analytics/multi-dim` | POST |
| Analytics | `/analytics/period-compare` | GET |
| Analytics | `/analytics/funnel` | GET |
| Analytics | `/analytics/data-quality` | GET |
| Analytics | `/analytics/time-series` | GET |
| Profiles | `/profiles` | GET |
| NLQ | `/nlq/query` | POST |
| Recommendations | `/recommendations/contextual` | POST |
| Narrator | `/narrator/insights` | GET |
| Narrator | `/narrator/run` | POST |
| Health | `/health` | GET |

## Project Structure

```
backend/
  api/
    main.py              # FastAPI app + scheduler
    deps.py              # DB connection pool
    routes/              # All API endpoints
  intelligence/
    recommendation/      # LLM-powered contextual recommendations
    nlq/                 # Natural language to SQL
    insight_narrator/    # Anomaly detection + LLM narration
    kpi_agent/           # Auto-KPI discovery engine

dashboard_frontend/
  app/
    dashboard/           # Executive Summary
    dashboard/usage/     # Usage & Trends
    dashboard/analysis/  # Drill-Down Analysis
    dashboard/funnel/    # Funnel & Type Mix
    dashboard/explorer/  # Video Explorer
    query/               # NLQ Chat
    narrator/            # Insight Narrator
  components/            # Shared UI components
  lib/                   # Profiles context, utilities
  types/                 # TypeScript type definitions
```
