"""
Dashboard state routes.

POST /dashboard/state          → UPSERT state for a user, returns {state_id, …}
GET  /dashboard/state/{id}     → load immutable snapshot by UUID (for ?state= links)
GET  /dashboard/state          → load the current live state for a user_id
DELETE /dashboard/state/{id}   → remove a saved snapshot
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
    """
    Matches DashboardStatePayload the frontend serialises.

    If `stateId` is provided the backend will UPDATE that specific row
    (if it exists and belongs to the same userId), which makes auto-saves
    idempotent — only one live row per user instead of unbounded inserts.

    Omit `stateId` (or set it to None) when creating a fresh shareable
    snapshot so it always gets its own new UUID.
    """
    stateId: Optional[str] = None       # round-tripped from a previous save
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

    - If `stateId` is provided AND that row exists for this user → UPDATE it.
      This is the normal auto-save path: one live row per user, updated in place.
    - Otherwise → INSERT a new row and return its state_id.
      Use this path for shareable snapshots (don't pass stateId).
    """
    filters_json = json.dumps(body.filters)

    with get_conn() as conn:
        cur = conn.cursor()

        # Try to UPDATE an existing row when stateId is supplied
        if body.stateId:
            cur.execute(
                """
                UPDATE internal.dashboard_state
                SET
                    version          = %s,
                    filters_json     = %s,
                    filters_expanded = %s,
                    loaded_range     = %s,
                    selected_kpi_id  = %s,
                    updated_at       = NOW()
                WHERE id = %s
                  AND (user_id = %s OR user_id IS NULL)
                RETURNING id
                """,
                (
                    body.version,
                    filters_json,
                    body.filtersExpanded,
                    body.loadedRange,
                    body.selectedKpiId,
                    body.stateId,
                    body.userId,
                ),
            )
            updated = cur.fetchone()
            if updated:
                conn.commit()
                cur.close()
                return {
                    "state_id":       str(updated[0]),
                    "action":         "updated",
                    "share_url_param": f"?state={updated[0]}",
                }

        # INSERT — either no stateId was given, or the UPDATE found nothing
        new_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO internal.dashboard_state
                (id, user_id, version, filters_json, filters_expanded, loaded_range, selected_kpi_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                new_id,
                body.userId,
                body.version,
                filters_json,
                body.filtersExpanded,
                body.loadedRange,
                body.selectedKpiId,
            ),
        )
        conn.commit()
        cur.close()

    return {
        "state_id":        new_id,
        "action":          "created",
        "share_url_param": f"?state={new_id}",
    }


@router.get("/dashboard/state/{state_id}")
def load_state_by_id(state_id: str):
    """Load an immutable snapshot by UUID (used for ?state= shared links)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, version, filters_json, filters_expanded,
                   loaded_range, selected_kpi_id, created_at, updated_at
            FROM internal.dashboard_state
            WHERE id = %s
            """,
            (state_id,),
        )
        row = cur.fetchone()
        cur.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"State '{state_id}' not found.")
    return _row_to_state(row)


@router.get("/dashboard/state")
def load_state_by_user(user_id: str = Query(..., description="User identifier")):
    """
    Load the most-recently updated live state for a given user_id.
    Called on initial page load to restore the last session.
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, user_id, version, filters_json, filters_expanded,
                   loaded_range, selected_kpi_id, created_at, updated_at
            FROM internal.dashboard_state
            WHERE user_id = %s
            ORDER BY COALESCE(updated_at, created_at) DESC
            LIMIT 1
            """,
            (user_id,),
        )
        row = cur.fetchone()
        cur.close()

    if not row:
        raise HTTPException(status_code=404, detail=f"No saved state for user '{user_id}'.")
    return _row_to_state(row)


@router.delete("/dashboard/state/{state_id}")
def delete_state(state_id: str, user_id: str = Query(...)):
    """Delete a saved state snapshot (only the owner can delete it)."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM internal.dashboard_state WHERE id = %s AND user_id = %s RETURNING id",
            (state_id, user_id),
        )
        deleted = cur.fetchone()
        conn.commit()
        cur.close()

    if not deleted:
        raise HTTPException(status_code=404, detail="State not found or not owned by this user.")
    return {"deleted": state_id}
