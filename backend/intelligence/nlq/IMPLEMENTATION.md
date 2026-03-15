# NLQ — Hybrid MetricFlow + SQL RAG Implementation

## Overview

The NLQ module converts plain-English questions into data results using two execution paths routed by an LLM. Metric/aggregation questions go through MetricFlow's semantic layer (no raw SQL hallucination). Exploratory/row-level questions fall back to direct LLM-generated SQL with enriched schema context.

---

## 1. High-Level Architecture

```mermaid
graph TD
    User["👤 User\n(frontend /query page)"]
    API["POST /nlq/query\n(FastAPI route)"]
    LLM1["LLM — Router\nGemini / OpenAI\n(system prompt with schema + semantic context)"]
    MFPath["MetricFlow Path"]
    SQLPath["SQL Path"]
    MFClient["metricflow_client.py\nmf query --explain"]
    MFYAML["Semantic Layer\n(dbt project + YAML)"]
    DB[("PostgreSQL\nfact_created_videos\n+ dim tables\n+ mat. views")]
    LLM2["LLM — Answer Narrator\n(plain-English answer from rows)"]
    Response["JSON Response\n{answer, sql, chart_type, data, path, query_time_ms}"]
    Frontend["ChartRenderer\n+ AssistantBubble\n(frontend)"]

    User -->|"natural language question"| API
    API --> LLM1
    LLM1 -->|"path=metricflow\n{metrics, group_by, where,\nstart_time, end_time}"| MFPath
    LLM1 -->|"path=sql\n{sql, chart_type}"| SQLPath
    MFPath --> MFClient
    MFClient <-->|"mf query --explain\nsubprocess"| MFYAML
    MFClient -->|"compiled SQL"| DB
    SQLPath -->|"validate SELECT\ninject LIMIT"| DB
    DB -->|"rows"| LLM2
    LLM2 -->|"1–3 sentence answer"| Response
    Response --> Frontend
```

---

## 2. Request Lifecycle (Sequence Diagram)

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as FastAPI /nlq/query
    participant SR as sql_rag.py
    participant CTX as context.py
    participant LLM as LLM (Gemini/OpenAI)
    participant MFC as metricflow_client.py
    participant MF as mf CLI subprocess
    participant DB as PostgreSQL

    FE->>API: POST {question, client_id}
    API->>SR: run_nlq_query(question, client_id, conn)

    SR->>CTX: build_system_prompt(client_id)
    CTX-->>SR: prompt (schema + YAML-loaded metrics/dims + routing rules)

    SR->>LLM: call_llm(system_prompt, question)
    Note over LLM: Decides path=metricflow or path=sql<br/>Generates query params or raw SQL
    LLM-->>SR: {path, metrics, group_by, where, start_time, end_time, ...}

    alt path = "metricflow"
        SR->>MFC: run_metricflow_query(metrics, group_by, where, order, limit, start_time, end_time)
        MFC->>MFC: _ensure_manifest() — dbt parse if needed
        MFC->>MFC: _dbt_env() — parse DATABASE_URL → DBT_* vars
        MFC->>MF: subprocess: mf query --explain ...
        MF-->>MFC: compiled SQL (stdout)
        MFC->>MFC: _extract_sql() — strip ANSI, regex SELECT
        MFC-->>SR: compiled SQL string
    else path = "sql"
        SR->>SR: validate SELECT-only
        SR->>SR: inject LIMIT 500 if missing
    end

    SR->>DB: cursor.execute(sql)
    DB-->>SR: rows

    SR->>SR: _serialize() — dates/decimals → JSON-safe
    SR->>SR: _log_query() → query_log table

    SR->>LLM: generate_answer(question, data[:15])
    LLM-->>SR: plain-English answer string

    SR-->>API: {question, answer, path, sql, chart_type, title, x, y, data, row_count, query_time_ms}
    API-->>FE: JSON response
