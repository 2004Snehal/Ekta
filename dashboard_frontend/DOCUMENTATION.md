# Frammer AI — Dashboard Frontend Documentation

> **Stack:** Next.js 16 · React 19 · TypeScript 5 · Tailwind CSS v4 · Recharts 2 · Radix UI · Vercel Analytics  
> **Purpose:** Data-driven analytics dashboard for video processing and publishing metrics

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Folder Structure](#2-folder-structure)
3. [Tech Stack](#3-tech-stack)
4. [Component Reference](#4-component-reference)
   - 4.1 [ChartRenderer](#41-chartrenderer--the-universal-renderer)
   - 4.2 [KPICard](#42-kpicard)
   - 4.3 [InsightPanel](#43-insightpanel)
   - 4.4 [Filters](#44-filters)
   - 4.5 [Sidebar](#45-sidebar)
5. [Universal Chart Response Format](#5-universal-chart-response-format)
   - 5.1 [Schema](#51-schema)
   - 5.2 [Bar Chart](#52-bar-chart)
   - 5.3 [Line Chart](#53-line-chart)
   - 5.4 [Pie Chart](#54-pie-chart)
   - 5.5 [Scatter Plot](#55-scatter-plot)
   - 5.6 [Stacked Bar](#56-stacked-bar-multi-dimension)
   - 5.7 [Multi-Chart Dashboard Response](#57-multi-chart-dashboard-response)
   - 5.8 [Table Fallback](#58-table-fallback)
6. [ChartRenderer Logic](#6-chartrenderer-logic)
   - 6.1 [Field Resolution Strategy](#61-field-resolution-strategy)
   - 6.2 [Stacked Bar Pivot](#62-stacked-bar-pivot-long--wide)
7. [Backend API Contract](#7-backend-api-contract)
8. [Design System & Theming](#8-design-system--theming)
9. [Local Development](#9-local-development)
10. [Connecting to the Backend](#10-connecting-to-the-backend)
11. [Vercel Deployment](#11-vercel-deployment)
12. [Environment Variables](#12-environment-variables)
13. [Extending the Dashboard](#13-extending-the-dashboard)

---

## 1. Project Overview

The dashboard is a **data-driven, spec-driven frontend**.  
The backend decides:
- What SQL to run
- What `chart_type` to use
- What axis fields to map

The frontend's single job is to **receive a chart specification and render it** — exactly how Metabase, Apache Superset, and ChatGPT's Data Analysis tool work.

```
Backend                          Frontend
──────                           ────────
NL query → SQL → chart spec  →  ChartRenderer(spec) → pixel-perfect chart
```

---

## 2. Folder Structure

```
dashboard_frontend/
├── app/
│   ├── globals.css              # Global CSS variables (design tokens)
│   ├── layout.tsx               # Root layout: Sidebar + Vercel Analytics
│   └── dashboard/
│       └── page.tsx             # Main dashboard page (mock data → live API)
│
├── components/
│   ├── ChartRenderer.tsx        # ★ Universal chart renderer (bar/line/pie/scatter/stacked/table)
│   ├── KPICard.tsx              # Metric card with trend arrow
│   ├── InsightPanel.tsx         # AI insight cards with "Take Action" CTAs
│   ├── Filters.tsx              # Date range / client / channel / video-type filters
│   ├── Sidebar.tsx              # Fixed left navigation
│   ├── theme-provider.tsx       # next-themes dark/light provider
│   └── ui/                      # ~50 Radix UI + Tailwind shadcn components
│
├── types/
│   └── chart.ts                 # TypeScript types for the universal chart spec
│
├── hooks/
│   ├── use-mobile.ts
│   └── use-toast.ts
│
├── lib/
│   └── utils.ts                 # cn() Tailwind class merger
│
├── public/                      # Static assets (icons, images)
├── styles/
│   └── globals.css
│
├── .env.example                 # Environment variable template
├── next.config.mjs              # Next.js config (TypeScript error bypass for build)
├── vercel.json                  # Vercel deployment configuration
├── package.json
├── tsconfig.json
└── pnpm-lock.yaml
```

---

## 3. Tech Stack

| Layer | Library | Version | Purpose |
|-------|---------|---------|---------|
| Framework | Next.js | 16.1.6 | App Router, SSR, API routes |
| UI Library | React | 19.2.4 | Component model |
| Language | TypeScript | 5.7.3 | Type safety |
| Styling | Tailwind CSS | v4 | Utility-first CSS, design tokens |
| Charts | Recharts | 2.15.0 | `<BarChart>`, `<LineChart>`, `<PieChart>`, `<ScatterChart>` |
| Components | Radix UI | various | Accessible headless UI primitives |
| Icons | Lucide React | 0.564 | SVG icon set |
| Analytics | @vercel/analytics | 1.6.1 | Page-view tracking on Vercel |
| Package manager | pnpm | — | Faster installs, strict lockfile |

---

## 4. Component Reference

### 4.1 `ChartRenderer` — The Universal Renderer

**File:** [components/ChartRenderer.tsx](components/ChartRenderer.tsx)

The single most important component. It accepts **any** `UniversalChartSpec` object and delegates rendering to the correct Recharts chart.

#### Props

```typescript
interface Props {
  chart: UniversalChartSpec;  // Defined in types/chart.ts
}
```

#### Supported `chart_type` Values

| `chart_type` | Renderer | Required fields |
|---|---|---|
| `"bar"` | `<BarChart>` | `axes.x.field`, `axes.y.field`, `data` |
| `"line"` | `<LineChart>` | `axes.x.field`, `axes.y.field`, `data` |
| `"pie"` | `<PieChart>` | `category` (or `axes.x.field`), `value` (or `axes.y.field`), `data` |
| `"scatter"` | `<ScatterChart>` | `axes.x.field`, `axes.y.field`, `data` (numeric values) |
| `"stacked_bar"` | `<BarChart stackId>` | `axes.x.field`, `axes.y.field`, `group_by` (optional), `data` |
| `"table"` | HTML `<table>` | `data` |
| anything else | HTML `<table>` | `data` |

#### Backward Compatibility

The component supports **both** the new universal spec and the legacy flat format:

```typescript
// New universal format ✅
{ chart_type: "bar", axes: { x: { field: "channel" }, y: { field: "videos" } }, data: [...] }

// Legacy flat format ✅ (still works)
{ chart_type: "bar", x: "channel", y: "videos", data: [...] }
```

Field resolution priority: `axes.x.field` > `x` > `""`.

---

### 4.2 `KPICard`

**File:** [components/KPICard.tsx](components/KPICard.tsx)

Displays a single metric with a percentage change indicator.

```typescript
interface KPICardProps {
  title: string;        // e.g. "Uploaded Videos"
  value: string | number; // e.g. "1,245"
  change: number;       // e.g. 12 (positive) or -3 (negative)
  timeframe: string;    // e.g. "vs last week"
  icon?: React.ReactNode; // Lucide icon
}
```

Green arrow for positive `change`, red arrow for negative.

---

### 4.3 `InsightPanel`

**File:** [components/InsightPanel.tsx](components/InsightPanel.tsx)

Renders a list of AI-generated insight cards.

```typescript
interface InsightPanelProps {
  insights: {
    title: string;
    description: string;
    actionable?: boolean; // Shows "Take Action →" button when true
  }[];
}
```

---

### 4.4 `Filters`

**File:** [components/Filters.tsx](components/Filters.tsx)

Collapsible filter bar with four controls:

| Control | Options |
|---|---|
| Date Range | Last 7 Days, Last 30 Days, Last 90 Days, All Time |
| Client | All, Client A, Client B |
| Channel | All, YouTube, TikTok, Instagram, LinkedIn |
| Video Type | All, Short-form, Long-form, Live |

```typescript
interface FiltersProps {
  onApply?: (filters: FilterState) => void; // Called on every change
}
```

Filters propagate up via `onApply` so the parent page can re-fetch data.

---

### 4.5 `Sidebar`

**File:** [components/Sidebar.tsx](components/Sidebar.tsx)

Fixed 256 px left navigation. Routes:

| Label | Path |
|---|---|
| Dashboard | `/dashboard` |
| Natural Language Query | `/query` |
| KPI Lab | `/kpi-lab` |
| Data Manager | `/data` |

Active state is derived from `usePathname()`.

---

## 5. Universal Chart Response Format

Every backend analytics endpoint **must** return a response that conforms to the schema below.  
The frontend reads only `chart_type`, `axes`, `category`, `value`, `group_by`, and `data`.

### 5.1 Schema

```json
{
  "visualization": {
    "id": "chart_1",
    "title": "Videos by Channel",
    "chart_type": "bar",
    "description": "Distribution of processed videos across channels",

    "axes": {
      "x": { "field": "channel",     "label": "Channel" },
      "y": { "field": "video_count", "label": "Videos"  }
    },

    "data": [
      { "channel": "News",     "video_count": 120 },
      { "channel": "Sports",   "video_count": 90  },
      { "channel": "Politics", "video_count": 60  }
    ],

    "meta": {
      "generated_sql": "SELECT channel, COUNT(*) as video_count FROM videos GROUP BY channel",
      "row_count": 3
    }
  },

  "table":   [ /* mirrors visualization.data */ ],
  "sql":     "SELECT channel, COUNT(*) ...",
  "insight": "News channels account for the highest number of processed videos."
}
```

**TypeScript type:** `AnalyticsResponse` in [types/chart.ts](types/chart.ts).

---

### 5.2 Bar Chart

```json
{
  "visualization": {
    "chart_type": "bar",
    "title": "Videos by Channel",
    "axes": {
      "x": { "field": "channel", "label": "Channel" },
      "y": { "field": "videos",  "label": "Video Count" }
    },
    "data": [
      { "channel": "AajTak", "videos": 120 },
      { "channel": "NDTV",   "videos": 95  }
    ]
  }
}
```

`x-axis → channel` · `y-axis → videos`

---

### 5.3 Line Chart

```json
{
  "visualization": {
    "chart_type": "line",
    "title": "Processing Trend",
    "axes": {
      "x": { "field": "date",             "label": "Date" },
      "y": { "field": "processed_videos", "label": "Videos Processed" }
    },
    "data": [
      { "date": "2026-01-01", "processed_videos": 20 },
      { "date": "2026-01-02", "processed_videos": 35 },
      { "date": "2026-01-03", "processed_videos": 30 }
    ]
  }
}
```

Renders as a time-series line. No additional configuration needed.

---

### 5.4 Pie Chart

Pie charts use `category` (slice labels) and `value` (slice sizes) instead of `axes`.

```json
{
  "visualization": {
    "chart_type": "pie",
    "title": "Output Distribution",
    "category": "output_type",
    "value": "count",
    "data": [
      { "output_type": "reels",    "count": 120 },
      { "output_type": "shorts",   "count": 80  },
      { "output_type": "chapters", "count": 40  }
    ]
  }
}
```

`category → slice labels` · `value → slice size`

> You can also use `axes.x.field` / `axes.y.field` — the renderer will fall back gracefully.

---

### 5.5 Scatter Plot

Used for correlation analysis.

```json
{
  "visualization": {
    "chart_type": "scatter",
    "title": "Duration vs Publish Probability",
    "axes": {
      "x": { "field": "duration",            "label": "Duration (s)" },
      "y": { "field": "publish_probability", "label": "Publish Probability" }
    },
    "data": [
      { "duration": 60,  "publish_probability": 0.2 },
      { "duration": 120, "publish_probability": 0.7 },
      { "duration": 90,  "publish_probability": 0.4 }
    ]
  }
}
```

Both axis fields must be numeric.

---

### 5.6 Stacked Bar (Multi-dimension)

Supports **two data formats**:

#### Long format (recommended — with `group_by`)

```json
{
  "visualization": {
    "chart_type": "stacked_bar",
    "title": "Channel × Input Type",
    "axes": {
      "x": { "field": "channel" },
      "y": { "field": "videos"  }
    },
    "group_by": "input_type",
    "data": [
      { "channel": "News",   "input_type": "interview", "videos": 50 },
      { "channel": "News",   "input_type": "speech",    "videos": 70 },
      { "channel": "Sports", "input_type": "interview", "videos": 40 }
    ]
  }
}
```

The frontend automatically **pivots** long → wide format before rendering.

#### Wide format (no `group_by`)

```json
{
  "visualization": {
    "chart_type": "stacked_bar",
    "axes": { "x": { "field": "channel" } },
    "data": [
      { "channel": "News",   "interview": 50, "speech": 70 },
      { "channel": "Sports", "interview": 40, "speech": 20 }
    ]
  }
}
```

Every key except the x-axis field is treated as a series.

---

### 5.7 Multi-Chart Dashboard Response

Return an **array** of chart specs under the `charts` key for dashboard pages.

```json
{
  "charts": [
    {
      "chart_type": "line",
      "title": "Processing Trend",
      "axes": { "x": { "field": "date" }, "y": { "field": "videos" } },
      "data": [...]
    },
    {
      "chart_type": "pie",
      "title": "Output Distribution",
      "category": "output_type",
      "value": "count",
      "data": [...]
    }
  ]
}
```

Frontend renders it with:

```tsx
{response.charts.map((chart, i) => (
  <ChartRenderer key={i} chart={chart} />
))}
```

---

### 5.8 Table Fallback

When `chart_type` is `"table"` (or unrecognised), `ChartRenderer` renders an HTML table built from the `data` array. Column headers are derived from object keys with underscores converted to spaces.

---

## 6. ChartRenderer Logic

### 6.1 Field Resolution Strategy

```
Axis field priority (highest → lowest):
  axes.x.field  →  x  →  ""      (X axis)
  axes.y.field  →  y  →  yAxis   (Y axis)

Pie field priority:
  category      →  axes.x.field  →  x   (slice names)
  value         →  axes.y.field  →  y   (slice sizes)
```

This means the same `ChartRenderer` handles both the new universal spec **and** legacy flat-field specs without conditionals in consuming code.

### 6.2 Stacked Bar Pivot (Long → Wide)

When `group_by` is set, the renderer runs `pivotStackedData()` before passing data to Recharts:

```
Input (long):                      Output (wide):
{ channel: "News",                 [
  input_type: "interview",           { channel: "News",   interview: 50, speech: 70 },
  videos: 50 }                       { channel: "Sports", interview: 40 }
{ channel: "News",                 ]
  input_type: "speech",
  videos: 70 }
```

Recharts then maps each unique `group_by` value to a `<Bar stackId="a">`.

---

## 7. Backend API Contract

### `POST /analytics/query`

Natural language → chart spec.

**Request:**
```json
{ "query": "Which channels publish the most videos?" }
```

**Response:**
```json
{
  "visualization": {
    "id": "chart_1",
    "chart_type": "bar",
    "title": "Videos by Channel",
    "axes": {
      "x": { "field": "channel", "label": "Channel" },
      "y": { "field": "video_count", "label": "Videos" }
    },
    "data": [
      { "channel": "News",   "video_count": 120 },
      { "channel": "Sports", "video_count": 90  }
    ],
    "meta": { "generated_sql": "SELECT ...", "row_count": 2 }
  },
  "table":   [...],
  "sql":     "SELECT channel, COUNT(*) ...",
  "insight": "News channels account for the highest number of processed videos."
}
```

### `GET /analytics/dashboard`

Returns multiple charts for the overview page.

**Response:**
```json
{
  "charts": [ ...array of UniversalChartSpec... ],
  "kpis": [
    { "title": "Uploaded Videos", "value": 1245, "change": 12, "timeframe": "vs last week" }
  ]
}
```

### Connecting the Frontend

In [app/dashboard/page.tsx](app/dashboard/page.tsx), replace the `mockCharts` array with a `fetch` call:

```typescript
const [charts, setCharts] = useState<UniversalChartSpec[]>([]);

useEffect(() => {
  fetch(`${process.env.NEXT_PUBLIC_API_URL}/analytics/dashboard`)
    .then(r => r.json())
    .then(data => setCharts(data.charts));
}, [filters]);

// In JSX:
{charts.map((chart, i) => <ChartRenderer key={i} chart={chart} />)}
```

---

## 8. Design System & Theming

The dashboard uses a **dark-first** design system defined in [app/globals.css](app/globals.css) via CSS custom properties.

| Token | Value | Usage |
|---|---|---|
| `--background` | `#0B0B0B` | Page background |
| `--card` | `#141414` | Chart / card surfaces |
| `--primary` | `#FF4D5A` | Brand red — active states, CTAs |
| `--secondary` | `#2B2B2B` | Secondary surfaces, borders |
| `--muted-foreground` | `#9CA3AF` | Axis labels, secondary text |
| `--border` | `#2B2B2B` | Card and table borders |

Chart colour palette (in order): `#FF4D5A` · `#3B82F6` · `#06B6D4` · `#FB923C` · `#8B5CF6` · `#10B981`

Pass a custom `colors` array to any chart spec to override:
```json
{ "colors": ["#FFD700", "#C0C0C0", "#CD7F32"] }
```

---

## 9. Local Development

### Prerequisites

| Tool | Version | Install |
|---|---|---|
| Node.js | ≥ 18 | [nodejs.org](https://nodejs.org) |
| pnpm | ≥ 8 | `npm install -g pnpm` |
| Git | any | [git-scm.com](https://git-scm.com) |

### Step 1 — Clone / navigate to the project

```bash
cd ekta/dashboard_frontend
```

### Step 2 — Install dependencies

```bash
pnpm install
```

This installs Next.js, Recharts, Radix UI, Tailwind CSS and all other dependencies declared in `package.json`.

### Step 3 — Configure environment variables

```bash
# Windows PowerShell
Copy-Item .env.example .env.local

# macOS / Linux
cp .env.example .env.local
```

Open `.env.local` and set `NEXT_PUBLIC_API_URL`:

```env
# Point to your running backend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

If you do not have a backend running yet, leave the value empty — the dashboard renders **mock data** by default.

### Step 4 — Start the development server

```bash
pnpm dev
```

The dashboard will be available at **http://localhost:3000/dashboard**.

Hot-reload is enabled. Any change to `.tsx`, `.ts`, or `.css` files refreshes the browser instantly.

### Step 5 — Verify the build compiles

Before pushing or deploying, confirm there are no build errors:

```bash
pnpm build
```

Expected output: `✓ Compiled successfully` and an `.next/` output directory.

### Step 6 — Run a production-style server locally

```bash
pnpm build
pnpm start
```

Serves the optimised build at **http://localhost:3000**.

---

### Testing Chart Rendering Locally

You can inject any chart spec directly into [app/dashboard/page.tsx](app/dashboard/page.tsx) to test rendering without a backend.

**Example — test a pie chart:**

```typescript
const mockCharts: UniversalChartSpec[] = [
  {
    chart_type: 'pie',
    title: 'Output Type Distribution',
    category: 'output_type',
    value: 'count',
    data: [
      { output_type: 'Reels',    count: 120 },
      { output_type: 'Shorts',   count: 80  },
      { output_type: 'Chapters', count: 40  },
    ],
  },
];
```

**Example — test a stacked bar with `group_by`:**

```typescript
const mockCharts: UniversalChartSpec[] = [
  {
    chart_type: 'stacked_bar',
    title: 'Channel × Input Type',
    axes: { x: { field: 'channel' }, y: { field: 'videos' } },
    group_by: 'input_type',
    data: [
      { channel: 'News',   input_type: 'Interview', videos: 50 },
      { channel: 'News',   input_type: 'Speech',    videos: 70 },
      { channel: 'Sports', input_type: 'Interview', videos: 40 },
    ],
  },
];
```

Pass the array to `<ChartRenderer>` — it handles the pivot automatically.

---

### curl: Test a Backend Endpoint Locally

If the backend is running at `http://localhost:8000`:

```bash
curl -X POST http://localhost:8000/analytics/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Which channels publish the most videos?"}'
```

Paste the JSON response into `mockCharts` to validate rendering.

---

## 10. Connecting to the Backend

### Replace Mock Data

1. Open [app/dashboard/page.tsx](app/dashboard/page.tsx).
2. Add the following imports at the top:
   ```typescript
   import { useEffect } from 'react';
   import type { UniversalChartSpec } from '@/types/chart';
   ```
3. Replace the `mockCharts` constant with state:
   ```typescript
   const [charts, setCharts] = useState<UniversalChartSpec[]>([]);
   const [loading, setLoading] = useState(true);

   useEffect(() => {
     setLoading(true);
     fetch(`${process.env.NEXT_PUBLIC_API_URL}/analytics/dashboard`)
       .then(r => r.json())
       .then(data => { setCharts(data.charts ?? []); setLoading(false); })
       .catch(() => setLoading(false));
   }, [filters]);
   ```
4. In JSX, replace the static grid with:
   ```tsx
   {loading ? (
     <div className="text-muted-foreground">Loading charts…</div>
   ) : (
     <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
       {charts.map((chart, i) => <ChartRenderer key={i} chart={chart} />)}
     </div>
   )}
   ```

---

## 11. Vercel Deployment

The project is pre-configured for Vercel (see [vercel.json](vercel.json)).

### Option A — Deploy via Vercel CLI

```bash
# Install Vercel CLI globally once
npm install -g vercel

# From the dashboard_frontend directory
cd ekta/dashboard_frontend
vercel

# Follow the interactive prompts:
#   Set up and deploy? → Y
#   Which scope?       → Select your team/account
#   Link to existing?  → N (first time)
#   Project name:      → frammer-dashboard (or any name)
#   Root directory:    → ./  (already in dashboard_frontend)
#   Override settings? → N
```

### Option B — Deploy via Vercel Dashboard (GitHub)

1. Push the repository to GitHub.
2. Go to [vercel.com/new](https://vercel.com/new).
3. Import the GitHub repository.
4. Set **Root Directory** to `ekta/dashboard_frontend`.
5. Vercel auto-detects Next.js — leave build settings as defaults.
6. Add environment variables (see [§12](#12-environment-variables)).
7. Click **Deploy**.

### Production Build Commands

Vercel uses these commands automatically (configured in [vercel.json](vercel.json)):

| Step | Command |
|---|---|
| Install | `pnpm install` |
| Build | `pnpm build` |
| Output | `.next/` |

### CORS for the Backend

If the backend runs on a different domain from the Vercel deployment, configure CORS on the backend to allow the Vercel domain:

```python
# FastAPI example
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-app.vercel.app",   # add your Vercel URL
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Custom Domain

1. In the Vercel project settings → **Domains**.
2. Add your domain (e.g., `analytics.frammer.ai`).
3. Follow the DNS configuration instructions (usually a CNAME record).

---

## 12. Environment Variables

| Variable | Required | Example | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | Yes (for live data) | `https://api.frammer.ai` | Base URL of the analytics backend |

> Variables starting with `NEXT_PUBLIC_` are **bundled into the client JS** — never put secrets in them.

### Setting variables on Vercel

1. Project Settings → **Environment Variables**.
2. Add `NEXT_PUBLIC_API_URL` = your backend URL.
3. Apply to **Production**, **Preview**, and **Development** as needed.
4. Re-deploy for the changes to take effect.

---

## 13. Extending the Dashboard

### Add a New Chart Type

1. Add the type to the union in [types/chart.ts](types/chart.ts):
   ```typescript
   export type ChartType = 'bar' | 'line' | 'pie' | 'scatter' | 'stacked_bar' | 'table' | 'area';
   ```
2. Add a `case` block in [components/ChartRenderer.tsx](components/ChartRenderer.tsx):
   ```tsx
   case 'area':
     return (
       <ResponsiveContainer width="100%" height={300}>
         <AreaChart data={chart.data} ...>
           <Area type="monotone" dataKey={yField} stroke={colors[0]} fill={colors[0]} fillOpacity={0.2} />
         </AreaChart>
       </ResponsiveContainer>
     );
   ```
3. The backend can now return `"chart_type": "area"` and the frontend renders it automatically.

### Add a New Page

1. Create `app/your-page/page.tsx`.
2. Add the route to the `links` array in [components/Sidebar.tsx](components/Sidebar.tsx):
   ```typescript
   { href: '/your-page', label: 'Your Page', icon: SomeIcon }
   ```

### Add a New Filter

In [components/Filters.tsx](components/Filters.tsx), add a new `<select>` block inside the grid and add the key to the `FilterState` interface.
