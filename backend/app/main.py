"""
FastAPI application entry point.

Startup sequence:
  1. Connect to PostgreSQL (initialise connection pool)
  2. Load database schema
  3. Train Vanna with schema context
  4. Start FastAPI server

All heavy initialisation happens inside the lifespan context manager so
the server only begins accepting requests once everything is ready.
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config.settings import get_settings
from app.db.postgres import check_connection, close_pool, init_pool
from app.services.vanna_service import train_vanna_with_schema
from app.utils.logger import get_logger

logger = get_logger("nlq.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown side-effects."""
    settings = get_settings()

    # ── Startup ───────────────────────────────────────────────────────────────
    logger.info("=== NLQ Analytics Backend starting up ===")

    logger.info("[1/3] Initialising PostgreSQL connection pool…")
    init_pool()

    if not check_connection():
        raise RuntimeError(
            "Cannot connect to PostgreSQL. Check DB_* environment variables."
        )
    logger.info("[1/3] PostgreSQL connection OK.")

    logger.info("[2/3] Training Vanna with database schema…")
    train_vanna_with_schema()
    logger.info("[2/3] Vanna ready.")

    logger.info(
        "[3/3] FastAPI ready. LLM provider: %s | debug: %s",
        settings.llm_provider,
        settings.debug,
    )
    logger.info("=== Startup complete. Accepting requests. ===")

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("=== Shutting down NLQ Analytics Backend ===")
    close_pool()
    logger.info("PostgreSQL pool closed. Goodbye.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="NLQ Analytics Backend",
        description=(
            "Production-ready Natural Language Query engine. "
            "Converts plain-English questions into SQL, executes them on PostgreSQL, "
            "and returns structured results with optional LIDA visualisations."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ────────────────────────────────────────────────────────────────
    app.include_router(router, prefix="/nlq")

    return app


app = create_app()


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level="info",
    )
