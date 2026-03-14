"""
Growth / trend KPI templates.
"""

from __future__ import annotations

from typing import Any, Dict, List

GROWTH_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "growth_rate",
        "description": "Percentage change in a metric between two consecutive periods.",
        "formula_pattern": "(current_period_value - prior_period_value) * 100.0 / NULLIF(prior_period_value, 0)",
        "suitable_column_types": ["DATE", "TIMESTAMP", "INTEGER", "DOUBLE"],
        "example": "month-over-month revenue growth",
    },
    {
        "name": "cumulative_sum",
        "description": "Running total of a numeric column ordered by a date column.",
        "formula_pattern": "SUM({value_col}) OVER (ORDER BY {date_col})",
        "suitable_column_types": ["INTEGER", "DOUBLE", "FLOAT"],
        "example": "cumulative sales over time",
    },
    {
        "name": "period_over_period",
        "description": "Compare aggregate values across periods (e.g., this month vs last month).",
        "formula_pattern": "SUM(CASE WHEN {period_condition} THEN {value_col} ELSE 0 END)",
        "suitable_column_types": ["DATE", "TIMESTAMP"],
        "example": "this quarter vs last quarter revenue",
    },
    {
        "name": "moving_average",
        "description": "Rolling average of a metric over N periods.",
        "formula_pattern": "AVG({value_col}) OVER (ORDER BY {date_col} ROWS BETWEEN {n} PRECEDING AND CURRENT ROW)",
        "suitable_column_types": ["INTEGER", "DOUBLE", "FLOAT"],
        "example": "7-day moving average of daily active users",
    },
]
