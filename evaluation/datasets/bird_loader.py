"""
BIRD mini_dev dataset loader.

Downloads birdsql/bird_mini_dev from HuggingFace datasets and prepares
(question, gold_sql, db_id) tuples. SQLite .db files must be downloaded
separately from the BIRD benchmark site into BIRD_DB_ROOT.

Usage:
    records = load_bird_mini_dev()
    for r in records:
        print(r["question"], r["gold_sql"], r["db_id"])
"""
from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Iterator


def load_bird_mini_dev(limit: int = None) -> list[dict]:
    """
    Load BIRD mini_dev from HuggingFace.
    Returns list of dicts with keys:
      question, gold_sql, db_id, difficulty

    Requires: pip install datasets
    """
    try:
        from datasets import load_dataset
    except ImportError:
        raise ImportError("Run: pip install datasets")

    # split confirmed from dataset inspection: mini_dev_sqlite (500 rows)
    ds = load_dataset("birdsql/bird_mini_dev", split="mini_dev_sqlite")

    records = []
    for row in ds:
        records.append({
            "question":   row["question"],
            "gold_sql":   row["SQL"],
            "db_id":      row["db_id"],
            "difficulty": row.get("difficulty", "unknown"),
            "evidence":   row.get("evidence", ""),
        })
        if limit and len(records) >= limit:
            break
    return records


def get_sqlite_conn(db_id: str, bird_db_root: Path) -> sqlite3.Connection:
    """
    Return a SQLite connection for a given BIRD db_id.
    Looks for <bird_db_root>/<db_id>/sqlite/<db_id>.db
    (matches the folder structure inside the Google Drive zip)
    """
    # Support both layouts: db_id/sqlite/db_id.db and db_id/db_id.sqlite
    candidates = [
        bird_db_root / db_id / "sqlite" / f"{db_id}.db",
        bird_db_root / db_id / f"{db_id}.sqlite",
        bird_db_root / db_id / f"{db_id}.db",
    ]
    db_path = next((p for p in candidates if p.exists()), None)
    if db_path is None:
        raise FileNotFoundError(
            f"SQLite DB not found for {db_id} in {bird_db_root / db_id}"
        )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def get_schema_str(conn: sqlite3.Connection) -> str:
    """
    Extract schema DDL from a SQLite connection.
    Returns a compact string listing all tables and their columns.
    """
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]

    lines = []
    for table in tables:
        cur = conn.execute(f"PRAGMA table_info({table})")
        cols = cur.fetchall()
        col_defs = ", ".join(f"{c[1]} {c[2]}" for c in cols)
        lines.append(f"TABLE {table} ({col_defs})")

    return "\n".join(lines)


def load_own_queries(path: Path) -> list[str]:
    """
    Load own queries from own_queries.txt.

    Handles the mixed format in the file:
      - Strips leading numbering:  "31. Show me..." → "Show me..."
      - Strips inline labels:      "(Off-Topic)", "(Multi-turn 1A)", "(** ... **)"
      - Skips section header lines (ALL-CAPS title lines)
      - Skips comment lines (start with #)
      - Skips empty lines
    """
    import re

    if not path.exists():
        raise FileNotFoundError(f"Own queries file not found: {path}")

    # All-caps section headers like "FRAMMER AI ADVANCED NLQ TEST QUESTIONS (...)"
    _HEADER_RE = re.compile(r'^[A-Z][A-Z\s\(\)\-]+$')
    # Leading "31. " numbering
    _NUM_RE    = re.compile(r'^\d+\.\s+')
    # Trailing inline labels like "(Off-Topic)", "(Multi-turn 1A)", "(** for security testing **)"
    _LABEL_RE  = re.compile(r'\s*\(\*?\*?[^)]*\*?\*?\)\s*$')

    queries = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()

        if not line or line.startswith("#"):
            continue
        if _HEADER_RE.match(line):
            continue

        line = _NUM_RE.sub("", line)
        line = _LABEL_RE.sub("", line).strip()

        if line:
            queries.append(line)

    return queries
