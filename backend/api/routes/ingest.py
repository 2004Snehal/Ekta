"""
Ingest route — placeholder.
Production ingestion shape TBD (depends on upstream Frammer system).
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/ingest")
def ingest():
    return JSONResponse(
        status_code=501,
        content={"detail": "Ingestion endpoint not yet implemented. Shape TBD based on upstream data source."},
    )
