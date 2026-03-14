# NLQ Analytics Backend

Production-ready Natural Language Query engine built with FastAPI, Vanna.AI, PostgreSQL, and LIDA.

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI + Uvicorn |
| Text-to-SQL | Vanna.AI (RAG + ChromaDB) |
| Database | PostgreSQL + psycopg2 |
| LLM | OpenAI GPT-4o **or** Google Gemini (switchable) |
| Insight engine | LIDA (optional) |
| Data processing | Pandas |
| Config | Pydantic-Settings |

---

## Setup

### 1. Clone and enter the backend directory

```bash
cd backend
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Edit .env with your DB credentials and API keys
```

### 5. Start the server

```bash
# From the backend/ directory
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive docs available at `http://localhost:8000/docs`.

---

## API Reference

### `POST /query`

Convert a plain-English question into SQL, execute it, and return a structured response.

**Request**

```json
{
  "question": "Show monthly output per channel",
  "session_id": "abc123",
  "explore": false
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | string | ✓ | Natural language analytics question |
| `session_id` | string | | Session ID for conversational context (default: `"default"`) |
| `explore` | boolean | | Set `true` to trigger LIDA insight generation (default: `false`) |

**Response**

```json
{
  "sql": "SELECT ...",
  "answer": "In January, Sports channel had the highest output with 120 items...",
  "chart_type": "bar",
  "x": "channel",
  "y": "output_count",
  "title": "Monthly Output per Channel",
  "data": [
    {"month": "Jan", "channel": "Sports", "output_count": 120},
    {"month": "Jan", "channel": "News",   "output_count": 95}
  ],
  "insights": []
}
```

| Field | Description |
|---|---|
| `sql` | Final SQL executed (may differ from generated if self-healed) |
| `answer` | LLM-generated plain-English summary |
| `chart_type` | `line` / `bar` / `pie` / `scatter` / `table` |
| `x` / `y` | Suggested axis column names |
| `title` | Suggested chart title |
| `data` | Raw query result rows |
| `insights` | LIDA-generated chart specs (only when `explore=true`) |

### `GET /health`

Liveness probe — returns `{"status": "ok"}`.

---

## Pipeline Architecture

```
User Question
  │
  ▼
[1] Session Service       — load previous SQL for follow-up queries
  │
  ▼
[2] Vanna RAG Engine      — Text → SQL + chart spec (ChromaDB retrieval)
  │
  ▼
[3] Self-Healing Executor — run SQL; on error → LLM fix → retry (max 2×)
  │
  ▼
[4] PostgreSQL            — execute final SQL, return rows + DataFrame
  │
  ▼
[5] LIDA (optional)       — generate additional visualisation goals
  │
  ▼
[6] LLM Answer Generator  — produce plain-English summary
  │
  ▼
[7] Vanna KB Update       — store verified Q→SQL pair for future retrieval
  │
  ▼
[8] Session Update        — save question + SQL for next turn
```

---

## Switching LLM Providers

Set `LLM_PROVIDER` in `.env`:

```
LLM_PROVIDER=openai    # uses OPENAI_API_KEY + OPENAI_MODEL
LLM_PROVIDER=gemini    # uses GEMINI_API_KEY + GEMINI_MODEL
```

No code changes required.

---

## Conversational Queries

The session service remembers the last SQL per `session_id`. Example flow:

```
Turn 1: "Show monthly output per channel"
         → generates fresh SQL

Turn 2: "Now filter by Hindi only"
         → previous SQL injected into prompt → Vanna modifies it
```

---

## Project Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app + lifespan startup
│   ├── config/
│   │   └── settings.py          # Pydantic-Settings (all env vars)
│   ├── api/
│   │   └── routes.py            # POST /query + GET /health
│   ├── services/
│   │   ├── vanna_service.py     # Vanna RAG Text-to-SQL
│   │   ├── sql_executor.py      # Execution entry point
│   │   ├── self_healing.py      # LLM-assisted SQL retry loop
│   │   ├── lida_service.py      # LIDA insight engine
│   │   ├── llm_service.py       # OpenAI / Gemini abstraction
│   │   └── session_service.py   # In-memory session context
│   ├── db/
│   │   ├── postgres.py          # Connection pool + execute_query
│   │   └── schema_loader.py     # Schema introspection → DDL string
│   ├── models/
│   │   ├── request_models.py    # QueryRequest
│   │   └── response_models.py   # QueryResponse + LidaInsight
│   └── utils/
│       └── logger.py            # Shared logging config
├── requirements.txt
├── .env.example
└── nlq_README.md
```
