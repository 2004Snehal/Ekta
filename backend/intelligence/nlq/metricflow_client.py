"""
MetricFlow client wrapper.

Calls `mf query --explain` via subprocess to compile a semantic query
into PostgreSQL. Falls back gracefully when mf CLI is unavailable.

Usage:
    sql = run_metricflow_query(
        metrics=["publish_rate"],
        group_by=["channel_name", "metric_time"],
        where=["{{ Dimension('created_videos__client_id') }} = '1'"],
        order_by=["-publish_rate"],
        limit=20,
    )
"""

import logging
import os
import re
import subprocess
import time
import yaml
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger("nlq.mf")

# Path to the dbt project root
SEMANTIC_DIR = Path(__file__).resolve().parent.parent.parent / "semantic"

_METRICS_FILE  = SEMANTIC_DIR / "models" / "semantic" / "_metrics.yml"
_SEMANTIC_FILE = SEMANTIC_DIR / "models" / "semantic" / "_semantic__created_videos.yml"


def run_metricflow_query(
    metrics: list[str],
    group_by: list[str],
    where: list[str] | None = None,
    order_by: list[str] | None = None,
    limit: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
) -> str:
    """
    Compile a MetricFlow semantic query to SQL via `mf query --explain`.

    Returns the compiled SQL string ready to execute against PostgreSQL.
    Raises RuntimeError if mf CLI fails or SQL cannot be extracted.
    """
    cmd = [
        "mf",
        "query",
        "--explain",
    ]

    if metrics:
        cmd += ["--metrics", ",".join(metrics)]
    if group_by:
        cmd += ["--group-by", ",".join(group_by)]
    if where:
        for clause in where:
            cmd += ["--where", clause]
    if order_by:
        cmd += ["--order", ",".join(order_by)]
    if limit:
        cmd += ["--limit", str(limit)]
    if start_time:
        cmd += ["--start-time", start_time]
    if end_time:
        cmd += ["--end-time", end_time]

    env = _dbt_env()
    _ensure_manifest(env)

    log.info(f"[MF]  subprocess     {' '.join(cmd[2:])}")
    t0 = time.perf_counter()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        cwd=str(SEMANTIC_DIR),
        env=env,
        timeout=60,
    )
    log.info(f"[MF]  subprocess     done  ({time.perf_counter()-t0:.2f}s)")

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    if result.returncode != 0:
        raise RuntimeError(
            f"MetricFlow compilation failed.\n"
            f"CMD: {' '.join(cmd)}\n"
            f"STDERR: {stderr.strip()}\n"
            f"STDOUT: {stdout.strip()}"
        )

    return _extract_sql(stdout)


def get_available_metrics() -> list[dict]:
    """
    Parse _metrics.yml and return metric definitions.

    Returns list of dicts: {name, type, description, label}
    Falls back to empty list if file is missing.
    """
    try:
        with open(_METRICS_FILE) as f:
            data = yaml.safe_load(f)
        return [
            {
                "name": m["name"],
                "type": m.get("type", ""),
                "description": m.get("description", "").strip(),
                "label": m.get("label", m["name"]),
            }
            for m in data.get("metrics", [])
        ]
    except FileNotFoundError:
        return []


def get_available_dimensions() -> list[dict]:
    """
    Parse the semantic model YAML and return dimension definitions.

    Returns list of dicts: {name, type, description}
    Falls back to empty list if file is missing.
    """
    try:
        with open(_SEMANTIC_FILE) as f:
            data = yaml.safe_load(f)
        dims = []
        for sm in data.get("semantic_models", []):
            for d in sm.get("dimensions", []):
                dims.append({
                    "name": d["name"],
                    "type": d.get("type", "categorical"),
                    "description": d.get("description", ""),
                })
        return dims
    except FileNotFoundError:
        return []


# ── internals ──────────────────────────────────────────────────────────────────

def _dbt_env() -> dict:
    """
    Parse DATABASE_URL into individual DBT_* env vars so profiles.yml
    can read them via env_var().

    DATABASE_URL format: postgresql://user:password@host:port/dbname
    """
    env = os.environ.copy()
    database_url = env.get("DATABASE_URL", "")

    if database_url:
        parsed = urlparse(database_url)
        env["DBT_HOST"]     = parsed.hostname or ""
        env["DBT_USER"]     = parsed.username or ""
        env["DBT_PASSWORD"] = parsed.password or ""
        env["DBT_PORT"]     = str(parsed.port or 5432)
        env["DBT_DBNAME"]   = (parsed.path or "").lstrip("/")

    # Tell dbt where to find profiles.yml (our semantic/ dir)
    env["DBT_PROFILES_DIR"] = str(SEMANTIC_DIR)

    # Fix Windows console encoding — mf outputs emoji that cp1252 can't handle
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"]       = "1"

    return env


def _ensure_manifest(env: dict) -> None:
    """
    Run `dbt parse` to generate target/semantic_manifest.json if it doesn't exist.
    MetricFlow needs this artifact before it can list metrics or compile queries.
    """
    manifest_path = SEMANTIC_DIR / "target" / "semantic_manifest.json"
    if manifest_path.exists():
        return

    log.info("[MF]  manifest missing — running dbt parse …")
    t0 = time.perf_counter()
    result = subprocess.run(
        ["dbt", "parse", "--profiles-dir", str(SEMANTIC_DIR)],
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace',
        cwd=str(SEMANTIC_DIR),
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"dbt parse failed — cannot initialize MetricFlow.\n{result.stderr.strip()}"
        )
    log.info(f"[MF]  dbt parse      done  ({time.perf_counter()-t0:.2f}s)")


def _extract_sql(mf_output: str) -> str:
    """
    Extract the SELECT statement from `mf query --explain` output.

    mf prints something like:
        🔹 Success 🔹
        📋 Generated SQL (remove --explain to see data):
        SELECT ...
        FROM ...
        LIMIT 500
    """
    # Strip ANSI escape codes
    clean = re.sub(r"\x1b\[[0-9;]*m", "", mf_output)

    match = re.search(r"(SELECT\b.*)", clean, re.IGNORECASE | re.DOTALL)
    if not match:
        raise RuntimeError(
            f"Could not extract SQL from MetricFlow output:\n{mf_output}"
        )
    return match.group(1).strip()
