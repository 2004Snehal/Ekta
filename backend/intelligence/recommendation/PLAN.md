# Recommendation Agent — Implementation Plan

## What it does
Surfaces actionable recommendations for the operations team — things like
"Channel X has the lowest publish rate; here's what the top channels do
differently" or "User Y productivity dropped 30%; consider workload review".
Combines pattern detection (rule/statistical) with an LLM that frames the
finding as a concrete next action.

---

## Approach (flexible)
1. Pull relevant aggregates (channel health, user performance, content mix)
2. Run a scoring/ranking pass to identify the highest-impact gaps or patterns
3. For each finding, build a concise data snippet as LLM context
4. LLM generates: `title`, `action`, `rationale`, `priority`
5. Return ranked list; optionally persist for dashboard feed

---

## API

### `GET /recommendations/`

**Query params**
```
client_id   int     required
scope       string  optional  — "channel" | "user" | "content" | "all" (default)
channel_id  int     optional  — narrow to one channel
date_from   date    optional
date_to     date    optional
limit       int     optional  — max recommendations to return (default 5)
```

**Response**
```json
{
  "recommendations": [
    {
      "id":        "rec_001",
      "scope":     "channel",
      "subject":   "CNN Hindi",
      "priority":  "high",
      "title":     "Publish rate 22% below network average",
      "action":    "Review QC bottleneck in output review stage",
      "rationale": "CNN Hindi completes 310 outputs/month but publishes only 68. Top comparable channels publish >75%. Historical data shows the gap widened in Q3.",
      "supporting_metrics": {
        "publish_rate_pct": 21.9,
        "network_avg_pct":  61.0
      }
    }
  ],
  "generated_at": "2024-12-01T10:00:00Z"
}
```

---

### `POST /recommendations/feedback`
Records user feedback on a recommendation (helpful / not helpful).

**Request body**
```json
{
  "recommendation_id": "rec_001",
  "client_id":         1,
  "rating":            "helpful"
}
```

**Response**
```json
{ "status": "recorded" }
```

---

## Notes / Decisions to make later
- Rule-based scoring first, LLM framing second — keeps costs low
- Feedback loop: use thumbs up/down data to tune future prompt ranking
- Whether to auto-refresh recommendations nightly or only on-demand
