# NLQ Analytics Pipeline — Engineering Documentation

> **Audience:** Backend engineers, ML engineers, and technical stakeholders onboarding to this system.
> **Scope:** End-to-end explanation of the Natural Language Query (NLQ) analytics pipeline — from a user typing a plain-English question to a structured answer with charts and insights being returned.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [End-to-End Pipeline Flow](#2-end-to-end-pipeline-flow)
3. [Vanna.AI Architecture](#3-vannaai-architecture)
4. [Self-Healing SQL Mechanism](#4-self-healing-sql-mechanism)
5. [PostgreSQL Execution Layer](#5-postgresql-execution-layer)
6. [LIDA Architecture and Role](#6-lida-architecture-and-role)
7. [LLM Answer Generation](#7-llm-answer-generation)
8. [Knowledge Base Update](#8-knowledge-base-update)
9. [Session Memory and Multi-Turn Queries](#9-session-memory-and-multi-turn-queries)
10. [Role-Based Personalization](#10-role-based-personalization)
11. [Complete Example Walkthrough](#11-complete-example-walkthrough)
12. [Advantages of This Architecture](#12-advantages-of-this-architecture)
13. [Limitations and Future Improvements](#13-limitations-and-future-improvements)

---

## 1. System Overview

### 1.1 The Problem

Business analysts and product managers need to query analytics data daily. The traditional path is:

1. Write a SQL query manually (requires SQL knowledge)
2. Copy results into Excel or a BI tool
3. Manually describe what the data means

This creates a hard dependency on engineers or data analysts for every ad-hoc question. Questions like *"Which channel has the highest publish rate this month?"* should not require a SQL expert.

### 1.2 What This System Does

This system accepts a plain-English question and returns:

- The **SQL query** that was run
- The **raw data rows** from the database
- A **recommended chart type** with axis mappings and a title
- A **natural language answer** summarising the key insight
- Optionally, **additional AI-generated chart suggestions** (via LIDA)

No SQL knowledge is required from the user.

### 1.3 Technology Stack

| Layer | Technology | Role |
|---|---|---|
| API | FastAPI (Python) | HTTP interface, request validation, pipeline orchestration |
| LLM Provider | OpenAI / Gemini / Groq | SQL generation, self-healing, answer generation |
| RAG Engine | Vanna.AI + ChromaDB | Text-to-SQL with a persistent knowledge base |
| Database | PostgreSQL (psycopg2) | SQL execution, data storage |
| Data Processing | Pandas | DataFrame handling, LIDA input preparation |
| Visualization AI | LIDA + Altair | Optional AI-generated Vega-Lite chart specifications |
| Config | Pydantic Settings | Centralised, environment-driven configuration |

### 1.4 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          CLIENT (Frontend)                          │
│                POST /nlq/query { question, session_id, explore }    │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         FastAPI Backend                             │
│                                                                     │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────────────┐ │
│  │   Session   │    │  Vanna RAG   │    │   Self-Healing SQL     │ │
│  │   Service   │───▶│   Engine     │───▶│     Executor           │ │
│  └─────────────┘    └──────────────┘    └────────────┬───────────┘ │
│                            │                         │             │
│                     ┌──────┴───────┐                 ▼             │
│                     │  ChromaDB    │        ┌─────────────────┐    │
│                     │  (Vector KB) │        │   PostgreSQL    │    │
│                     └──────────────┘        └────────┬────────┘    │
│                                                      │             │
│  ┌──────────────────┐   ┌──────────────┐            │             │
│  │  LIDA Insight    │◀──│   Pandas     │◀───────────┘             │
│  │  Engine          │   │  DataFrame   │                           │
│  └──────────────────┘   └──────────────┘                           │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              LLM Answer Generator (call_llm)                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.5 Pipeline Overview (Quick Reference)

```
User Question
     │
     ▼ Step 1
[Load Session Context]
 - Retrieve last SQL from session store (enables follow-up queries)
     │
     ▼ Step 2
[Vanna RAG → SQL Generation]
 - Vector similarity search over schema + Q→SQL examples
 - LLM generates SQL + chart metadata JSON
     │
     ▼ Step 3
[Self-Healing SQL Execution]
 - Execute SQL on PostgreSQL
 - On failure: send error + schema to LLM for correction
 - Retry up to MAX_SQL_RETRIES times
     │
     ▼ Step 4 (conditional — only when explore=true)
[LIDA Insight Engine]
 - Summarise DataFrame
 - Generate N additional chart goals
 - Produce Vega-Lite specs
     │
     ▼ Step 5
[LLM Answer Generator]
 - Convert raw rows into a 2-4 sentence plain-English insight
     │
     ▼ Step 6
[Store Q→SQL in Vanna KB]
 - Persist verified question→SQL pair to ChromaDB
 - Improves future retrieval accuracy
     │
     ▼ Step 7
[Update Session Context]
 - Store final SQL + question in session for next turn
     │
     ▼
[Return QueryResponse to Client]
 sql, data, chart_type, x, y, title, description, insights
```

---

## 2. End-to-End Pipeline Flow

### Step 1 — Load Session Context

**What happens:**
Before generating any SQL, the system loads the session context for the given `session_id`. Sessions are lightweight in-memory stores (keyed by `session_id`) that hold the question and SQL from the previous turn.

**Input:** `session_id` string from the request.

**Output:** `previous_sql` (string or `None` if this is the first question in the session).

**Why it is needed:**
Users rarely ask isolated one-off questions. More commonly they ask follow-ups:

```
Turn 1: "Show monthly uploads by channel"
Turn 2: "Now filter to only Hindi"
Turn 3: "Sort by descending volume"
```

Without session memory, Turn 2 has no context about what "it" refers to. The previous SQL is injected into the Vanna prompt so the LLM modifies the existing query rather than generating from scratch.

**What could go wrong:**
If the session store is cleared (e.g., server restart), `previous_sql` becomes `None` and the follow-up is treated as a fresh question. This is a graceful degradation — the query still runs, it just loses conversation context.

---

### Step 2 — Vanna RAG → SQL Generation

**What happens:**
The user question (optionally prefixed with `previous_sql` and a role context) is sent to Vanna.AI. Vanna performs a vector similarity search over its ChromaDB knowledge base to find the most relevant:

- DDL schema blocks
- Documentation strings
- Previously verified question → SQL examples

These retrieved documents are assembled into a few-shot prompt and sent to the configured LLM (OpenAI / Gemini / Groq). The LLM returns a SQL query plus a JSON block with chart metadata.

**Input:**
```
question       = "Top 5 clients by output volume"
previous_sql   = None  (or a prior SQL for follow-ups)
user_role      = "founder"
```

**Output:** A `VannaResult` dataclass:
```python
VannaResult(
    sql        = "SELECT client_id, COUNT(*) AS output_count ...",
    chart_type = "bar",
    x_column   = "client_id",
    y_column   = "output_count",
    title      = "Top 5 Clients by Output Volume"
)
```

**Why it is needed:**
Raw LLM prompting without RAG would require sending the entire schema on every call (expensive, slow, error-prone). Vanna's vector search selects only the most relevant schema context, making prompts smaller and more accurate.

**What could go wrong:**
- The LLM may hallucinate table or column names not in the schema. This is caught by Step 3 (self-healing).
- The chart JSON block may be malformed or missing. The `_parse_vanna_output` parser handles this gracefully: it extracts what it can and leaves fields as `None`, which Step 3's `_fill_chart_meta` then infers from actual result data.
- Quota/rate-limit errors (HTTP 429) are handled by a retry loop with exponential backoff.

---

### Step 3 — Self-Healing SQL Execution

**What happens:**
The SQL from Step 2 is executed against PostgreSQL. If it succeeds, results are returned immediately. If it fails (any `psycopg2.Error` or Python exception), the error message, the original SQL, the full live schema, and the original user question are packaged into a correction prompt and sent to the LLM. The LLM returns a corrected SQL, which is then executed again. This loop runs up to `MAX_SQL_RETRIES` times (default: 2).

**Input:**
```
sql            = "SELECT ... FROM data.fact_videos ..."   ← may reference a bad table
question       = "Top 5 clients by output volume"
```

**Output:**
```python
(final_sql, rows, df)
# final_sql  = corrected (or original) SQL string
# rows       = list[dict]  — raw query results
# df         = pandas.DataFrame of rows
```

**Why it is needed:**
Even the best LLMs make mistakes — wrong column names, non-existent tables, bad type casts. Without self-healing, ~15-25% of queries would return errors to the user. Self-healing converts most of those into recoverable situations silently.

**What could go wrong and how it is handled:**

| Failure | Handling |
|---|---|
| Wrong table name | LLM sees available table list in the heal prompt — corrects to an existing table |
| Wrong column name | Schema DDL in the heal prompt shows exact column names |
| Type mismatch (e.g. `uploaded_at::timestamp`) | Error message from PostgreSQL is specific enough for LLM to fix the cast |
| Placeholder SQL (`SELECT 0`) | The heal prompt explicitly forbids dummy SQL |
| All retries exhausted | HTTP 500 is returned with the final error message |

---

### Step 4 — Optional LIDA Insight Engine

**What happens (only when `explore=true`):**
LIDA receives the Pandas DataFrame from Step 3. It:
1. **Summarises** the DataFrame (column types, value ranges, sample values)
2. **Generates** up to `LIDA_MAX_GOALS` (default: 3) additional chart goals — questions that the data can answer beyond the original query
3. **Visualises** each goal as an Altair/Vega-Lite chart specification
4. Returns the specs with inline data so the frontend can render them without a second API call

**Input:** `pandas.DataFrame`, original question string, optional user role.

**Output:** `List[LidaInsight]` where each insight contains:
```python
LidaInsight(
    title      = "Distribution of publish rates by language",
    chart_spec = { "$schema": "...", "mark": "bar", "encoding": {...}, "data": {"values": [...]} }
)
```

**Why it is needed:**
A user asking *"show me published videos by channel"* may not know to also ask about language breakdown or time trend. LIDA proactively surfaces these additional angles, making the analytics experience more explorative.

**What could go wrong:**
- LIDA chart generation for a specific goal may fail (e.g., the LLM generates invalid Vega-Lite). This is caught per-goal — failed goals are skipped, others still return.
- If the DataFrame is empty, LIDA is skipped entirely.
- LIDA is non-critical; any error returns an empty list without failing the main response.

---

### Step 5 — LLM Answer Generator

**What happens:**
A second LLM call converts the raw tabular data into a human-readable analytics sentence. The prompt includes the original question, the executed SQL, and up to 20 rows of results. The system prompt is customised per user role (e.g., "You are presenting findings to a company founder").

**Input:**
```
question = "Top 5 clients by output volume"
sql      = "SELECT client_id, COUNT(*) AS output_count ..."
data     = [{"client_id": 42, "output_count": 1820}, ...]
user_role = "founder"
```

**Output:**
```
"Client 42 leads output volume with 1,820 videos, followed by Client 17 with 1,340.
The top 5 clients collectively account for 68% of total output this quarter,
suggesting heavy concentration among a small number of accounts."
```

**Why it is needed:**
Raw tabular data requires the user to interpret numbers themselves. A natural language summary immediately answers the *"so what?"* question, making the analytics accessible to non-technical stakeholders.

**What could go wrong:**
If the LLM call fails (network error, quota), the system falls back gracefully to a simple `"Query returned N rows."` string rather than failing the entire response.

---

### Step 6 — Knowledge Base Update

**What happens:**
After a successful SQL execution, the verified `(question → sql)` pair is stored back into Vanna's ChromaDB knowledge base via `vn.train(question=..., sql=...)`. This happens asynchronously in the background and does not block the response.

**Why it is needed:**
Every successful query teaches the system. The next time a similar question is asked, the verified SQL appears in the RAG retrieval results, increasing the probability of correct SQL generation without an LLM re-deriving the logic from scratch.

**What could go wrong:**
ChromaDB write failures are non-fatal — logged as warnings and silently skipped. The user response is unaffected.

---

### Step 7 — Update Session Context

**What happens:**
The session store is updated with the current `question` and `final_sql` (the SQL that actually ran successfully, which may differ from what Vanna originally generated if self-healing was triggered).

This `final_sql` becomes the `previous_sql` for the next turn in this session.

---

## 3. Vanna.AI Architecture

### 3.1 What is Vanna

Vanna.AI is an open-source Python framework that implements **Retrieval-Augmented Generation (RAG) for Text-to-SQL**. It solves a fundamental problem with raw LLM SQL generation: LLMs have a knowledge cutoff, don't know your specific schema, and can't benefit from past corrections without retraining.

Vanna gives the LLM three things it would otherwise lack:

1. **Your schema** (DDL statements describing your tables, columns, and types)
2. **Your documentation** (plain English explanations of what columns and tables mean)
3. **Verified examples** (real question → SQL pairs that have already been tested)

All of this is stored in a vector database (ChromaDB in our setup) and retrieved at query time.

### 3.2 Vanna's Internal RAG System

```
At Training Time:
──────────────────────────────────────────────────────────────────────
Schema DDL ──┐
             │  embed (text → vector)
Documentation├──────────────────────────────▶  ChromaDB collections
             │
Q→SQL pairs ─┘

At Query Time:
──────────────────────────────────────────────────────────────────────
User Question ──▶ embed ──▶ similarity search ──▶ top-K documents
                                                        │
                                                        ▼
                              [schema DDL relevant to this question]
                              [documentation relevant to this question]
                              [similar Q→SQL pairs as few-shot examples]
                                                        │
                                                        ▼
                              assembled into a few-shot LLM prompt
                                                        │
                                                        ▼
                                              LLM generates SQL
```

The key insight is that **only the most relevant context is retrieved**, not the entire schema. For a large database with 100 tables, only the 3-5 tables most likely needed for this question will appear in the prompt.

### 3.3 What Vanna Stores

Vanna organises its ChromaDB into separate collections for each training data type:

**DDL (Schema):**
```sql
CREATE TABLE data.shortened_filtered_data (
    video_id      BIGINT,
    published     TEXT,
    language      TEXT,
    channel       TEXT,
    ...
);
```
These tell the LLM what tables and columns exist and what data types they hold.

**Documentation:**
```
The PRIMARY table for all video analytics queries is: data.shortened_filtered_data

Key columns:
- published: TEXT — indicates whether a video was published. Use: LOWER(published) = 'yes'
- language: TEXT — language name (e.g. 'English', 'Spanish'). No join needed.
```
These tell the LLM *how* to use the schema correctly (e.g., the `published` column is a TEXT field, not a boolean — never use `WHERE published = TRUE`).

**Question → SQL Pairs:**
```
Q: "how many videos have been published"
A: SELECT COUNT(*) AS published_count FROM data.shortened_filtered_data
   WHERE LOWER(published) = 'yes';
```
These act as few-shot examples: when a similar question is asked, the LLM sees a concrete correct example and mimics its pattern.

### 3.4 How Retrieval Works

When a user asks a question:

1. The question is converted to a dense embedding vector by the same embedding model used at training time.
2. ChromaDB performs approximate nearest-neighbour (ANN) search over all stored embeddings.
3. The top-K most similar documents (from all three collections) are returned.
4. These are assembled into the system prompt for the LLM.

The result: the LLM sees *"here are the relevant tables, here are usage notes, and here are examples of similar questions answered correctly"* — without ever seeing the full schema.

### 3.5 How It Improves Over Time

Every successful query (one that executes without error) is stored back into the knowledge base:

```python
vn.train(question="Top 5 clients by output volume",
         sql="SELECT client_id, COUNT(*) AS output_count ...")
```

Over time, as the system is used, the knowledge base grows. Frequently asked questions will have multiple verified SQL examples in the store, making retrieval highly reliable. The system literally gets smarter with every correct query it processes.

### 3.6 Chart Specification Generation

We extend Vanna's standard SQL generation by appending a chart inference suffix to every prompt:

```
After writing the SQL, also output a JSON block (fenced with ```json```) with:
{
  "chart_type": "line|bar|pie|table|scatter",
  "x_column": "<column name for x-axis or category>",
  "y_column": "<column name for y-axis or value>",
  "title": "<short descriptive chart title>"
}

Rules:
- Time series (month/date/year trend) → line
- Category vs numeric value → bar
- Part-of-whole (percentage/share) → pie
- Two continuous numeric columns → scatter
- Otherwise → table
```

The `_parse_vanna_output` function then splits the raw LLM output into the SQL portion and the JSON portion:

```python
def _parse_vanna_output(raw: str) -> tuple[str, dict]:
    # 1. Extract ```json ... ``` block
    # 2. Remove the JSON block from the raw string
    # 3. Strip any remaining ```sql fences
    # 4. Return (clean_sql, chart_metadata_dict)
```

If the LLM omits or malforms the chart JSON, `_fill_chart_meta` in `routes.py` infers the chart metadata from the actual result columns (checking for numeric vs text columns and time-related column names).

### 3.7 How Vanna Integrates Into Our Pipeline

**What we send to Vanna:**
```python
vanna_service.generate_sql(
    question   = augmented_question,  # may include previous_sql + role context + chart rules
    previous_sql = "SELECT ...",       # injected for follow-up queries
    user_role  = "founder",
)
```

The `augmented_question` that reaches Vanna's `generate_sql()` is built up in layers:

```
[Answering for: Founder / CEO]
Focus: Prioritise high-level business metrics: overall publish rates...

Previous SQL: SELECT ...   ← only if follow-up query

Top 5 clients by output volume  ← original question

After writing the SQL, also output a JSON block...  ← chart inference suffix
```

**What we receive from Vanna:**
```
SELECT
  client_id,
  COUNT(*) AS output_count
FROM data.shortened_filtered_data
GROUP BY client_id
ORDER BY output_count DESC
LIMIT 5;

```json
{
  "chart_type": "bar",
  "x_column": "client_id",
  "y_column": "output_count",
  "title": "Top 5 Clients by Output Volume"
}
```

The `_parse_vanna_output` function then separates this into the SQL string and the chart metadata dict.

---

## 4. Self-Healing SQL Mechanism

### 4.1 Why SQL Errors Happen

Even with a well-populated RAG knowledge base, SQL generation errors occur for several reasons:

- **Hallucinated table names:** The LLM invents a table like `fact_videos` when only `data.shortened_filtered_data` exists.
- **Hallucinated column names:** The LLM uses `publish_status` when the real column is `published`.
- **Wrong type casting:** A column stored as `TEXT` is cast to `INTEGER` incorrectly.
- **Wrong schema prefix:** Using `public.videos` instead of `data.shortened_filtered_data`.
- **Ambiguous questions:** The LLM misinterprets the intent and generates syntactically valid but semantically wrong SQL (e.g., counts rows instead of sums a column).

### 4.2 Retry Mechanism

```
sql = vanna_result.sql
question = request.question

for attempt in range(max_retries + 1):   # default: 3 total attempts
    try:
        rows = execute_query(sql)
        return sql, rows                 # success — exit immediately

    except (psycopg2.Error, Exception):
        if attempt >= max_retries:
            raise                        # all retries exhausted

        sql = heal_sql(
            original_sql   = sql,
            error_message  = str(exception),
            question       = question,
        )
        # loop continues with the corrected sql
```

### 4.3 What the Heal Prompt Contains

The `heal_sql` function sends the LLM this structured prompt:

```
You are a PostgreSQL expert. The following SQL query produced an error.

## Available Tables (ONLY use these)
data.shortened_filtered_data, ...

## Full Database Schema
CREATE TABLE data.shortened_filtered_data (
  video_id BIGINT,
  published TEXT,
  ...
);

## Original User Question
Top 5 clients by output volume

## Broken SQL
SELECT client_id, COUNT(*) FROM data.fact_videos ...

## Error
ERROR: relation "data.fact_videos" does not exist

Fix the SQL so it runs without errors using ONLY the tables listed above.
IMPORTANT: Do NOT generate placeholder/dummy SQL like SELECT 0 or SELECT 'data not available'.
Return ONLY the corrected SQL with no explanation, no markdown fences, no extra text.
```

The PostgreSQL error message is the key ingredient. It tells the LLM **exactly** what went wrong:
- `relation "X" does not exist` → wrong table
- `column "Y" does not exist` → wrong column
- `operator does not exist: text = boolean` → type mismatch
- `syntax error at or near "Z"` → malformed SQL

The live schema (fetched fresh from the database, not cached) ensures the LLM corrects to an actually existing table/column.

### 4.4 Limitations

- **Semantic errors** are not caught. If the SQL runs without error but answers the wrong question (e.g., it counts `uploaded_by` instead of `client_id`), self-healing will not trigger.
- **Complex multi-table queries** may require multiple healing rounds to get all joins right.
- **MAX_SQL_RETRIES is 2 by default** (3 total attempts). Questions requiring more than 2 corrections will return an HTTP 500.
- **LLM heal calls are not free** — each retry adds latency (~1-3 seconds) and consumes tokens.

---

## 5. PostgreSQL Execution Layer

### 5.1 Connection Pool

The backend uses `psycopg2.pool.ThreadedConnectionPool` initialised at application startup:

```
minconn = 1
maxconn = 10
```

Connections are checked out from the pool before a query and returned immediately after, ensuring thread-safety for concurrent FastAPI requests. The pool is initialised from either a `DATABASE_URL` environment variable (Supabase connection string format) or individual `DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD` variables.

A custom URL parser handles passwords containing special characters (`&`, `/`, `*`, `+`) which would break Python's standard `urlparse`.

### 5.2 Query Execution

```python
def execute_query(sql: str) -> List[Dict[str, Any]]:
    conn = pool.getconn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = cur.fetchall()
        return [dict(row) for row in rows]
    pool.putconn(conn)
```

`RealDictCursor` makes every row a Python dict keyed by column name rather than a tuple. This means column names are preserved through the entire pipeline — the frontend receives `{"language": "English", "count": 4200}` rather than `("English", 4200)`.

### 5.3 Data Format Through the Pipeline

```
PostgreSQL rows
      │
      ▼  RealDictCursor → list[dict]
[{"language": "English", "count": 4200}, ...]
      │
      ▼  _flatten_rows() in routes.py
Nested dicts/lists (JSONB columns) → JSON strings
      │
      ├──▶  rows  (list[dict])  → JSON response body
      │
      └──▶  pd.DataFrame(rows) → LIDA, chart inference
```

Converting to Pandas DataFrame gives LIDA access to column dtypes (float, int, object), value ranges, and sample values — all used by LIDA's summariser.

---

## 6. LIDA Architecture and Role

### 6.1 What is LIDA

LIDA (Language Interface for Data Analysis) is a library from Microsoft Research that uses LLMs to automatically generate visualizations and insights from datasets. It operates through four internal components:

```
┌─────────────────────────────────────────────────────────────────┐
│                        LIDA Pipeline                            │
│                                                                 │
│  DataFrame ──▶ [Summarizer] ──▶ [Goal Explorer] ──▶ [Viz Gen] │
│                    │                  │                │        │
│               Data summary      Chart questions   Vega-Lite    │
│               (column types,    ("What is the    spec + code   │
│                stats, samples)   distribution    generated     │
│                                  of X?")         by LLM        │
└─────────────────────────────────────────────────────────────────┘
```

**Summarizer:** Converts the DataFrame into a compact statistical summary including column names, data types, number of unique values, min/max, and sample values. This summary is much smaller than the raw data and fits in an LLM context window.

**Goal Explorer:** Given the data summary and a persona context (e.g., "You are generating insights for a Founder / CEO"), the LLM generates N visualisation goals — questions the data can answer. For example:
- *"What is the distribution of published vs unpublished videos by language?"*
- *"Which channels have the highest output volume?"*
- *"How does the publish rate vary across content types?"*

**Visualization Generator:** For each goal, LIDA asks the LLM to generate chart code (using Altair in our setup). The generated code is executed in a sandboxed environment and the resulting chart object is captured.

**Refinement:** If chart generation fails or the spec is invalid, LIDA can iterate and self-correct (similar to our SQL self-healing).

### 6.2 How LIDA is Triggered

LIDA only runs when the API request includes `explore: true`:

```python
if request.explore:
    insights = lida_service.generate_insights(
        df        = df,
        question  = request.question,
        user_role = request.user_role,
    )
```

This is intentional — LIDA makes 3-5 additional LLM calls (one per goal + one summarise + one per visualisation), adding significant latency. It is opt-in for "explore mode" only.

### 6.3 What LIDA Outputs in Our System

Each LIDA goal produces a `LidaInsight`:

```python
LidaInsight(
    title      = "Distribution of publish rates by language",
    chart_spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "mark": "bar",
        "encoding": {
            "x": {"field": "language", "type": "nominal"},
            "y": {"field": "publish_rate_pct", "type": "quantitative"}
        },
        "data": {
            "values": [
                {"language": "English", "publish_rate_pct": 74.2},
                {"language": "Spanish", "publish_rate_pct": 68.1},
                ...
            ]
        }
    }
)
```

The `_extract_spec` function ensures inline data is always embedded in the spec. Without this, Altair's `to_dict()` produces a spec that references a named Python dataset (`"data": {"name": "data-abc123"}`) which is meaningless in a JSON API response. We replace this with `"data": {"values": [...records...]}` so the frontend can render it independently.

### 6.4 Role-Aware LIDA Goals

The LIDA `persona` is customised per user role:

| Role | LIDA Persona Context |
|---|---|
| `founder` | Business growth trends, overall publish rates, top-performing channels |
| `client_success` | Per-client delivery rates, publish performance, clients needing attention |
| `operations` | Workflow throughput, upload durations, processing efficiency |
| `editorial` | Content type distribution, language performance, team contributions |
| `tech` | System usage patterns, data quality distributions, technical anomalies |

This ensures that when a founder and an operations engineer see insights from the same query, those insights are framed differently and highlight different aspects of the data.

---

## 7. LLM Answer Generation

### 7.1 Why a Second LLM Call is Needed

Step 2 (Vanna) uses the LLM to convert natural language to SQL. That is a code generation task.

Step 5 uses the LLM for a different purpose: **data interpretation**. It reads query results and writes a plain-English explanation of what the numbers mean. These are fundamentally different prompts requiring different instructions.

### 7.2 Prompt Structure

```python
prompt = f"""A user asked the following analytics question:{role_instruction}

Question: {question}

SQL executed:
{sql}

Results (up to 20 rows):
{preview}

Generate a clear, concise analytics answer in 2–4 sentences.
Focus on key numbers, trends, or comparisons visible in the data.
Do not mention SQL or technical details.
"""
```

The system prompt is role-specific:
```
# For a Founder / CEO:
"You are a data analyst presenting findings to a company founder or CEO.
Lead with the single most important business insight. Focus on growth,
efficiency, and strategic implications. Use percentages and comparisons.
Keep it under 4 sentences."

# For an Operations Team:
"You are a data analyst supporting an operations team.
Focus on efficiency, throughput, and identifying bottlenecks.
Highlight process metrics and operational KPIs..."
```

### 7.3 Data Preview Truncation

Only the first 20 rows are included in the answer prompt:

```python
preview = data[:20]
```

For a typical bar chart query returning 10 rows this is the full dataset. For time-series queries returning 365 rows, only the first 20 are included. This prevents the prompt from exceeding the LLM's context window while still providing enough data for a meaningful summary.

### 7.4 Fallback

If the LLM call fails for any reason:
```python
except Exception as exc:
    logger.warning("LLM answer generation failed: %s — using fallback.", exc)
    answer = f"Query returned {len(rows)} rows."
```

The user always receives a response. The description may be less rich, but the SQL, data, and chart metadata are unaffected.

---

## 8. Knowledge Base Update

### 8.1 When a Query is Considered Successful

A query is only stored in Vanna's knowledge base if it **executes successfully on PostgreSQL**. SQL that fails (even after self-healing attempts) is never stored. This prevents poisoning the knowledge base with bad examples.

The storage happens with the `final_sql` — the SQL that actually ran, not Vanna's original generated SQL. If self-healing corrected the SQL, it is the corrected version that gets stored.

### 8.2 Storage Mechanism

```python
vanna_service.store_successful_query(
    question = "Top 5 clients by output volume",
    sql      = "SELECT client_id, COUNT(*) AS output_count FROM data.shortened_filtered_data ...",
)

# Internally:
vn.train(question=question, sql=sql)
```

Vanna embeds the question text and stores the `(embedding, sql)` pair in ChromaDB. On future queries, when a question with similar embedding is asked, this pair appears as a few-shot example in the LLM prompt.

### 8.3 Feedback Loop Effect

```
Day 1: User asks "Top 5 clients by output"
       → Vanna has no example → relies purely on schema + documentation
       → LLM generates SQL with minor error → self-healing fixes it
       → Corrected SQL stored in KB

Day 2: Same user asks "Top 3 clients by output"
       → Vanna finds yesterday's example → includes it as few-shot
       → LLM generates correct SQL immediately, no self-healing needed

Week 3: System has accumulated 200+ verified examples
        → High retrieval accuracy, very few self-healing triggers
        → Faster responses, lower LLM token costs
```

---

## 9. Session Memory and Multi-Turn Queries

### 9.1 Why Session Memory is Needed

Analytical conversations are naturally iterative. A user rarely asks a complete, self-contained question the first time. They explore:

```
"Show me published videos by language"
"Now filter to last 30 days"
"Break that down by channel"
"Who are the top users in English?"
```

Each follow-up modifies the previous result. Without memory, every question must be entirely self-contained and the user must re-specify the full context each time.

### 9.2 What is Stored

The session store (in-memory dict keyed by `session_id`) stores:

```python
{
    "session_id_abc123": {
        "last_question": "Show me published videos by language",
        "last_sql": "SELECT language, COUNT(*) ... WHERE LOWER(published) = 'yes' ..."
    }
}
```

Only the most recent turn is stored — the system does not maintain a full conversation history. This is a deliberate simplicity trade-off.

### 9.3 How Follow-Up SQL Modification Works

When `previous_sql` is present, the augmented question sent to Vanna is:

```
Previous SQL:
SELECT language, COUNT(*) AS published_count
FROM data.shortened_filtered_data
WHERE LOWER(published) = 'yes'
GROUP BY language
ORDER BY language;

New question (modify the previous SQL to answer this):
Now filter to last 30 days
```

The LLM sees the exact SQL it needs to modify and makes targeted changes:

```sql
-- Modified SQL:
SELECT language, COUNT(*) AS published_count
FROM data.shortened_filtered_data
WHERE LOWER(published) = 'yes'
  AND uploaded_at::timestamp >= NOW() - INTERVAL '30 days'
GROUP BY language
ORDER BY language;
```

Rather than generating a completely new query (which might use different column aliases or table joins), the LLM surgically modifies the existing SQL. This produces more consistent, predictable results across conversation turns.

### 9.4 Session Isolation

Each `session_id` maintains independent context. A `session_id: "user_alice"` and `session_id: "user_bob"` are completely isolated — Bob's follow-up questions never interfere with Alice's context.

---

## 10. Role-Based Personalization

### 10.1 Overview

The API accepts an optional `user_role` field. Five roles are defined, each with distinct configuration for three parts of the pipeline:

| Pipeline Stage | How Role Affects It |
|---|---|
| Vanna SQL generation | `sql_focus` is prepended to the question, biasing the LLM toward role-relevant SQL |
| LLM answer generation | `answer_persona` is the system prompt for the answer LLM call |
| LIDA goal generation | `lida_context` is the LIDA persona for insight generation |

### 10.2 Defined Roles

| Key | Display Name | SQL Focus |
|---|---|---|
| `founder` | Founder / CEO | Business KPIs, publish rates, growth trends, channel performance |
| `client_success` | Client Success | Per-client delivery metrics, publish rates, SLA indicators |
| `operations` | Operations Team | Throughput, upload durations, bottlenecks, workflow efficiency |
| `editorial` | Editorial / Production | Content by language/channel/type, team contributions |
| `tech` | Tech / Product | System metrics, data quality, usage patterns, anomalies |

### 10.3 Example: Same Question, Different Roles

**Question:** *"Show me output by channel"*

**Founder SQL focus adds:**
```
Prioritise high-level business metrics: overall publish rates,
month-over-month growth trends, top-performing channels and clients...
```
→ LLM generates SQL that includes publish rate percentage alongside raw counts

**Operations SQL focus adds:**
```
Focus on operational efficiency: throughput volumes, upload-to-publish duration,
team output rates, workflow bottlenecks...
```
→ LLM generates SQL that includes `uploaded_hours` and duration metrics alongside counts

---

## 11. Complete Example Walkthrough

### User Query

```json
POST /nlq/query
{
    "question": "Which channel has the highest publish rate?",
    "session_id": "user_alice_session",
    "explore": false,
    "user_role": "founder"
}
```

### Step 1 — Session Load

`session_id = "user_alice_session"` is new → `previous_sql = None`.

### Step 2 — Vanna SQL Generation

Augmented question sent to Vanna:
```
[Answering for: Founder / CEO]
Focus: Prioritise high-level business metrics...

Which channel has the highest publish rate?

After writing the SQL, also output a JSON block...
```

Vanna retrieves from ChromaDB:
- DDL for `data.shortened_filtered_data`
- Documentation: *"Use LOWER(published) = 'yes' for published filter"*
- Q→SQL example: *"which channel has the highest publish rate"* (from initial training)

LLM generates:
```sql
SELECT
  channel,
  COUNT(*) AS total_videos,
  COUNT(CASE WHEN LOWER(published) = 'yes' THEN 1 END) AS published_videos,
  ROUND(
    100.0 * COUNT(CASE WHEN LOWER(published) = 'yes' THEN 1 END) / NULLIF(COUNT(*), 0),
    2
  ) AS publish_rate_pct
FROM data.shortened_filtered_data
GROUP BY channel
ORDER BY publish_rate_pct DESC
LIMIT 1;
```

```json
{
  "chart_type": "bar",
  "x_column": "channel",
  "y_column": "publish_rate_pct",
  "title": "Channel with Highest Publish Rate"
}
```

### Step 3 — SQL Execution

SQL executes successfully on first attempt.

```python
rows = [{"channel": "Alpha Studio", "total_videos": 3200, "published_videos": 2784, "publish_rate_pct": 87.0}]
df   = pd.DataFrame(rows)
```

### Step 4 — LIDA

Skipped (`explore: false`).

### Step 5 — LLM Answer

Prompt sent to LLM:
```
[Answering for: Founder / CEO]
Question: Which channel has the highest publish rate?
SQL: SELECT channel, ...
Results: [{"channel": "Alpha Studio", ..., "publish_rate_pct": 87.0}]
Generate a clear, concise analytics answer in 2–4 sentences...
```

Answer returned:
```
Alpha Studio leads all channels with an 87% publish rate, converting 2,784 of its
3,200 created videos into published content. This significantly outperforms the
company-wide average, making it the most efficient channel in the portfolio.
```

### Step 6 — Knowledge Base Update

```python
vn.train(
    question = "Which channel has the highest publish rate?",
    sql      = "SELECT channel, COUNT(*) AS total_videos ..."
)
```

### Step 7 — Session Update

```python
session["user_alice_session"] = {
    "last_question": "Which channel has the highest publish rate?",
    "last_sql": "SELECT channel, COUNT(*) ..."
}
```

### Final API Response

```json
{
  "question": "Which channel has the highest publish rate?",
  "sql": "SELECT channel, COUNT(*) AS total_videos, ...",
  "description": "Alpha Studio leads all channels with an 87% publish rate...",
  "chart_type": "bar",
  "x": "channel",
  "y": "publish_rate_pct",
  "title": "Channel with Highest Publish Rate",
  "data": [{"channel": "Alpha Studio", "total_videos": 3200, "published_videos": 2784, "publish_rate_pct": 87.0}],
  "columns": ["channel", "total_videos", "published_videos", "publish_rate_pct"],
  "row_count": 1,
  "insights": [],
  "processing_time_ms": 1843.2
}
```

---

## 12. Advantages of This Architecture

### 12.1 RAG vs Raw LLM Prompting

| Approach | Problem |
|---|---|
| Raw LLM (no RAG) | Must send full schema every call — expensive, slow, error-prone on large schemas |
| Fine-tuned model | Expensive to train, requires retraining when schema changes |
| **RAG (our approach)** | Retrieves only relevant context; schema updates are instant (just add new DDL to the KB) |

Vanna's RAG approach means the system improves **without retraining**. Adding a new table is as simple as calling `vn.train(ddl="CREATE TABLE ...")`.

### 12.2 Self-Healing vs Error Reporting

Without self-healing, LLM SQL errors would surface to users as cryptic database errors. The self-healing loop converts the majority of these into correct results transparently. From a user perspective, the query just works.

### 12.3 Accumulated Knowledge

Unlike a stateless API that is equally capable on day 1 and day 365, this system continuously improves. The ChromaDB knowledge base grows with every successful query. Frequently asked questions accumulate multiple verified SQL examples, which Vanna's retrieval will consistently surface, making those queries extremely reliable over time.

### 12.4 Role Personalization

A single analytics system serves multiple user personas meaningfully — a founder and an operations manager asking the same question get appropriately framed SQL, answers, and insights without maintaining separate systems.

### 12.5 Chart Inference

By asking the LLM to output chart metadata alongside SQL (and falling back to heuristic inference when needed), the frontend can render visualizations immediately without any additional chart-type detection logic. The system is self-describing.

---

## 13. Limitations and Future Improvements

### 13.1 Current Limitations

**Semantic errors are invisible to self-healing:**
If a generated SQL runs successfully but answers the wrong question (computes a simple count when a rate was asked for), there is no mechanism to detect this. The user sees a technically valid but analytically wrong result.

**Session memory is single-turn:**
Only the immediately previous SQL is stored. If a user says *"go back to the query from two steps ago"*, the system cannot comply. Full conversation history is not maintained.

**No query planning for complex questions:**
Multi-part questions like *"Show me the top 5 channels, and for each, the top 3 content types"* may produce a single flat query instead of a structured nested result. There is no query decomposition step.

**LIDA is stateless relative to the main query:**
LIDA's goal generation does not know what the user originally asked — it only sees the DataFrame. Its generated insights may not always be contextually relevant to the user's intent.

**Single-table bias:**
The training documentation explicitly directs the LLM to use `data.shortened_filtered_data` for all queries. Multi-table joins for complex dimension lookups are currently discouraged and may fail.

**In-memory session store:**
Sessions are lost on server restart. There is no persistent session storage (Redis, database) — sessions are Python dicts in the process memory.

### 13.2 Future Improvements

**Semantic layer (MetricFlow / Cube.js):**
A semantic layer sits between the LLM and PostgreSQL, pre-defining metrics (`publish_rate`, `output_volume`), dimensions, and relationships. The LLM generates against a controlled metric vocabulary rather than raw SQL, dramatically reducing the surface area for errors.

**Query decomposition / planning:**
For complex questions, an initial LLM step breaks the question into sub-questions, executes each independently, and combines results. This is similar to the "chain-of-thought" approach applied to SQL.

**Evaluation and feedback loop:**
A thumbs-up / thumbs-down signal from users on query results would allow the system to selectively add or remove examples from the knowledge base — removing bad examples that may have been stored after a query that ran without error but was semantically wrong.

**Persistent sessions:**
Replace the in-memory session dict with Redis or a database table. This enables session persistence across server restarts and multi-instance deployments.

**Advanced RAG:**
- Hybrid retrieval (dense + sparse/BM25 search) for better recall
- Re-ranking of retrieved documents before assembly into prompt
- Adaptive context window — dynamically adjust how many examples to include based on question complexity

**Multi-turn LIDA integration:**
Pass the original user question into LIDA's goal generation to bias the insights toward what the user actually cares about, rather than purely what the data can show.

**SQL validation layer:**
Before executing LLM-generated SQL, run a dry-run `EXPLAIN` to catch syntax and structural errors without scanning data. This is faster than a full execute → error → heal cycle.

---

*Document generated: 2026-03-17 | Backend version: Aryan_sqlrag_vanna branch*
