"""
All LLM prompt templates used by agents.
Centralised here to make prompt engineering easy.
"""

from __future__ import annotations

from typing import Any, Dict, List


# ================================================================== #
# Helper
# ================================================================== #

def _fmt(template: str, **kwargs: Any) -> str:
    return template.format(**kwargs)


# ================================================================== #
# Schema / relationship prompts
# ================================================================== #

RELATIONSHIP_DISCOVERY_PROMPT = """
You are a database analyst. Given the following tables and their columns, identify all likely JOIN relationships.

Tables and columns:
{schema_summary}

Rules:
- A relationship exists when a column in one table likely references a column in another table.
- Common patterns: user_id ↔ id in users table, order_id ↔ id in orders table, etc.
- Only suggest relationships that are strongly implied by column names and data types.

Respond ONLY with a JSON array. Each element must have:
{{
  "left_table": "<table>",
  "right_table": "<table>",
  "left_column": "<col>",
  "right_column": "<col>",
  "confidence": <0.0-1.0>
}}

If there are no relationships, respond with: []
""".strip()


# ================================================================== #
# KPI generation prompt
# ================================================================== #

KPI_GENERATION_PROMPT = """
You are a senior business analyst and data scientist.

You have been given the following database group:

Tables: {tables}

Schema:
{schema_detail}

Column statistics:
{stats_summary}

Available KPI templates:
{templates}

Your task:
Generate {n_kpis} meaningful, non-redundant KPI candidates for this table group.

Rules:
- Use ONLY columns and tables listed above.
- Each KPI must map to one of the available templates.
- Only suggest JOIN-based KPIs if the tables are known to be related.
- Prefer KPIs that are actionable and have business meaning.
- Do NOT invent columns or tables that do not exist.

Respond ONLY with a valid JSON array. Each element:
{{
  "name": "<KPI name>",
  "description": "<1-sentence business description>",
  "template": "<template_name>",
  "formula": "<human-readable formula, e.g. COUNT(orders) / COUNT(users)>",
  "tables": ["<table1>", ...],
  "columns": ["<col1>", ...],
  "requires_join": <true|false>,
  "confidence": <0.0-1.0>
}}
""".strip()


# ================================================================== #
# SQL Builder prompt
# ================================================================== #

SQL_BUILDER_PROMPT = """
You are a SQL expert.

Convert the following KPI formula into a single executable SQL query.

KPI name: {kpi_name}
Formula: {formula}
Tables involved: {tables}
Columns involved: {columns}
Requires join: {requires_join}

Known relationships (use ONLY these for JOINs):
{relationships}

Database dialect: {dialect}

Rules:
- Write a single SELECT statement.
- Never invent JOIN conditions not listed in the relationships above.
- If requires_join is false, query only the primary table.
- The query must return a single numeric value or a small result set.
- Use standard SQL unless the dialect requires otherwise.
- Do NOT include markdown, explanations or code fences — output raw SQL only.
""".strip()


# ================================================================== #
# KPI usefulness scoring prompt
# ================================================================== #

KPI_USEFULNESS_SCORING_PROMPT = """
You are a KPI quality evaluator for a business analytics system.

Rate the following KPI on a scale of 1–10 across three dimensions:
1. Business relevance  (is this metric something a business person would care about?)
2. Actionability       (can someone act on this metric to improve business outcomes?)
3. Uniqueness          (is this metric distinct from standard obvious metrics?)

KPI name: {kpi_name}
Description: {description}
Formula: {formula}
Computed value: {value}

Respond ONLY with valid JSON:
{{
  "business_relevance": <1-10>,
  "actionability": <1-10>,
  "uniqueness": <1-10>,
  "overall": <1-10>,
  "reason": "<one sentence>"
}}
""".strip()


# ================================================================== #
# Insight generation prompt
# ================================================================== #

INSIGHT_GENERATION_PROMPT = """
You are a business intelligence analyst writing executive-level insights.

Convert the following KPI result into a clear, concise, actionable business insight (1-2 sentences).

KPI name: {kpi_name}
Formula: {formula}
Computed value: {value}
Context (other related KPIs):
{context}

Rules:
- Be specific about the number.
- Suggest a possible implication or action.
- Write in plain English for a non-technical audience.
- Do not repeat the KPI name verbatim; rephrase it naturally.

Respond with ONLY the insight text. No JSON, no bullet points.
""".strip()


# ================================================================== #
# Public helpers
# ================================================================== #

def render_relationship_prompt(schema_summary: str) -> str:
    return _fmt(RELATIONSHIP_DISCOVERY_PROMPT, schema_summary=schema_summary)


def render_kpi_generation_prompt(
    tables: List[str],
    schema_detail: str,
    stats_summary: str,
    templates: str,
    n_kpis: int = 5,
) -> str:
    return _fmt(
        KPI_GENERATION_PROMPT,
        tables=", ".join(tables),
        schema_detail=schema_detail,
        stats_summary=stats_summary,
        templates=templates,
        n_kpis=n_kpis,
    )


def render_sql_builder_prompt(
    kpi_name: str,
    formula: str,
    tables: List[str],
    columns: List[str],
    requires_join: bool,
    relationships: str,
    dialect: str = "duckdb",
) -> str:
    return _fmt(
        SQL_BUILDER_PROMPT,
        kpi_name=kpi_name,
        formula=formula,
        tables=", ".join(tables),
        columns=", ".join(columns),
        requires_join=str(requires_join),
        relationships=relationships,
        dialect=dialect,
    )


def render_usefulness_scoring_prompt(
    kpi_name: str,
    description: str,
    formula: str,
    value: Any,
) -> str:
    return _fmt(
        KPI_USEFULNESS_SCORING_PROMPT,
        kpi_name=kpi_name,
        description=description,
        formula=formula,
        value=str(value),
    )


def render_insight_prompt(
    kpi_name: str,
    formula: str,
    value: Any,
    context: str = "",
) -> str:
    return _fmt(
        INSIGHT_GENERATION_PROMPT,
        kpi_name=kpi_name,
        formula=formula,
        value=str(value),
        context=context or "None",
    )
