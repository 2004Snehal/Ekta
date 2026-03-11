# Forecasting — Implementation Plan

## What it does
Projects future values for key metrics (monthly outputs, publish rate, uploads)
using historical data from `mv_monthly_kpis` or direct aggregates.

---

## Approach (flexible — pick one at implementation time)
- **Option A — Statistical:** `statsmodels` ARIMA / Holt-Winters on the monthly
  time series. Lightweight, no LLM needed, interpretable confidence intervals.
- **Option B — Prophet:** `neuralprophet` or `prophet` for trend + seasonality
  decomposition. Good when data has yearly patterns.
- **Option C — LLM-assisted:** Send recent trend data to LLM, ask for a
  best-estimate projection + reasoning narrative. Suitable when data is sparse.

Start with **Option A** (simplest), layer B/C later.

---

## API

### `GET /forecasting/predict`

**Query params**
```
client_id   int     required
metric      string  required  — "total_outputs" | "publish_rate_pct" | "total_uploads"
channel_id  int     optional  — channel-level forecast
horizon     int     optional  — number of months ahead (default 3, max 12)
```

**Response**
```json
{
  "metric":   "total_outputs",
  "channel":  null,
  "horizon":  3,
  "history": [
    { "period": "2024-09", "actual": 1420 },
    { "period": "2024-10", "actual": 1380 },
    { "period": "2024-11", "actual": 1290 }
  ],
  "forecast": [
    { "period": "2024-12", "predicted": 1310, "lower": 1180, "upper": 1440 },
    { "period": "2025-01", "predicted": 1350, "lower": 1190, "upper": 1510 },
    { "period": "2025-02", "predicted": 1390, "lower": 1200, "upper": 1580 }
  ],
  "model":        "holt_winters",
  "generated_at": "2024-12-01T10:00:00Z"
}
```

---

### `GET /forecasting/models`
Returns available metric + model combinations for this client.

---

## Notes / Decisions to make later
- Minimum history required before forecasting is meaningful (~6 months)
- Whether to expose confidence intervals in the UI or just the point estimate
- Retraining cadence: on-demand vs nightly batch
