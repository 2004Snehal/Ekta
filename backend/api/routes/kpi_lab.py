"""
KPI Lab routes — integrated from the Auto-KPI Discovery Engine.

Supports two data sources:
  - source=csv      : CSV files uploaded into an in-memory DuckDB instance
  - source=postgres : The existing Frammer PostgreSQL (Supabase) database

The PostgreSQL adapter reuses the shared connection pool from api.deps
to avoid exhausting Supabase's MaxClientsInSessionMode connection limit.

Postgres schema is cached in memory after the first successful fetch so
subsequent requests don't need an extra round-trip to the database.
"""

from __future__ import annotations

import json
import logging
import os
import sys

# ------------------------------------------------------------------ #
# Ensure auto_kpi_engine root is on sys.path so its internal imports
# (from config.settings, from db.duckdb_adapter, …) resolve correctly.
# ------------------------------------------------------------------ #
_HERE = os.path.dirname(os.path.abspath(__file__))
_KPI_ENGINE_ROOT = os.path.normpath(
    os.path.join(_HERE, "..", "..", "intelligence", "kpi_agent", "auto_kpi_engine")
)
if _KPI_ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _KPI_ENGINE_ROOT)

import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, Form

from pydantic import BaseModel

from config.settings import settings
from db.duckdb_adapter import DuckDBAdapter
from db.postgres_adapter import PostgreSQLAdapter
from db.adapter_base import DBAdapter
from llm.llm_service import LLMService
from graph.pipeline import run_pipeline, run_partial_pipeline

# Reuse the shared Postgres connection pool from the main backend
from api.deps import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/kpi-lab", tags=["KPI Lab"])

# ================================================================== #
# Adapter singletons
# ================================================================== #

_duckdb_adapter: Optional[DuckDBAdapter] = None

# Postgres schema cache — populated on first successful fetch.
# Keyed by schema name; value is the enriched tables dict.
_pg_schema_cache: Optional[Dict[str, Any]] = None


def get_csv_adapter() -> DuckDBAdapter:
    global _duckdb_adapter
    if _duckdb_adapter is None:
        _duckdb_adapter = DuckDBAdapter(db_path=settings.duckdb_path)
        _duckdb_adapter.connect()
    return _duckdb_adapter


def get_pg_adapter() -> PostgreSQLAdapter:
    """
    Returns a PostgreSQLAdapter scoped to the 'data' schema, borrowing
    connections from the shared backend pool (api.deps.get_conn).
    """
    return PostgreSQLAdapter(conn_factory=get_conn, schema="data")


def get_adapter(source: str) -> DBAdapter:
    return get_pg_adapter() if source == "postgres" else get_csv_adapter()


def get_llm() -> Optional[LLMService]:
    try:
        return LLMService.default()
    except Exception as exc:
        logger.warning("LLM service unavailable: %s", exc)
        return None


# ================================================================== #
# Request / Response models
# ================================================================== #

class UploadResponse(BaseModel):
    tables_loaded: List[str]
    message: str


class KPIDiscoverResponse(BaseModel):
    run_id: str
    source: str
    table_groups: List[List[str]]
    candidate_kpis: List[Dict[str, Any]]
    computed_values: Dict[str, Any]
    good_kpis: List[Dict[str, Any]]
    insights: List[Dict[str, Any]]
    errors: List[str]


class KPIGenerateResponse(BaseModel):
    run_id: str
    source: str
    table_groups: List[List[str]]
    candidate_kpis: List[Dict[str, Any]]
    errors: List[str]


class KPIComputeResponse(BaseModel):
    run_id: str
    source: str
    computed_values: Dict[str, Any]
    errors: List[str]


class KPIEvaluateResponse(BaseModel):
    run_id: str
    source: str
    good_kpis: List[Dict[str, Any]]
    errors: List[str]


# ================================================================== #
# Helpers
# ================================================================== #

def _save_upload(upload_file: UploadFile) -> Path:
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload_file.filename or "upload.csv").suffix or ".csv"
    dest = settings.upload_dir / f"{uuid.uuid4().hex}{suffix}"
    with dest.open("wb") as f:
        shutil.copyfileobj(upload_file.file, f)
    return dest


