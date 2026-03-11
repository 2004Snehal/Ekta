# KPI Agent — Implementation Plan

## What it does
Monitors KPI values across time windows and surfaces anomalies, threshold
breaches, or notable shifts. Can be rule-based, statistical, or LLM-assisted.

---

## Approach (flexible)
1. Pull recent KPI snapshots from `mv_monthly_kpis` or direct aggregates
2. Compare against a baseline (rolling average, previous period, or fixed threshold)
3. Flag metrics that deviate beyond a configurable tolerance
4. Optionally pass flagged metrics to LLM for a one-line human-readable label
5. Persist alerts to a future `kpi_alerts` table (optional)

---

## API

### `GET /kpi-agent/alerts`

**Query params**
```
client_id   int     required
channel_id  int     optional  — filter to one channel
date_from   date    optional
date_to     date    optional
severity    string  optional  — "high" | "medium" | "low"
```

**Response**
```json
{
  "alerts": [
    {
      "metric":      "publish_rate_pct",
      "channel":     "CNN Hindi",
      "period":      "2024-11",
      "value":       34.2,
      "baseline":    61.0,
      "delta_pct":   -43.9,
      "severity":    "high",
      "label":       "Publish rate dropped sharply vs prior 3-month average"
    }
  ],
  "generated_at": "2024-12-01T10:00:00Z"
}
```

---

### `GET /kpi-agent/summary`
Returns a single paragraph narrative of the most important KPI movements.

**Query params** — same as above

**Response**
```json
{
  "narrative": "...",
  "period":    "2024-10 – 2024-11"
}
```

---

## Notes / Decisions to make later
- Threshold values: hardcoded defaults vs user-configurable per client
- Anomaly method: z-score / IQR / LLM comparison — pick at implementation time
- Persistence: store alerts in DB so dashboard can show historical alert feed
