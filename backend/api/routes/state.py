"""
Dashboard state routes.

POST /dashboard/state          → save current state, returns {state_id, ...}
GET  /dashboard/state/{id}    → load state by shareable UUID  (for ?state= links)
GET  /dashboard/state         → load most-recent state for a user_id
"""

import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_conn

router = APIRouter()


# ── Pydantic models ───────────────────────────────────────────────────────────

class SaveStateRequest(BaseModel):
    """Matches the DashboardStatePayload the frontend serialises."""
    userId: Optional[str] = None
    version: int = 1
    filters: dict[str, Any] = {}
    filtersExpanded: bool = True
    loadedRange: Optional[str] = None
    selectedKpiId: Optional[str] = None
    updatedAt: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _row_to_state(row: tuple) -> dict:
    id_, user_id, version, filters_json, filters_expanded, loaded_range, selected_kpi_id, created_at, updated_at = row
    filters = filters_json if isinstance(filters_json, dict) else json.loads(filters_json or "{}")
    return {
        "state_id":        str(id_),
        "userId":          user_id,
        "version":         version,
        "filters":         filters,
        "filtersExpanded": filters_expanded,
        "loadedRange":     loaded_range,
        "selectedKpiId":   selected_kpi_id,
        "updatedAt":       (updated_at or created_at).isoformat() if (updated_at or created_at) else None,
    }


# ── routes ────────────────────────────────────────────────────────────────────

@router.post("/dashboard/state")
def save_state(body: SaveStateRequest):
    """
    Persist a dashboard state snapshot.
    Returns the generated state_id so the frontend can build a shareable URL.
    """
    state_id = str(uuid.uuid4())
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO dashboard_state
                (id, user_id, version, filters_json, filters_expanded, loaded_range, selected_kpi_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                state_id,
                body.userId,
                body.version,
                json.dumps(body.filters),
                body.filtersExpanded,
                body.loadedRange,
                body.selectedKpiId,
            ),
        )
        conn.commit()
    return {"state_id": state_id, "share_url_param": f"?state={state_id}"}


@router.get("/dashboard/state/{state_id}")
def load_state_by_id(state_id: str):
    """
    Load a saved dashboard state by its UUID.
    Used when opening a shared link like /dashboard?state=<uuid>.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, version, filters_json, filters_expanded,
                   loaded_range, selected_kpi_id, created_at, updated_at
            FROM dashboard_state
            WHERE id = %s
            """,
            (state_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"State '{state_id}' not found.")
    return _row_to_state(row)


@router.get("/dashboard/state")
def load_state_by_user(user_id: str = Query(..., description="User identifier")):
    """
    Load the most-recently saved state for a given user_id.
    Used on initial page load to restore the last session.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, version, filters_json, filters_expanded,
                   loaded_range, selected_kpi_id, created_at, updated_at
            FROM dashboard_state
            WHERE user_id = %s
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"No saved state for user '{user_id}'.")
    return _row_to_state(row)