def _serialise(obj: Any) -> Any:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_serialise(i) for i in obj]
    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    return obj


def _enrich_schema(adapter: DBAdapter) -> Dict[str, Any]:
    """Fetch full schema + row counts + sample rows from any adapter."""
    raw = adapter.get_schema()
    enriched: Dict[str, Any] = {}
    for table, cols in raw.items():
        try:
            rc = adapter.row_count(table)
            sample = adapter.sample_rows(table, n=3)
        except Exception:
            rc = 0
            sample = []
        enriched[table] = {"columns": cols, "row_count": rc, "sample_rows": sample}
    return enriched


# ================================================================== #
# Registry save helpers (used after discovery)
# ================================================================== #

def _save_discovered_kpi(kpi: dict) -> str:
    """
    Upsert a discovered KPI into internal.kpi_registry.
    Returns the UUID of the saved row (new or updated).
    """
    kpi_id = str(uuid.uuid4())
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO internal.kpi_registry
              (id, name, description, formula, sql_expression, columns_used, tables_used,
               category, current_value, usefulness_score, source, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'discovery',NOW())
            ON CONFLICT (name) DO UPDATE SET
              description      = EXCLUDED.description,
              formula          = EXCLUDED.formula,
              sql_expression   = EXCLUDED.sql_expression,
              columns_used     = EXCLUDED.columns_used,
              tables_used      = EXCLUDED.tables_used,
              category         = EXCLUDED.category,
              current_value    = EXCLUDED.current_value,
              usefulness_score = EXCLUDED.usefulness_score,
              source           = EXCLUDED.source,
              expand_page      = NULL,
              updated_at       = NOW()
            RETURNING id
            """,
            (
                kpi_id,
                kpi.get("name"),
                kpi.get("description", ""),
                kpi.get("formula", ""),
                kpi.get("sql", ""),
                json.dumps(kpi.get("columns", [])),
                json.dumps(kpi.get("tables", [])),
                kpi.get("template", ""),
                json.dumps(kpi.get("value")),
                kpi.get("usefulness_score"),
            ),
        )
        returned_id = str(cur.fetchone()[0])
        conn.commit()
        cur.close()
    return returned_id


def _trigger_expand_page(registry_id: str, kpi_dict: dict) -> None:
    """
    Background task: generate the expand page via LLM and persist it.
    Uses a lazy import from kpi_registry to avoid circular module imports.
    """
    try:
        from api.routes.kpi_registry import _update_expand_page_bg  # noqa: PLC0415
        _update_expand_page_bg(registry_id, kpi_dict)
    except Exception as exc:
        logger.warning("expand page generation failed for kpi %s: %s", registry_id, exc)


# ================================================================== #
# Endpoints
# ================================================================== #

# ── Source info ───────────────────────────────────────────────────

@router.get("/sources")
async def list_sources():
    """
    Return available data sources with table counts.
    Uses the cached Postgres schema (no extra DB connection if already cached).
    """
    global _pg_schema_cache

    # CSV tables (in-memory DuckDB — zero DB connections)
    csv_tables: List[str] = []
    try:
        csv_tables = get_csv_adapter().list_tables()
    except Exception:
        pass

    # Postgres: use cache if available, otherwise count from DB
    pg_tables: List[str] = []
    if _pg_schema_cache is not None:
        pg_tables = list(_pg_schema_cache.keys())
    else:
        try:
            pg_tables = get_pg_adapter().list_tables()
        except Exception:
            pass

    return {
        "sources": [
            {
                "id": "postgres",
                "label": "Frammer Database",
                "description": "Live Supabase PostgreSQL — all production tables",
                "table_count": len(pg_tables),
                "tables": pg_tables,
            },
            {
                "id": "csv",
                "label": "Uploaded CSV",
                "description": "CSV files uploaded in this session (in-memory DuckDB)",
                "table_count": len(csv_tables),
                "tables": csv_tables,
            },
        ]
    }


# ── Schema ────────────────────────────────────────────────────────

@router.get("/schema")
async def get_schema(
    source: str = Query(default="postgres", pattern="^(csv|postgres)$"),
    refresh: bool = Query(default=False),
):
    """
    Return schema for the chosen source.

    Postgres schema is cached after the first fetch.
    Pass ?refresh=true to force a re-fetch from the database.
    """
    global _pg_schema_cache

    if source == "postgres":
        if _pg_schema_cache is not None and not refresh:
            return {"source": "postgres", "cached": True, "tables": _pg_schema_cache}
        # Fetch from DB and cache
        try:
            enriched = _enrich_schema(get_pg_adapter())
            _pg_schema_cache = enriched
            return {"source": "postgres", "cached": False, "tables": enriched}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # CSV — always live (in-memory DuckDB, no network cost)
    try:
        enriched = _enrich_schema(get_csv_adapter())
        return {"source": "csv", "cached": False, "tables": enriched}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── CSV upload ────────────────────────────────────────────────────

@router.post("/data/upload", response_model=UploadResponse)
async def upload_data(
    files: List[UploadFile] = File(...),
    table_names: Optional[str] = Form(None),
):
    """Upload one or more CSV files into the in-memory DuckDB instance."""
    adapter = get_csv_adapter()
    custom_names: List[Optional[str]] = []
    if table_names:
        custom_names = [n.strip() or None for n in table_names.split(",")]

    loaded: List[str] = []
    errors: List[str] = []

    for idx, upload in enumerate(files):
        if not upload.filename:
            errors.append(f"File at index {idx} has no filename — skipped")
            continue
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in (".csv", ".tsv", ".txt"):
            errors.append(f"'{upload.filename}' is not a CSV file — skipped")
            continue
        custom_name: Optional[str] = custom_names[idx] if idx < len(custom_names) else None
        try:
            path = _save_upload(upload)
            tbl = adapter.load_csv(str(path), table_name=custom_name)
            loaded.append(tbl)
        except Exception as exc:
            errors.append(f"Failed to load '{upload.filename}': {exc}")

    if not loaded and errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    return UploadResponse(
        tables_loaded=loaded,
        message=f"Loaded {len(loaded)} table(s). Errors: {len(errors)}",
    )


# ── Pipeline endpoints ────────────────────────────────────────────

@router.post("/kpi/generate", response_model=KPIGenerateResponse)
async def generate_kpis(source: str = Query(default="postgres", pattern="^(csv|postgres)$")):
    """Run pipeline up to KPI generation (schema → relationships → grouping → stats → candidates)."""
    adapter = get_adapter(source)
    llm = get_llm()
    try:
        state = run_partial_pipeline(db_adapter=adapter, llm_service=llm, stop_after="kpi_generator")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return KPIGenerateResponse(
        run_id=state.get("run_id", ""),
        source=source,
        table_groups=state.get("table_groups", []),
        candidate_kpis=_serialise(state.get("candidate_kpis", [])),
        errors=state.get("errors", []),
    )


@router.post("/kpi/compute", response_model=KPIComputeResponse)
async def compute_kpis(source: str = Query(default="postgres", pattern="^(csv|postgres)$")):
    """Run pipeline up to SQL execution."""
    adapter = get_adapter(source)
    llm = get_llm()
    try:
        state = run_partial_pipeline(db_adapter=adapter, llm_service=llm, stop_after="query_executor")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return KPIComputeResponse(
        run_id=state.get("run_id", ""),
        source=source,
        computed_values=_serialise(state.get("computed_values", {})),
        errors=state.get("errors", []),
    )


@router.post("/kpi/evaluate", response_model=KPIEvaluateResponse)
async def evaluate_kpis(source: str = Query(default="postgres", pattern="^(csv|postgres)$")):
    """Run pipeline up to evaluation (filters by variance, correlation, usefulness)."""
    adapter = get_adapter(source)
    llm = get_llm()
    try:
        state = run_partial_pipeline(db_adapter=adapter, llm_service=llm, stop_after="kpi_evaluator")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return KPIEvaluateResponse(
        run_id=state.get("run_id", ""),
        source=source,
        good_kpis=_serialise(state.get("good_kpis", [])),
        errors=state.get("errors", []),
    )


@router.post("/kpi/discover", response_model=KPIDiscoverResponse)
async def discover_kpis(
    background_tasks: BackgroundTasks,
    source: str = Query(default="postgres", pattern="^(csv|postgres)$"),
):
    """
    Run the full 9-agent Auto-KPI pipeline end-to-end.
    Good KPIs (non-null computed values) are saved to internal.kpi_registry
    and their expand pages are generated asynchronously.
    Returns registry_id alongside each good KPI.
    """
    adapter = get_adapter(source)
    llm = get_llm()
    dialect = "postgres" if source == "postgres" else "duckdb"
    try:
        state = run_pipeline(db_adapter=adapter, llm_service=llm, dialect=dialect)
    except Exception as exc:
        logger.exception("Pipeline error")
        raise HTTPException(status_code=500, detail=str(exc))

    # Build candidate lookup: candidate.id → candidate dict
    candidate_map: dict = {}
    for c in state.get("candidate_kpis", []):
        c_dict = c.model_dump() if hasattr(c, "model_dump") else dict(c)
        candidate_map[c_dict.get("id")] = c_dict

    # Enrich good KPIs, skip null values, save to registry
    enriched_good_kpis = []
    for ev in state.get("good_kpis", []):
        ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else dict(ev)

        # Skip KPIs with no computed value
        if ev_dict.get("value") is None:
            logger.debug("Skipping KPI '%s': null value", ev_dict.get("name"))
            continue

        kpi_id = ev_dict.get("kpi_id")
        candidate = candidate_map.get(kpi_id, {})

        merged = {
            "name": ev_dict.get("name", ""),
            "description": candidate.get("description", ""),
            "formula": candidate.get("formula", ""),
            "sql": candidate.get("sql") or "",
            "columns": candidate.get("columns", []),
            "tables": candidate.get("tables", []),
            "template": candidate.get("template", ""),
            "value": ev_dict.get("value"),
            "usefulness_score": ev_dict.get("usefulness_score", 0),
        }

        try:
            registry_id = _save_discovered_kpi(merged)
            background_tasks.add_task(
                _trigger_expand_page,
                registry_id,
                {
                    "name": merged["name"],
                    "description": merged["description"],
                    "formula": merged["formula"],
                    "sql_expression": merged["sql"],
                    "columns_used": merged["columns"],
                    "tables_used": merged["tables"],
                    "category": merged["template"],
                    "current_value": merged["value"],
                },
            )
        except Exception as exc:
            logger.warning("Failed to save KPI '%s' to registry: %s", merged["name"], exc)
            registry_id = None

        enriched_good_kpis.append({
            **ev_dict,
            "description": merged["description"],
            "formula": merged["formula"],
            "sql": merged["sql"],
            "category": merged["template"],
            "registry_id": registry_id,
        })

    return KPIDiscoverResponse(
        run_id=state.get("run_id", ""),
        source=source,
        table_groups=state.get("table_groups", []),
        candidate_kpis=_serialise(state.get("candidate_kpis", [])),
        computed_values=_serialise(state.get("computed_values", {})),
        good_kpis=enriched_good_kpis,
        insights=_serialise(state.get("insights", [])),
        errors=state.get("errors", []),
    )


# ── Reset (CSV only) ──────────────────────────────────────────────

@router.delete("/data/reset")
async def reset_data():
    """Drop all uploaded CSV tables and reset the DuckDB session."""
    global _duckdb_adapter
    if _duckdb_adapter is not None:
        try:
            for t in _duckdb_adapter.list_tables():
                _duckdb_adapter.execute_no_return(f'DROP TABLE IF EXISTS "{t}"')
        except Exception as exc:
            logger.warning("Reset error: %s", exc)
        _duckdb_adapter = None
    return {"message": "All CSV tables dropped. Ready for new uploads."}


@router.delete("/schema/cache")
async def clear_schema_cache():
    """Force the Postgres schema cache to be cleared (next /schema call re-fetches)."""
    global _pg_schema_cache
    _pg_schema_cache = None
    return {"message": "Schema cache cleared."}
