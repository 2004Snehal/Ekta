# Required Backend for Client-Side Dashboard Filtering

## Goal

The frontend is now designed to load a dataset window once, cache it in memory, and apply narrower filters locally. If the backend sends 90 days of rows, the frontend will use that same dataset for 7-day and 30-day views without calling the backend again. A new request is only needed when the requested range exceeds the cached coverage, for example switching from `last-90-days` to `all-time`.

## Required Endpoints

### `GET /dashboard`

Purpose: return raw dashboard records plus filter metadata for a single user and a requested coverage window.

Recommended query params:

```http
GET /dashboard?user_id=user_123&date_range=last-90-days
```

Supported `date_range` values:

- `last-7-days`
- `last-30-days`
- `last-90-days`
- `all-time`

Recommended response:

```json
{
  "user_id": "user_123",
  "requested_range": "last-90-days",
  "data_window": {
    "start_date": "2025-12-15",
    "end_date": "2026-03-14",
    "coverage_days": 90
  },
  "filter_fields": [
    { "key": "client", "label": "Client", "defaultVisible": true },
    { "key": "channel", "label": "Channel", "defaultVisible": true },
    { "key": "user", "label": "User", "defaultVisible": true },
    { "key": "language", "label": "Language", "defaultVisible": true },
    { "key": "type", "label": "Type", "defaultVisible": true },
    { "key": "platform", "label": "Platform", "defaultVisible": true },
    { "key": "workflow", "label": "Workflow" },
    { "key": "publisher", "label": "Publisher" },
    { "key": "content_bucket", "label": "Content Bucket" },
    { "key": "status", "label": "Status" }
  ],
  "records": [
    {
      "date": "2026-03-14",
      "client": "Frammer AI",
      "channel": "YouTube",
      "user": "Sneha",
      "language": "English",
      "type": "Short-form",
      "platform": "Mobile App",
      "workflow": "Auto",
      "publisher": "Internal",
      "content_bucket": "News",
      "status": "Published",
      "uploadedVideos": 72,
      "processedVideos": 68,
      "publishedVideos": 63,
      "promotedVideos": 30,
      "engagement": 11970,
      "avgDurationSeconds": 75
    }
  ]
}
```

Implementation notes:

- Return row-level or daily-grain records, not only pre-aggregated chart payloads.
- Every filterable frontend column should exist in `records` or be declared in `filter_fields`.
- Use a stable ISO date string for `date` in `YYYY-MM-DD` format.
- Include enough history in one response to support local narrowing.
- If the user selects `last-7-days`, you may still choose to return `last-90-days` and mark that coverage in `data_window`, which lets the frontend reuse the larger cache immediately.

### `GET /dashboard/state`

Purpose: restore the saved dashboard state for a user.

Recommended query params:

```http
GET /dashboard/state?user_id=user_123
```

Recommended response:

```json
{
  "userId": "user_123",
  "version": 1,
  "filters": {
    "dateRange": "last-90-days",
    "client": "Frammer AI",
    "channel": "all",
    "user": "all",
    "language": "English",
    "type": "all",
    "platform": "all",
    "extraFilters": [
      {
        "id": "workflow-1710001000",
        "field": "workflow",
        "value": "Auto"
      }
    ]
  },
  "filtersExpanded": true,
  "loadedRange": "last-90-days",
  "selectedKpiId": "average_duration",
  "updatedAt": "2026-03-14T09:15:00Z"
}
```

### `POST /dashboard/state`

Purpose: persist the current frontend state for a user.

Recommended request body:

```json
{
  "userId": "user_123",
  "version": 1,
  "filters": {
    "dateRange": "last-30-days",
    "client": "Frammer AI",
    "channel": "YouTube",
    "user": "Sneha",
    "language": "English",
    "type": "Short-form",
    "platform": "Mobile App",
    "extraFilters": [
      {
        "id": "publisher-1710002000",
        "field": "publisher",
        "value": "Internal"
      }
    ]
  },
  "filtersExpanded": true,
  "loadedRange": "last-90-days",
  "selectedKpiId": "average_duration",
  "updatedAt": "2026-03-14T09:16:00Z"
}
```

Recommended response:

```json
{
  "ok": true,
  "savedAt": "2026-03-14T09:16:00Z"
}
```

### `GET /dashboard/kpi-detail`

Purpose: return a detailed payload for a single KPI id when you want backend-driven drill-down instead of frontend-computed details.

Recommended query params:

```http
GET /dashboard/kpi-detail?user_id=user_123&kpi_id=average_duration&date_range=last-30-days
```

Recommended response:

