"""
Workspace routes — team directory + saved dashboards.

Endpoints:
  GET  /workspace/team                     - team members grouped by profile
  GET  /workspace/dashboards               - all saved dashboards
  POST /workspace/dashboards               - save a new dashboard
  GET  /workspace/dashboards/{id}          - get single saved dashboard
  DELETE /workspace/dashboards/{id}        - delete (creator only, via ?user_id=)
"""

import json
import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.deps import get_conn

router = APIRouter()


# ── Pydantic models ────────────────────────────────────────────────────────────

class SaveDashboardRequest(BaseModel):
    name: str
    description: Optional[str] = None
    created_by: str
    created_by_name: Optional[str] = None
    visible_kpi_ids: List[str] = []
    graphs: List[Any] = []


# ── Team directory ─────────────────────────────────────────────────────────────

@router.get("/workspace/team")
def get_team():
    """Return all users grouped by profile."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, email, profile, role
                FROM internal.users
                ORDER BY profile, name
            """)
            rows = cur.fetchall()

    grouped: dict[str, list] = {}
    for user_id, name, email, profile, role in rows:
        member = {
            "id": user_id,
            "name": name or email or user_id,
            "profile": profile or "user",
            "role": role or "user",
        }
        grouped.setdefault(profile or "user", []).append(member)

    return {"grouped": grouped}


# ── Saved dashboards ───────────────────────────────────────────────────────────

@router.get("/workspace/dashboards")
def list_dashboards():
    """Return all saved dashboards ordered by newest first."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, created_by, created_by_name,
                       visible_kpi_ids, graphs, created_at
                FROM internal.saved_dashboards
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()

    dashboards = []
    for row in rows:
        id_, name, desc, created_by, created_by_name, kpi_ids, graphs, created_at = row
        dashboards.append({
            "id": str(id_),
            "name": name,
            "description": desc,
            "created_by": created_by,
            "created_by_name": created_by_name,
            "visible_kpi_ids": list(kpi_ids) if kpi_ids else [],
            "graphs": graphs if isinstance(graphs, list) else json.loads(graphs or "[]"),
            "created_at": created_at.isoformat() if created_at else None,
        })

    return {"dashboards": dashboards}


@router.post("/workspace/dashboards", status_code=201)
def save_dashboard(req: SaveDashboardRequest):
    """Save the current dashboard state."""
    new_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO internal.saved_dashboards
                    (id, name, description, created_by, created_by_name,
                     visible_kpi_ids, graphs)
                VALUES (%s, %s, %s, %s, %s, %s::TEXT[], %s::JSONB)
            """, (
                new_id,
                req.name.strip(),
                req.description.strip() if req.description else None,
                req.created_by,
                req.created_by_name,
                req.visible_kpi_ids,
                json.dumps(req.graphs),
            ))
        conn.commit()

    return {"id": new_id, "name": req.name.strip()}


@router.get("/workspace/dashboards/{dashboard_id}")
def get_dashboard(dashboard_id: str):
    """Return a single saved dashboard by ID."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, description, created_by, created_by_name,
                       visible_kpi_ids, graphs, created_at
                FROM internal.saved_dashboards
                WHERE id = %s
            """, (dashboard_id,))
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    id_, name, desc, created_by, created_by_name, kpi_ids, graphs, created_at = row
    return {
        "id": str(id_),
        "name": name,
        "description": desc,
        "created_by": created_by,
        "created_by_name": created_by_name,
        "visible_kpi_ids": list(kpi_ids) if kpi_ids else [],
        "graphs": graphs if isinstance(graphs, list) else json.loads(graphs or "[]"),
        "created_at": created_at.isoformat() if created_at else None,
    }


@router.delete("/workspace/dashboards/{dashboard_id}", status_code=204)
def delete_dashboard(dashboard_id: str, user_id: str = Query(...)):
    """Delete a saved dashboard. Only the creator can delete."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                DELETE FROM internal.saved_dashboards
                WHERE id = %s AND created_by = %s
            """, (dashboard_id, user_id))
            deleted = cur.rowcount
        conn.commit()

    if deleted == 0:
        raise HTTPException(status_code=404, detail="Dashboard not found or not owner")