```

---

## 3. Routing Logic

```mermaid
flowchart LR
    Q["User Question"]
    R{"LLM Router\n(system prompt with\nrouting rules)"}
    MF["MetricFlow Path\npre-defined metrics only\nno SQL hallucination"]
    SQL["SQL Path\nfull flexibility\nraw SQL generation"]

    Q --> R

    R -->|"involves: publish_rate,\ncreated_count, published_count,\noutput_multiplier, durations\nOR: group by channel/user/language/\ntype/platform/team\nOR: trend/aggregate/KPI"| MF

    R -->|"asks for: specific rows, records,\ntext/keyword search (headline, url),\nwindow functions, rankings,\nthings NOT in defined metrics"| SQL
```

---

## 4. MetricFlow Semantic Layer Structure

```mermaid
graph TD
    subgraph "backend/semantic/ (dbt project)"
        PROJ["dbt_project.yml"]
        PROF["profiles.yml\n(reads DBT_* env vars\nparsed from DATABASE_URL)"]
        MACRO["macros/generate_schema_name.sql\n(prevents public_public double-prefix)"]

        subgraph "models/staging/"
            SRC["sources.yml\n(9 raw PostgreSQL tables)"]
            STG["stg_fact_created_videos.sql\nDENORMALIZED VIEW\nfact + all 7 dim tables joined"]
            TS["metricflow_time_spine.sql\none row per calendar day\n2020-01-01 → today + 2 years"]
        end

        subgraph "models/semantic/"
            SM["_semantic__created_videos.yml\nSEMANTIC MODEL\n5 entities · 18 dimensions · 6 measures"]
            ME["_metrics.yml\n8 METRIC DEFINITIONS\n3 simple · 2 ratio · 3 simple duration"]
        end
    end

    STG --> SM
    TS -->|"required by MetricFlow\nfor time grain support"| SM
    SM --> ME
```

---

## 5. Semantic Model Detail

```mermaid
erDiagram
    CREATED_VIDEOS_SEMANTIC_MODEL {
        entity video_output "primary — id"
        entity client "foreign — client_id"
        entity channel "foreign — channel_id"
        entity user "foreign — user_id"
        entity team "foreign — team_id"
        time created_at "uploaded_at · granularity=day"
        dim channel_name "categorical"
        dim channel_code "categorical"
        dim user_name "categorical"
        dim user_role "categorical · editor/auto"
        dim is_bot "categorical"
        dim team_name "categorical"
        dim input_type_name "categorical"
        dim input_type_category "categorical · live/recorded/scripted"
        dim output_type_name "categorical"
        dim language_name "categorical"
        dim language_code "categorical · en/hi/mix/es/ar/mr"
        dim platform_name "categorical"
        dim published_flag "categorical"
        dim client_id "categorical — use in where filters"
        measure created_count "agg=count on id"
        measure published_count "agg=sum_boolean on published_flag"
        measure upload_count "agg=count_distinct on video_id"
        measure total_uploaded_duration_secs "agg=sum"
        measure total_created_duration_secs "agg=sum"
        measure total_published_duration_secs "agg=sum"
    }
```

---

## 6. Metrics Catalogue

```mermaid
graph LR
    subgraph "Simple Metrics (direct aggregations)"
        CC["created_count\nCOUNT(id)"]
        PC["published_count\nSUM(published_flag)"]
        UC["upload_count\nCOUNT DISTINCT(video_id)"]
        TU["total_uploaded_duration_secs\nSUM(uploaded_duration_secs)"]
        TC["total_created_duration_secs\nSUM(created_duration_secs)"]
        TP["total_published_duration_secs\nSUM(published_duration_secs)"]
    end

    subgraph "Ratio Metrics (derived)"
        PR["publish_rate\npublished_count ÷ created_count"]
        OM["output_multiplier\ncreated_count ÷ upload_count"]
    end

    PC --> PR
    CC --> PR
    CC --> OM
    UC --> OM
