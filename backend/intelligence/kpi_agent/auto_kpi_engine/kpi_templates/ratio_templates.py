"""
Ratio / rate KPI templates.
"""

from __future__ import annotations

from typing import Any, Dict, List

RATIO_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "conversion_rate",
        "description": "Percentage of rows meeting a success condition vs. total rows.",
        "formula_pattern": "COUNT(CASE WHEN {condition_col} = '{value}' THEN 1 END) * 100.0 / COUNT(*)",
        "suitable_column_types": ["VARCHAR", "INTEGER", "BOOLEAN"],
        "example": "completed orders / total orders",
    },
    {
        "name": "null_rate",
        "description": "Percentage of missing values in a column.",
        "formula_pattern": "SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*)",
        "suitable_column_types": ["ANY"],
        "example": "NULL emails / total users",
    },
    {
        "name": "efficiency_ratio",
        "description": "Ratio of output metric to input metric.",
        "formula_pattern": "SUM({output_col}) * 1.0 / NULLIF(SUM({input_col}), 0)",
        "suitable_column_types": ["INTEGER", "DOUBLE", "FLOAT", "DECIMAL"],
        "example": "revenue / cost",
    },
    {
        "name": "average_value",
        "description": "Average of a numeric column.",
        "formula_pattern": "AVG({col})",
        "suitable_column_types": ["INTEGER", "DOUBLE", "FLOAT", "DECIMAL"],
        "example": "average order value",
    },
    {
        "name": "fill_rate",
        "description": "Percentage of rows where a column is non-null.",
        "formula_pattern": "COUNT({col}) * 100.0 / COUNT(*)",
        "suitable_column_types": ["ANY"],
        "example": "rows with phone number / total users",
    },
]
