"""
Frammer AI Analytics — FastAPI application entry point.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import dashboard, intelligence, ingest, nlq

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

app.include_router(dashboard.router, tags=["Dashboard"])
app.include_router(intelligence.router, tags=["Intelligence"])
app.include_router(ingest.router, tags=["Ingest"])
app.include_router(nlq.router, tags=["NLQ"])


@app.get("/health")
def health():
    return {"status": "ok"}
