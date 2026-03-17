# Adding Navigation Depth to Frammer Analytics

## What was done

### URL-Param Based Drill-Down System
All drill-down state is carried via URL query params — stateless, shareable, back-button friendly.

URL pattern: `/dashboard/analysis?dim1=channel&filter_channel=CNN-IBN&from=summary`

---

### New Files

**`dashboard_frontend/lib/drill-down.ts`**
- `buildDrillUrl(targetPage, params)` — builds a URL string with dim1, dim2, metric, filter_*, from, group_by params
- `parseDrillParams(searchParams)` — parses URLSearchParams back into structured drill params

**`dashboard_frontend/components/DrillBreadcrumb.tsx`**
- Shows breadcrumb trail like `Summary → Analysis` with active filter chips
- Uses existing `components/ui/breadcrumb.tsx` primitives
- Only renders when `from` URL param is present

---

### Modified Files

**`dashboard_frontend/types/chart.ts`**
- Added `drillDown?` field to `UniversalChartSpec` — configures which dimension key to extract, target page, and param type (dim1 or filter)
- Added `refLinks?` field — array of `{ label, href }` shown as links below charts

**`dashboard_frontend/components/ChartRenderer.tsx`**
- New `onElementClick?(dimensionKey, value)` prop
- Click handlers wired on: `<Bar>`, `<Pie>`, `<Line activeDot>`, `<Scatter>`, stacked bars
- `cursor: 'pointer'` when drillDown is configured
- `<Brush>` zoom slider on line charts when data.length > 15
- "Show top N / Show all" toggle on bar charts with 10+ items
- Enhanced tooltip with "Click to drill down" hint when drillDown is present
- Ref links rendered below chart card

**`dashboard_frontend/components/CrossTabChart.tsx`**
- New `onBarClick?(dimensionValue)` prop
- Wired to both single-dimension horizontal bars and stacked vertical bars

**`dashboard_frontend/components/FunnelChart.tsx`**
- New `onGroupClick?(groupName)` prop
- Group name cells styled as clickable links (uplink color, pointer cursor)

**`dashboard_frontend/app/dashboard/page.tsx` (Summary)**
- Trend charts enriched with refLinks → Usage page
- Distribution charts enriched with drillDown → Analysis page + refLinks → Funnel
- `handleChartClick` uses `router.push(buildDrillUrl(...))` for client-side navigation

**`dashboard_frontend/app/dashboard/analysis/page.tsx`**
- Reads dim1, dim2, metric from URL params on mount via `useSearchParams()` + `parseDrillParams()`
- Applies `filter_*` params client-side on response rows
- Shows `<DrillBreadcrumb>` when `from` param is present
- Ref links to Funnel and Usage
- Passes `onBarClick` to CrossTabChart → navigates to Funnel filtered by clicked value

**`dashboard_frontend/app/dashboard/funnel/page.tsx`**
- Reads `group_by` from URL params for initial state
- Group names in FunnelChart table clickable → navigate to Analysis filtered by that group
- Conversion bar chart has drillDown config + refLinks
- Shows breadcrumb when navigated to from another page

**`dashboard_frontend/app/dashboard/usage/page.tsx`**
- Line charts configured with drillDown → Brush zoom auto-enabled (data > 15 points)
- Clickable activeDots → navigate to Analysis filtered by clicked period
- Ref links pointing to Analysis
- Shows breadcrumb when navigated to from another page

---

### Navigation Flow

```
Summary
  ├─ click bar/pie slice → Analysis (dim1 + filter pre-filled)
  ├─ "View in Usage →"   → Usage
  └─ "See Funnel →"      → Funnel (group_by pre-filled)

Analysis
  ├─ click bar           → Funnel (group_by + filter)
  ├─ "See Funnel →"      → Funnel
  └─ "See Usage →"       → Usage

Funnel
  ├─ click group name    → Analysis (dim1 + filter)
  ├─ click conversion bar→ Analysis (dim1 + filter)
  └─ "Analyze in Detail →"→ Analysis

Usage
  ├─ click line dot      → Analysis (filter by period)
  ├─ brush/zoom on lines → native recharts zoom
  └─ "View in Analysis →"→ Analysis
```

All pages show a breadcrumb with filter chips when arrived at via drill-down. Browser back button works naturally since state is in URL params.
