"""
Dynamic schema context for the NLQ system prompt.
Introspects the live database so SQL generation always matches the real schema.
Schema is cached for 5 minutes to avoid redundant round-trips.
"""

import time
from typing import Optional

# ── Simple in-process cache ────────────────────────────────────────────────────
_cache: Optional[str] = None
_cache_ts: float = 0.0
_CACHE_TTL = 300  # seconds


def fetch_live_schema(conn) -> str:
    """
    Query the live DB and return a schema description string.
    Result is cached for _CACHE_TTL seconds.
    """
    global _cache, _cache_ts
    if _cache and (time.time() - _cache_ts) < _CACHE_TTL:
        return _cache

    cur = conn.cursor()

    # ── 1. All tables, views, and materialized views ───────────────────────────
    cur.execute("""
        SELECT table_name, 'TABLE' AS kind
        FROM information_schema.tables
        WHERE table_schema = 'data'
          AND table_type = 'BASE TABLE'
        UNION ALL
        SELECT table_name, 'VIEW'
        FROM information_schema.views
        WHERE table_schema = 'data'
        UNION ALL
        SELECT matviewname, 'MATERIALIZED VIEW'
        FROM pg_matviews
        WHERE schemaname = 'data'
        ORDER BY 1
    """)
    objects = cur.fetchall()  # [(name, kind), ...]

    if not objects:
        return "No tables found in the data schema."

    # ── 2. Columns for every object ────────────────────────────────────────────
    all_names = tuple(r[0] for r in objects)
    cur.execute("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'data'
          AND table_name = ANY(%s)
        ORDER BY table_name, ordinal_position
    """, (list(all_names),))
    col_rows = cur.fetchall()

    # Group columns by table
    from collections import defaultdict
    cols_by_table: dict = defaultdict(list)
    for tname, cname, dtype in col_rows:
        cols_by_table[tname].append((cname, dtype))

    # ── 3. Sample distinct values for low-cardinality text columns ─────────────
    # Only sample text/varchar columns; skip if table has no rows
    sample_values: dict = {}  # (table, col) → [val, ...]
    TEXT_TYPES = {"text", "character varying", "varchar", "char", "character"}
    MAX_SAMPLE_COLS = 5  # limit per table to keep startup fast

    for tname, kind in objects:
        sampled = 0
        for cname, dtype in cols_by_table.get(tname, []):
            if dtype.lower() not in TEXT_TYPES:
                continue
            if sampled >= MAX_SAMPLE_COLS:
                break
            try:
                cur.execute(
                    f'SELECT DISTINCT "{cname}" FROM data."{tname}" '
                    f'WHERE "{cname}" IS NOT NULL LIMIT 12'
                )
                vals = [str(r[0]) for r in cur.fetchall() if r[0] is not None]
                if 1 < len(vals) <= 12:          # skip unique-ish columns
                    sample_values[(tname, cname)] = vals
                    sampled += 1
            except Exception:
                conn.rollback()

    # ── 4. Build human-readable schema string ─────────────────────────────────
    lines = ["DATABASE: PostgreSQL — live schema (all tables are in the 'data' schema)\n"]

    kind_order = {"TABLE": 0, "MATERIALIZED VIEW": 1, "VIEW": 2}
    sorted_objects = sorted(objects, key=lambda r: (kind_order.get(r[1], 3), r[0]))

    for tname, kind in sorted_objects:
        lines.append(f"=== {kind}: data.{tname} ===")
        for cname, dtype in cols_by_table.get(tname, []):
            sample = sample_values.get((tname, cname))
            sample_str = f"  -- values: {', '.join(sample)}" if sample else ""
            lines.append(f"  {cname}  ({dtype}){sample_str}")
        lines.append("")

    schema_str = "\n".join(lines)
    _cache = schema_str
    _cache_ts = time.time()
    return schema_str


