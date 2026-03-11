# NLQ (Natural Language Query) — Implementation Plan

## Status: implemented (see context.py, llm.py, sql_rag.py)

## What it does
Accepts a plain-English question, converts it to SQL via an LLM with hardcoded
schema context, executes the query, and returns both the data and a chart spec
the frontend can render directly.

---

## Approach
1. Build system prompt from `SCHEMA_CONTEXT` + `client_id` safety injection
2. Call LLM (Gemini or OpenAI — toggled via `LLM_PROVIDER` in `.env`)
3. Validate LLM response shape + assert SELECT-only SQL
4. Inject `LIMIT 500` if missing
5. Execute query, serialize dates/Decimals, log to `query_log`
6. Return `{sql, chart_type, chart_config, data, row_count}`

---

## API

### `POST /nlq/query`

**Request body**
```json
{
  "question":  "Which channel had the highest publish rate last quarter?",
  "client_id": 1
}
```

**Response (success)**
```json
{
  "question":    "Which channel had the highest publish rate last quarter?",
  "sql":         "SELECT ...",
  "chart_type":  "bar",
  "chart_config": {
    "x_key": "channel_name",
    "y_keys": ["publish_rate_pct"],
    "title":  "Publish Rate by Channel — Q3 2024"
  },
  "data":      [ { "channel_name": "IBN7", "publish_rate_pct": 78.4 } ],
  "row_count": 1
}
```

**Response (error)**
```json
{
  "error":    "LLM returned non-SELECT SQL",
  "question": "...",
  "data":     []
}
```

---

## Possible extensions (not yet planned)
- Conversation history: multi-turn follow-up questions
- Query history: save successful queries per client for reuse
- Semantic caching: skip LLM if the question matches a recent cached query
- pgvector: enable if/when extension becomes available for column-level context
