"""
Central configuration for Auto-KPI Discovery Engine.
All settings are loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ------------------------------------------------------------------ #
    # LLM
    # ------------------------------------------------------------------ #
    llm_provider: Literal["groq", "openai", "gemini"] = Field(
        default="groq", alias="LLM_PROVIDER"
    )

    # Groq
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama3-70b-8192", alias="GROQ_MODEL")

    # OpenAI
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    db_engine: Literal["duckdb", "clickhouse"] = Field(
        default="duckdb", alias="DB_ENGINE"
    )
    duckdb_path: str = Field(default=":memory:", alias="DUCKDB_PATH")

    # ClickHouse (future)
    clickhouse_host: str = Field(default="localhost", alias="CLICKHOUSE_HOST")
    clickhouse_port: int = Field(default=9000, alias="CLICKHOUSE_PORT")
    clickhouse_database: str = Field(default="default", alias="CLICKHOUSE_DATABASE")
    clickhouse_user: str = Field(default="default", alias="CLICKHOUSE_USER")
    clickhouse_password: str = Field(default="", alias="CLICKHOUSE_PASSWORD")

    # ------------------------------------------------------------------ #
    # File storage
    # ------------------------------------------------------------------ #
    upload_dir: Path = Field(
        default=Path(__file__).resolve().parent.parent / "data" / "uploads",
        alias="UPLOAD_DIR",
    )

    # ------------------------------------------------------------------ #
    # KPI evaluation thresholds
    # ------------------------------------------------------------------ #
    kpi_variance_threshold: float = Field(
        default=0.0, alias="KPI_VARIANCE_THRESHOLD"
    )
    kpi_correlation_threshold: float = Field(
        default=0.95, alias="KPI_CORRELATION_THRESHOLD"
    )
    kpi_usefulness_score_threshold: float = Field(
        default=6.0, alias="KPI_USEFULNESS_SCORE_THRESHOLD"
    )

    # ------------------------------------------------------------------ #
    # Column name overlap threshold for relationship discovery
    # ------------------------------------------------------------------ #
    relationship_column_overlap_min: int = Field(
        default=1, alias="RELATIONSHIP_COLUMN_OVERLAP_MIN"
    )

    model_config = {"populate_by_name": True, "env_file": ".env", "extra": "ignore"}


# Singleton
settings = Settings()

# Ensure upload directory exists
settings.upload_dir.mkdir(parents=True, exist_ok=True)
