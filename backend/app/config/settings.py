"""
Application settings loaded from environment variables via Pydantic BaseSettings.
All configuration is centralised here — no magic strings anywhere else.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── PostgreSQL ────────────────────────────────────────────────────────────
    db_host: str = Field("localhost", env="DB_HOST")
    db_port: int = Field(5432, env="DB_PORT")
    db_name: str = Field("ekta_db", env="DB_NAME")
    db_user: str = Field("postgres", env="DB_USER")
    db_password: str = Field("", env="DB_PASSWORD")

    # ── LLM Provider (openai | gemini) ────────────────────────────────────────
    llm_provider: Literal["openai", "gemini"] = Field("openai", env="LLM_PROVIDER")
    openai_api_key: str = Field("", env="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o", env="OPENAI_MODEL")
    gemini_api_key: str = Field("", env="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-1.5-pro", env="GEMINI_MODEL")

    # ── Vanna ─────────────────────────────────────────────────────────────────
    # Vanna uses its own ChromaDB internally; set the persist directory
    vanna_chroma_path: str = Field("./vanna_chroma_db", env="VANNA_CHROMA_PATH")
    vanna_model_name: str = Field("ekta_nlq", env="VANNA_MODEL_NAME")

    # ── LIDA ──────────────────────────────────────────────────────────────────
    lida_max_goals: int = Field(3, env="LIDA_MAX_GOALS")

    # ── API ───────────────────────────────────────────────────────────────────
    api_host: str = Field("0.0.0.0", env="API_HOST")
    api_port: int = Field(8000, env="API_PORT")
    debug: bool = Field(False, env="DEBUG")

    # ── Self-healing ──────────────────────────────────────────────────────────
    max_sql_retries: int = Field(2, env="MAX_SQL_RETRIES")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def db_dsn(self) -> str:
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — import and call this everywhere."""
    return Settings()
