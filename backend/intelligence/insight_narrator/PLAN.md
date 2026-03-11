# Insight Narrator — Implementation Plan

## What it does
Reads aggregated performance data and generates a short, human-readable
narrative — think "editor's briefing" written by an AI. Different insight
types cover different lenses (executive summary, channel deep-dive, user
spotlight, content-mix breakdown).

---

## Approach (flexible)
1. Accept a request specifying `insight_type` + filters
2. Pull the relevant aggregated data (materialized views or direct query)
3. Serialize data into a compact table/JSON structure
4. Pass to LLM with a role-specific prompt ("you are a media analytics editor…")
5. Parse and return structured insight objects with category + severity tags

---

## API

### `POST /insights/generate`

**Request body**
```json
{
  "client_id":    1,
  "insight_type": "executive_summary",
  "channel_id":   null,
  "date_from":    "2024-09-01",
  "date_to":      "2024-11-30"
}
```

`insight_type` options (add more later):
- `executive_summary`
- `channel_deep_dive`   — requires `channel_id`
- `user_spotlight`
- `content_mix`

**Response**
```json
{
  "insights": [
    {
      "id":       "ins_001",
      "category": "performance",
      "severity": "high",
      "title":    "Overall publish rate declined 18% MoM",
      "body":     "In November, publish rate fell from 61% to 43% ...",
      "tags":     ["publish_rate", "month_over_month"]
    }
  ],
  "insight_type": "executive_summary",
  "generated_at": "2024-12-01T10:00:00Z"
}
```

---

### `GET /insights/`  *(already scaffolded)*
Returns cached / pre-generated insights for the dashboard feed.

---

## Notes / Decisions to make later
- Cache strategy: regenerate on every request vs store in DB with TTL
- Prompt tuning: generic vs client-specific tone instructions
- Number of insights to generate per call: 3–7 is a good default
