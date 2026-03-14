"""
Distribution / ranking KPI templates.
"""

from __future__ import annotations

from typing import Any, Dict, List

DISTRIBUTION_TEMPLATES: List[Dict[str, Any]] = [
    {
        "name": "distribution",
        "description": "Count and percentage of each distinct value in a categorical column.",
        "formula_pattern": "COUNT(*) GROUP BY {col} ORDER BY COUNT(*) DESC",
        "suitable_column_types": ["VARCHAR", "INTEGER", "BOOLEAN"],
        "example": "orders by status (pending, completed, cancelled)",
    },
    {
        "name": "top_k",
        "description": "Top K entities by an aggregate metric.",
        "formula_pattern": "SELECT {group_col}, SUM({value_col}) AS total ORDER BY total DESC LIMIT {k}",
        "suitable_column_types": ["VARCHAR", "INTEGER", "DOUBLE"],
        "example": "top 10 products by revenue",
    },
    {
        "name": "percentile",
        "description": "Percentile distribution (p50, p90, p99) of a numeric column.",
        "formula_pattern": "PERCENTILE_CONT({p}) WITHIN GROUP (ORDER BY {col})",
        "suitable_column_types": ["INTEGER", "DOUBLE", "FLOAT", "DECIMAL"],
        "example": "p50 / p90 / p99 of response times",
    },
    {
        "name": "histogram_bucket",
        "description": "Distribution of a numeric column across equal-width buckets.",
        "formula_pattern": "WIDTH_BUCKET({col}, {min}, {max}, {n_buckets}) AS bucket, COUNT(*) GROUP BY bucket",
        "suitable_column_types": ["INTEGER", "DOUBLE", "FLOAT"],
        "example": "age distribution in 10-year buckets",
    },
    {
        "name": "unique_count",
        "description": "Number of distinct values in a column.",
        "formula_pattern": "COUNT(DISTINCT {col})",
        "suitable_column_types": ["ANY"],
        "example": "number of unique customers",
    },
    {
        "name": "concentration_ratio",
        "description": "Percentage of total value held by the top N entities (market concentration).",
        "formula_pattern": "SUM(top_n.total) * 100.0 / SUM(all.total)",
        "suitable_column_types": ["INTEGER", "DOUBLE"],
        "example": "top 5 customers as % of total revenue",
    },
]


# Convenience: all templates in a single registry
ALL_TEMPLATES: List[Dict[str, Any]] = DISTRIBUTION_TEMPLATES
