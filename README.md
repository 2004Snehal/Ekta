# Frammer — AI-Powered Video Analytics Platform

Frammer gives media operations teams a unified analytics workspace for video publishing data. It combines an executive KPI dashboard, drill-down analytics, funnel analysis, and a natural language query interface so anyone on the team can explore data without writing SQL. An LLM-powered Insight Narrator runs nightly anomaly detection and surfaces plain-English summaries, while a KPI Lab auto-discovers relevant metrics using a LangGraph agent.

**Stack:** FastAPI · PostgreSQL (Supabase) · Next.js 15 · Vanna RAG + ChromaDB · OpenRouter LLMs

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.10+ |
| Node.js | 18+ |
| PostgreSQL | Any (Supabase recommended) |
| OpenRouter API key | [openrouter.ai/keys](https://openrouter.ai/keys) |

---

## Environment Setup

### Backend — `backend/.env`

Copy the example and fill in the two required values:

```bash
cp backend/.env.example backend/.env
```

```env
# REQUIRED — PostgreSQL connection string
DATABASE_URL=postgresql://user:password@host:5432/dbname

# Optional — needed if DATABASE_URL points to a Supabase pooler
# (poolers cannot run DDL; use the direct connection URL here)
# DIRECT_DATABASE_URL=postgresql://user:password@db-host:5432/dbname

# REQUIRED — OpenRouter API key (https://openrouter.ai/keys)
LLM_API_KEY=sk-or-v1-your-key-here
```

### Frontend — `dashboard_frontend/.env`

```bash
cp dashboard_frontend/.env.example dashboard_frontend/.env
```

```env
# URL of the running backend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

For production, set this to your deployed backend URL before building.

---

## Running in Production

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

gunicorn -w 4 -k uvicorn.workers.UvicornWorker api.main:app --bind 0.0.0.0:8000
```

API is available at `http://localhost:8000`. Health check: `GET /health`.

> **Note:** On first start, the backend initialises the ChromaDB RAG knowledge base (`./chroma_db/`). This takes ~30 seconds. Subsequent starts are instant.

### Frontend

```bash
cd dashboard_frontend
npm install
npm run build
npm start                          # Serves on http://localhost:3000
```

---

## Key Pages

| Route | Description |
|---|---|
| `/dashboard` | Executive KPI summary |
| `/dashboard/usage` | Usage & trends over time |
| `/dashboard/analysis` | Drill-down multi-dimensional analysis |
| `/dashboard/funnel` | Funnel & content type mix |
| `/dashboard/explorer` | Browse & filter individual videos |
| `/query` | Natural language query chat (NLQ) |
| `/narrator` | LLM-generated insight narratives |
| `/kpi-lab` | Auto-discover KPIs with an AI agent |
| `/recommendations` | Role-aware contextual recommendations |
| `/admin` | Admin console |

---

## Default Credentials

Register a new account at `/signup`, or use the admin console to create users. Role options: `user` · `admin`. Profile types: `analyst`, `editor`, `manager`, `founder`, `team_member`.