```

---

## 7. File Map

```mermaid
graph TD
    subgraph "backend/intelligence/nlq/"
        SR["sql_rag.py\n— run_nlq_query() entry point\n— route on path key\n— _run_metricflow_path()\n— _run_sql_path()\n— _execute_and_respond()\n— per-step timing + logging"]
        CTX["context.py\n— load_semantic_context()\n  reads _metrics.yml + semantic YAML\n— build_system_prompt(client_id)\n  schema + metric/dim listings\n  routing rules + dual output format"]
        LLM["llm.py\n— call_llm() → JSON dict\n— generate_answer() → string\n— Gemini + OpenAI adapters"]
        MFC["metricflow_client.py\n— run_metricflow_query()\n— get_available_metrics()\n— get_available_dimensions()\n— _dbt_env() parse DATABASE_URL\n— _ensure_manifest() dbt parse\n— _extract_sql() strip ANSI + regex"]
        PLAN["PLAN.md\n(original)"]
        INIT["INIT.md\n(hybrid design plan)"]
        IMPL["IMPLEMENTATION.md\n← you are here"]
    end

    subgraph "backend/api/routes/"
        ROUTE["nlq.py\nPOST /nlq/query"]
    end

    subgraph "dashboard_frontend/app/query/"
        PAGE["page.tsx\n— chat UI\n— path badge (MetricFlow / SQL)\n— answer display\n— query_time_ms display\n— SQL collapsible block\n— ChartRenderer"]
    end

    ROUTE --> SR
    SR --> CTX
    SR --> LLM
    SR --> MFC
```

---

## 8. Terminal Log Format (per query)

```
HH:MM:SS  INFO  nlq  ────────────────────────────────────────────────────────
HH:MM:SS  INFO  nlq  [NLQ] ← "Which channel had the highest publish rate?"  (client=1)
HH:MM:SS  INFO  nlq  [NLQ] LLM routing      1.23s  → path=metricflow
HH:MM:SS  INFO  nlq  [NLQ] MF params        metrics=['publish_rate']  group_by=['video_output__channel_name']
HH:MM:SS  INFO  nlq.mf  [MF]  subprocess    query --explain --metrics publish_rate ...
HH:MM:SS  INFO  nlq.mf  [MF]  subprocess    done  (0.45s)
HH:MM:SS  INFO  nlq  [NLQ] MF compile       0.45s  ✓
HH:MM:SS  INFO  nlq  [NLQ] SQL execute      0.12s  → 8 rows
HH:MM:SS  INFO  nlq  [NLQ] Answer gen       0.89s
HH:MM:SS  INFO  nlq  [NLQ] Total            2.69s  → 8 rows
HH:MM:SS  INFO  nlq  ────────────────────────────────────────────────────────
```

---

## 9. Setup Checklist

```
backend/.env
  ├── DATABASE_URL=postgresql://user:pass@host:port/dbname
  ├── DBT_HOST, DBT_USER, DBT_PASSWORD, DBT_PORT, DBT_DBNAME  ← parsed from DATABASE_URL
  ├── LLM_PROVIDER=gemini  (or openai)
  ├── LLM_MODEL=gemini-2.5-flash
  └── GOOGLE_API_KEY / OPENAI_API_KEY

One-time DB setup (run from backend/semantic/):
  dbt run --profiles-dir . --select stg_fact_created_videos metricflow_time_spine

Start backend (from backend/):
  uvicorn api.main:app --reload

Start frontend (from dashboard_frontend/):
  pnpm dev
  → open http://localhost:3000/query
```

---

## 10. Extension Points

| What to add | Where |
|---|---|
| New metric (e.g. `avg_output_duration`) | `_metrics.yml` — add entry, `dbt parse` to refresh manifest |
| New dimension (e.g. `team_name` filter) | Already in semantic model — just use `video_output__team_name` in LLM output |
| New data source (e.g. `fact_published_events`) | Add `sources.yml` entry + staging SQL + new `_semantic__*.yml` |
| Conversation history / multi-turn | Add `history: []` param to `run_nlq_query`, inject prior Q&A into LLM prompt |
| Semantic caching | Hash `(question, client_id)` → cache compiled SQL + answer in Redis |
| Query feedback loop | Frontend sends `{query_id, helpful: true/false}` → updates `query_log.user_feedback` |