```json
{
  "user_id": "user_123",
  "kpi_id": "average_duration",
  "detail": {
    "kpiId": "average_duration",
    "title": "Average Duration Detail",
    "subtitle": "Current selection: Last 30 days",
    "description": "Drill-down for longest videos and duration distribution.",
    "stats": [
      { "label": "Average Duration", "value": "74s" },
      { "label": "Max Duration", "value": "142s" }
    ],
    "charts": [
      {
        "chart_type": "bar",
        "title": "Top 10 Longest Videos",
        "axes": {
          "x": { "field": "video", "label": "Video" },
          "y": { "field": "duration", "label": "Duration (s)" }
        },
        "data": [
          { "video": "YT Clip 98", "duration": 142 }
        ]
      }
    ],
    "tableTitle": "Top 10 Longest Videos",
    "table": [
      {
        "date": "2026-03-14",
        "video": "YT Clip 98",
        "channel": "YouTube",
        "user": "Sneha",
        "duration_seconds": 142
      }
    ]
  }
}
```

Allowed `kpi_id` values:

- `uploaded_videos`
- `processed_videos`
- `published_videos`
- `publish_rate`
- `average_duration`

## Suggested Database Schema

Use one table for persisted dashboard state.

```sql
CREATE TABLE dashboard_state (
  user_id VARCHAR(128) PRIMARY KEY,
  version INT NOT NULL DEFAULT 1,
  filters_json JSONB NOT NULL,
  filters_expanded BOOLEAN NOT NULL DEFAULT TRUE,
  loaded_range VARCHAR(32) NOT NULL,
  selected_kpi_id VARCHAR(64),
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Meaning of columns:

- `user_id`: the lookup key for a single user's dashboard preferences.
- `version`: allows future state migrations.
- `filters_json`: stores the full frontend filter object including dynamic filters.
- `filters_expanded`: persists whether the filter panel is open.
- `loaded_range`: tracks the largest dataset window last used by the frontend.
- `selected_kpi_id`: remembers the last opened KPI detail view.
- `updated_at`: audit field and cache invalidation aid.

If your database does not support `JSONB`, use `TEXT` and store serialized JSON.

## Backend Behavior Requirements

- The backend should not require a round-trip for narrower frontend filters once a wider dataset window is already loaded.
- The backend should treat `user_id` as required for state endpoints.
- The data endpoint should return only fields the frontend can safely expose.
- If the backend provides additional filterable columns, include them in `filter_fields` so they appear in the frontend “Add Filter” menu.
- Keep field keys stable over time. The frontend stores them in saved state.
- Include `videoTitle` or `videoId` in `records` if you want meaningful "Top 10 longest videos" labels.
- `GET /dashboard/kpi-detail` is optional if frontend computes details locally, but required if you want backend-authored KPI drill-down content.

## Minimal FastAPI Shapes

Suggested Pydantic models:

```python
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


DateRange = Literal["last-7-days", "last-30-days", "last-90-days", "all-time"]
KpiId = Literal["uploaded_videos", "processed_videos", "published_videos", "publish_rate", "average_duration"]


class FilterField(BaseModel):
    key: str
    label: str
    defaultVisible: bool = False


class DynamicFilter(BaseModel):
    id: str
    field: str
    value: str


class DashboardFilters(BaseModel):
    dateRange: DateRange
    client: str = "all"
    channel: str = "all"
    user: str = "all"
    language: str = "all"
    type: str = "all"
    platform: str = "all"
    extraFilters: list[DynamicFilter] = Field(default_factory=list)


class DashboardState(BaseModel):
    userId: str
    version: int = 1
    filters: DashboardFilters
    filtersExpanded: bool = True
    loadedRange: DateRange
    selectedKpiId: KpiId | None = None
    updatedAt: datetime | None = None


class KpiStat(BaseModel):
    label: str
    value: str


class KpiDetail(BaseModel):
    kpiId: KpiId
    title: str
    subtitle: str
    description: str
    stats: list[KpiStat]
    charts: list[dict[str, Any]]
    tableTitle: str
    table: list[dict[str, Any]]


class DashboardDatasetResponse(BaseModel):
    user_id: str
    requested_range: DateRange
    data_window: dict[str, Any]
    filter_fields: list[FilterField]
    records: list[dict[str, Any]]


class DashboardKpiDetailResponse(BaseModel):
    user_id: str
    kpi_id: KpiId
    detail: KpiDetail
```

## Practical Sequence

1. Build `GET /dashboard/state` and `POST /dashboard/state` first.
2. Build `GET /dashboard` to return raw records plus `filter_fields`.
3. Make sure the date column is standardized.
4. Verify that a 90-day payload can support 7-day and 30-day filtering entirely in the browser.
5. Optionally implement `GET /dashboard/kpi-detail` if KPI detail content should come from backend instead of frontend aggregation.