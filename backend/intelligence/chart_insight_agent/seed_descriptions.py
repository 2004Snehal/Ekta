"""
Seed script — pre-populate chart_description_cache for all known static charts.

Run once at setup:
    cd backend
    python -m intelligence.chart_insight_agent.seed_descriptions

Skips any chart whose description is already in the DB.
"""

from __future__ import annotations
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from api.deps import get_conn
from intelligence.chart_insight_agent.agent import generate_chart_description
from intelligence.chart_insight_agent.schemas import ChartDescriptionRequest
from intelligence.chart_insight_agent.description_service import make_cache_key, get_description, save_description

# All known static charts across the dashboard.
# Extend this list when new fixed charts are added.
KNOWN_CHARTS: list[dict] = [
    # ── Main dashboard ────────────────────────────────────────
    {"chart_title": "Videos by Channel",        "chart_type": "bar",  "x_label": "Channel", "y_label": "Count"},
    {"chart_title": "Daily Upload Trend",        "chart_type": "line", "x_label": "Date",    "y_label": "Videos"},
    {"chart_title": "Language Distribution",     "chart_type": "pie",  "x_label": None,      "y_label": None},
    {"chart_title": "Content by Type",           "chart_type": "bar",  "x_label": "Type",    "y_label": "Count"},

    # ── KPI detail modal ──────────────────────────────────────
    {"chart_title": "By Channel",               "chart_type": "bar",  "x_label": "Channel", "y_label": "Uploaded"},
    {"chart_title": "By User",                  "chart_type": "bar",  "x_label": "User",    "y_label": "Processed"},
    {"chart_title": "By Content Type",          "chart_type": "bar",  "x_label": "Type",    "y_label": "Count"},
    {"chart_title": "Published vs Unpublished", "chart_type": "pie",  "x_label": None,      "y_label": None},

    # ── Usage page ────────────────────────────────────────────
    {"chart_title": "Video Count Over Time",    "chart_type": "line", "x_label": "Period",  "y_label": "Count"},
    {"chart_title": "Cumulative Duration (hrs)","chart_type": "line", "x_label": "Period",  "y_label": "Hours"},

    # ── Funnel page ───────────────────────────────────────────
    {"chart_title": "Input Type Mix",           "chart_type": "pie",  "x_label": None,      "y_label": None},
    {"chart_title": "Publish Rate by channel",  "chart_type": "bar",  "x_label": "Group",   "y_label": "Publish Rate"},
    {"chart_title": "Publish Rate by user",     "chart_type": "bar",  "x_label": "Group",   "y_label": "Publish Rate"},
    {"chart_title": "Publish Rate by input type","chart_type": "bar", "x_label": "Group",   "y_label": "Publish Rate"},
    {"chart_title": "Publish Rate by language", "chart_type": "bar",  "x_label": "Group",   "y_label": "Publish Rate"},
]


def seed() -> None:
    print(f"Seeding descriptions for {len(KNOWN_CHARTS)} known charts...\n")

    with get_conn() as conn:
        for chart in KNOWN_CHARTS:
            key = make_cache_key(
                chart["chart_title"], chart["chart_type"],
                chart.get("x_label"), chart.get("y_label"),
            )
            existing = get_description(key, conn)
            if existing:
                print(f"  [SKIP] '{chart['chart_title']}' — already in DB")
                continue

            req = ChartDescriptionRequest(**chart)
            try:
                result = generate_chart_description(req)
                save_description(
                    key, chart["chart_title"], chart["chart_type"],
                    chart.get("x_label"), chart.get("y_label"),
                    result.description, conn,
                )
                print(f"  [OK]   '{chart['chart_title']}' — {result.description[:60]}...")
                time.sleep(6)  # stay under 10 req/min free-tier limit
            except Exception as e:
                print(f"  [ERR]  '{chart['chart_title']}' — {e}")


if __name__ == "__main__":
    seed()
