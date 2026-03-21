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
from api.routes import auth as auth_route
from api.routes import admin as admin_route
from api.routes import kpi_registry as kpi_registry_route
from api.routes import workspace as workspace_route

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


@asynccontextmanager
async def lifespan(app: FastAPI):

    # Train RAG KB with live schema (skipped if ChromaDB already populated)
    try:
        from intelligence.nlq.rag_service import train_with_schema
        from api.deps import get_conn
        with get_conn() as conn:
            train_with_schema(conn)
        logger.info("NLQ RAG knowledge base ready.")
    except Exception:
        logger.exception("RAG training failed — NLQ will still attempt queries but RAG quality may be reduced.")

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

app.include_router(dashboard_data.router,  tags=["Dashboard"])    # GET /dashboard
app.include_router(state_route.router,     tags=["Dashboard"])    # GET/POST /dashboard/state
app.include_router(dashboard.router,       tags=["Dashboard"])    # legacy KPI / filter routes
app.include_router(intelligence.router,    tags=["Intelligence"])
app.include_router(ingest.router,          tags=["Ingest"])
app.include_router(nlq.router,             tags=["NLQ"])
app.include_router(nlq_session.router,     tags=["NLQ"])
app.include_router(kpi_lab.router,         tags=["KPI Lab"])       # Auto-KPI Discovery Engine
app.include_router(data_manager.router,    tags=["Data Manager"])  # CSV append + row deletion
app.include_router(recommendations.router, tags=["Recommendations"])
app.include_router(profiles.router,        tags=["Profiles"])
app.include_router(analytics.router,       tags=["Analytics"])
app.include_router(auth_route.router,          tags=["Auth"])          # signup / login
app.include_router(admin_route.router,         tags=["Admin"])         # admin console
app.include_router(kpi_registry_route.router,  tags=["KPI Lab"])       # KPI registry CRUD + manual/agent creation
app.include_router(workspace_route.router,     tags=["Workspace"])     # team directory + saved dashboards


@app.get("/health")
def health():
    return {"status": "ok"}
