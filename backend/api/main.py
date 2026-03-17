"""
Frammer AI Analytics — FastAPI application entry point.
"""

import logging
import sys
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Logging ───────────────────────────────────────────────────────────────────
# Configure before importing routes so every module's logger inherits this.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)

from api.routes import analytics
from api.routes import dashboard, intelligence, ingest, nlq, recommendations
from api.routes import state as state_route
from api.routes import dashboard_data
from api.routes import nlq_session
from api.routes import kpi_lab
from api.routes import data_manager
from api.routes import profiles

logger = logging.getLogger(__name__)


# ── APScheduler: nightly narrator pipeline ────────────────────────────────────

_scheduler = BackgroundScheduler()


def _schedule_narrator():
    """
    Scheduled job: runs the Insight Narrator pipeline for client_id=1 nightly.
    Extend with a loop over all active clients when multi-tenant.
    """
    from intelligence.insight_narrator.pipeline import run_pipeline
    logger.info("scheduler: running nightly narrator pipeline")
    try:
        run_pipeline(client_id=1)
    except Exception:
        logger.exception("scheduler: narrator pipeline failed")


def run_migrations() -> None:
    """
    Idempotent startup migrations — create tables that may not exist yet.
    All statements use IF NOT EXISTS so re-running is safe.
    """
    from api.deps import get_conn

    ddl_statements = [
        # Dashboard state — one live row per user, updated in place on auto-save.
        # Shareable snapshots are extra rows identified by their UUID.
        """
        CREATE TABLE IF NOT EXISTS dashboard_state (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id          TEXT,
            version          INTEGER NOT NULL DEFAULT 1,
            filters_json     JSONB   NOT NULL DEFAULT '{}',
            filters_expanded BOOLEAN NOT NULL DEFAULT TRUE,
            loaded_range     TEXT,
            selected_kpi_id  TEXT,
            created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at       TIMESTAMPTZ
        )
        """,
        # Index so "most recent state for user_id" queries are fast
        """
        CREATE INDEX IF NOT EXISTS idx_dashboard_state_user_id
            ON dashboard_state (user_id)
        """,
        # NLQ sessions table (if not yet created by another migration)
        """
        CREATE TABLE IF NOT EXISTS nlq_session (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     TEXT,
            title       TEXT,
            messages    JSONB NOT NULL DEFAULT '[]',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ
        )
        """,
    ]

    try:
        with get_conn() as conn:
            cur = conn.cursor()
            for stmt in ddl_statements:
                cur.execute(stmt)
            conn.commit()
            cur.close()
        logger.info("run_migrations: all tables ready")
    except Exception:
        logger.exception("run_migrations: failed — some tables may be missing")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure required tables exist before serving requests
    run_migrations()

    # Train Vanna with live schema (skipped if ChromaDB already populated)
    try:
        from intelligence.nlq.vanna_service import train_vanna_with_schema
        from api.deps import get_conn
        with get_conn() as conn:
            train_vanna_with_schema(conn)
        logger.info("Vanna NLQ knowledge base ready.")
    except Exception:
        logger.exception("Vanna training failed — NLQ will still attempt queries but RAG quality may be reduced.")

    # Start nightly job at 02:00 server time (after materialized view refresh)
    _scheduler.add_job(
        _schedule_narrator,
        CronTrigger(hour=2, minute=0),
        id="narrator_nightly",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("APScheduler started — narrator job scheduled at 02:00 nightly")
    yield
    _scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Frammer AI Analytics API",
    version="0.1.0",
    description="Analytics platform for Frammer media operations teams.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_data.router, tags=["Dashboard"])   # GET /dashboard
app.include_router(state_route.router,    tags=["Dashboard"])   # GET/POST /dashboard/state
app.include_router(dashboard.router,      tags=["Dashboard"])   # legacy KPI / filter routes
app.include_router(intelligence.router,   tags=["Intelligence"])
app.include_router(ingest.router,         tags=["Ingest"])
app.include_router(nlq.router,             tags=["NLQ"])
app.include_router(nlq_session.router,     tags=["NLQ"])
app.include_router(kpi_lab.router,         tags=["KPI Lab"])       # Auto-KPI Discovery Engine
app.include_router(data_manager.router,    tags=["Data Manager"])  # CSV append + row deletion
app.include_router(recommendations.router, tags=["Recommendations"])
app.include_router(profiles.router,         tags=["Profiles"])
app.include_router(analytics.router,        tags=["Analytics"])


@app.get("/health")
def health():
    return {"status": "ok"}
