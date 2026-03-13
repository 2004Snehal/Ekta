"""
Frammer AI Analytics — FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import dashboard, intelligence, ingest, nlq
from api.routes import state as state_route
from api.routes import dashboard_data

app = FastAPI(
    title="Frammer AI Analytics API",
    version="0.1.0",
    description="Analytics platform for Frammer media operations teams.",
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


@app.get("/health")
def health():
    return {"status": "ok"}
