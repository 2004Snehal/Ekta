"""
Migration script — applies clean schema to Supabase.
Wipe already completed. This runs phase 3 only (create schemas + tables).
"""

import os
import sys
from urllib.parse import urlparse, unquote, quote

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env")
    sys.exit(1)

import psycopg2

def safe_parse(url):
    at = url.rfind("@")
    scheme_end = url.index("://") + 3
    if at != -1:
        userinfo = url[scheme_end:at]
        if ":" in userinfo:
            user, raw_pass = userinfo.split(":", 1)
            url = url[:scheme_end] + user + ":" + quote(raw_pass, safe="") + url[at:]
    return urlparse(url)

p = safe_parse(DATABASE_URL)
print(f"Connecting to {p.hostname}:{p.port or 5432} ...")

conn = psycopg2.connect(
    host=p.hostname,
    port=p.port or 5432,
    dbname=p.path.lstrip("/"),
    user=p.username,
    password=unquote(p.password) if p.password else None,
    sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()
print("Connected.\n")

print("=== Applying clean schema ===")

sql = open(
    os.path.join(os.path.dirname(__file__), "schema_clean.sql"),
    encoding="utf-8"
).read()

def split_sql(text):
    """Split SQL on semicolons but not inside $$-quoted blocks or comments."""
    statements, current, in_dollar, i = [], [], False, 0
    while i < len(text):
        if text[i:i+2] == '$$':
            in_dollar = not in_dollar
            current.append('$$')
            i += 2
            continue
        if text[i] == ';' and not in_dollar:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(text[i])
        i += 1
    last = ''.join(current).strip()
    if last:
        statements.append(last)
    return statements

statements = split_sql(sql)
ok = 0
for stmt in statements:
    lines = [l for l in stmt.splitlines() if l.strip() and not l.strip().startswith("--")]
    if not lines:
        continue
    try:
        cur.execute(stmt)
        ok += 1
    except Exception as e:
        print(f"\n  ERROR:\n  {stmt[:120]}\n  -> {e}\n")
        conn.close()
        sys.exit(1)

print(f"  Applied {ok} statements successfully.\n")
conn.close()

print("=== Migration complete! ===")
print("  internal schema: dashboard_state, nlq_session, kpi_registry, query_log")
print("  data schema:     shortened_filtered_data")
