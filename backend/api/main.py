"""
Frammer AI Analytics — FastAPI application entry point.
"""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import dashboard, intelligence, ingest, nlq
from api.routes import state as state_route
from api.routes import dashboard_data
from api.routes import nlq_session
from api.routes import kpi_lab
from api.routes import data_manager

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
        CREATE TABLE IF NOT EXISTS public.dashboard_state (
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
        """
        CREATE INDEX IF NOT EXISTS idx_dashboard_state_user_id
            ON public.dashboard_state (user_id)
        """,
        # NLQ sessions table
        """
        CREATE TABLE IF NOT EXISTS public.nlq_session (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     TEXT,
            title       TEXT,
            messages    JSONB NOT NULL DEFAULT '[]',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ
        )
        """,
        # Insight cache — stale-while-revalidate store for narrator pipeline
        """
        CREATE TABLE IF NOT EXISTS public.insight_cache (
            cache_key    TEXT PRIMARY KEY,
            insights     JSONB NOT NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            data_as_of   DATE
        )
        """,
        # Insight deduplication history
        """
        CREATE TABLE IF NOT EXISTS public.pg_insight_history (
            id           BIGSERIAL PRIMARY KEY,
            client_id    BIGINT NOT NULL,
            entity_type  TEXT,
            entity_id    TEXT,
            insight_type TEXT,
            metric_name  TEXT,
            period       TEXT,
            first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            seen_count    INTEGER NOT NULL DEFAULT 1,
            UNIQUE (client_id, entity_type, entity_id, insight_type, metric_name, period)
        )
        """,
        # Insight log — per-card record for /insights/ query endpoint
        """
        CREATE TABLE IF NOT EXISTS public.insight_log (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            insight_id       BIGSERIAL,
            client_id        BIGINT,
            insight_type     TEXT,
            severity         TEXT,
            title            TEXT,
            body             TEXT,
            dimensions       JSONB,
            metric_value     DOUBLE PRECISION,
            baseline_value   DOUBLE PRECISION,
            delta_pct        DOUBLE PRECISION,
            category         TEXT,
            entity_type      TEXT,
            entity_id        TEXT,
            period           TEXT,
            current_value    DOUBLE PRECISION,
            reference_value  DOUBLE PRECISION,
            confidence       DOUBLE PRECISION,
            root_cause_hint  TEXT,
            user_feedback    INTEGER,
            is_read          BOOLEAN NOT NULL DEFAULT FALSE,
            generated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
app.include_router(nlq.router,            tags=["NLQ"])
app.include_router(nlq_session.router,    tags=["NLQ"])
app.include_router(kpi_lab.router,        tags=["KPI Lab"])     # Auto-KPI Discovery Engine
app.include_router(data_manager.router,   tags=["Data Manager"]) # CSV append + row deletion


@app.get("/health")
def health():
    return {"status": "ok"}
