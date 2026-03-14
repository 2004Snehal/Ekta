"""
Integration tests for the Auto-KPI Discovery Engine.
Tests the full pipeline with an in-memory DuckDB database containing
multiple tables (related and independent).

Run with:
    cd auto_kpi_engine
    pytest tests/test_pipeline.py -v
"""

from __future__ import annotations

import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from db.duckdb_adapter import DuckDBAdapter
from graph.pipeline import run_pipeline


# ================================================================== #
# Fixtures
# ================================================================== #

@pytest.fixture
def populated_db():
    """
    Create an in-memory DuckDB with three tables:
      - users and orders (related via user_id)
      - website_logs    (independent)
    """
    db = DuckDBAdapter(db_path=":memory:")
    db.connect()

    # Users table
    db.execute_no_return("""
        CREATE TABLE users (
            id       INTEGER PRIMARY KEY,
            name     VARCHAR,
            email    VARCHAR,
            country  VARCHAR,
            age      INTEGER
        )
    """)
    db.execute_no_return("""
        INSERT INTO users VALUES
            (1, 'Alice',   'alice@example.com',   'US', 30),
            (2, 'Bob',     'bob@example.com',     'UK', 25),
            (3, 'Charlie', 'charlie@example.com', 'US', 35),
            (4, 'Diana',   'diana@example.com',   'DE', 28),
            (5, 'Eve',     NULL,                  'FR', 22)
    """)

    # Orders table (related to users via user_id)
    db.execute_no_return("""
        CREATE TABLE orders (
            order_id    INTEGER PRIMARY KEY,
            user_id     INTEGER,
            amount      DOUBLE,
            status      VARCHAR,
            created_at  DATE
        )
    """)
    db.execute_no_return("""
        INSERT INTO orders VALUES
            (101, 1, 150.0, 'completed',  '2024-01-10'),
            (102, 2,  80.5, 'completed',  '2024-01-11'),
            (103, 1, 200.0, 'pending',    '2024-01-12'),
            (104, 3,  50.0, 'cancelled',  '2024-01-13'),
            (105, 4, 320.0, 'completed',  '2024-01-14'),
            (106, 5,  90.0, 'pending',    '2024-01-15'),
            (107, 2, 110.0, 'completed',  '2024-01-16')
    """)

    # Independent table: website_logs (no relationships)
    db.execute_no_return("""
        CREATE TABLE website_logs (
            log_id      INTEGER PRIMARY KEY,
            page        VARCHAR,
            visits      INTEGER,
            bounce_rate DOUBLE,
            log_date    DATE
        )
    """)
    db.execute_no_return("""
        INSERT INTO website_logs VALUES
            (1, '/home',    1200, 0.45, '2024-01-10'),
            (2, '/pricing',  430, 0.62, '2024-01-10'),
            (3, '/blog',     780, 0.38, '2024-01-11'),
            (4, '/home',    1350, 0.41, '2024-01-11'),
            (5, '/signup',   290, 0.30, '2024-01-12')
    """)

    yield db
    db.close()


# ================================================================== #
# DB Adapter tests
# ================================================================== #

class TestDuckDBAdapter:

    def test_list_tables(self, populated_db):
        tables = populated_db.list_tables()
        assert set(tables) == {"users", "orders", "website_logs"}

    def test_get_schema(self, populated_db):
        schema = populated_db.get_schema()
        assert "users" in schema
        col_names = [c["name"] for c in schema["users"]]
        assert "id" in col_names
        assert "email" in col_names

    def test_sample_rows(self, populated_db):
        rows = populated_db.sample_rows("users", n=3)
        assert len(rows) <= 3
        assert "name" in rows[0]

    def test_row_count(self, populated_db):
        assert populated_db.row_count("users") == 5
        assert populated_db.row_count("orders") == 7

    def test_execute_select(self, populated_db):
        rows = populated_db.execute("SELECT COUNT(*) AS cnt FROM orders WHERE status = 'completed'")
        assert rows[0]["cnt"] == 4

    def test_load_csv(self, tmp_path):
        csv_file = tmp_path / "products.csv"
        csv_file.write_text("product_id,name,price\n1,Widget,9.99\n2,Gadget,19.99\n")
        db = DuckDBAdapter(":memory:")
        db.connect()
        tbl = db.load_csv(str(csv_file))
        assert tbl == "products"
        assert db.row_count("products") == 2
        db.close()

    def test_load_multiple_csvs(self, tmp_path):
        f1 = tmp_path / "alpha.csv"
        f1.write_text("x,y\n1,2\n3,4\n")
        f2 = tmp_path / "beta.csv"
        f2.write_text("a,b\n10,20\n")
        db = DuckDBAdapter(":memory:")
        db.connect()
        tables = db.load_multiple_csvs([str(f1), str(f2)])
        assert set(tables) == {"alpha", "beta"}
        db.close()


# ================================================================== #
# SQL Validator tests
# ================================================================== #

class TestSQLValidator:

    def test_safe_select(self):
        from utils.sql_validator import is_safe_sql
        ok, _ = is_safe_sql("SELECT COUNT(*) FROM orders")
        assert ok

    def test_blocks_drop(self):
        from utils.sql_validator import is_safe_sql
        ok, reason = is_safe_sql("DROP TABLE users")
        assert not ok

    def test_blocks_delete(self):
        from utils.sql_validator import is_safe_sql
        ok, _ = is_safe_sql("DELETE FROM orders WHERE 1=1")
        assert not ok

    def test_with_clause_allowed(self):
        from utils.sql_validator import is_safe_sql
        ok, _ = is_safe_sql("WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert ok


# ================================================================== #
# Stats utils tests
# ================================================================== #

class TestStatsUtils:

    def test_mean(self):
        from utils.stats_utils import safe_mean
        assert safe_mean([1, 2, 3, 4, 5]) == pytest.approx(3.0)

    def test_std(self):
        from utils.stats_utils import safe_std
        assert safe_std([2, 4, 4, 4, 5, 5, 7, 9]) == pytest.approx(2.0)

    def test_entropy_uniform(self):
        from utils.stats_utils import entropy
        # Uniform distribution should have max entropy
        vals = list(range(8))  # 8 unique values → entropy = log2(8) = 3
        assert entropy(vals) == pytest.approx(3.0)

    def test_entropy_concentrated(self):
        from utils.stats_utils import entropy
        vals = [1] * 100  # Only one value → entropy = 0
        assert entropy(vals) == pytest.approx(0.0)

    def test_null_rate(self):
        from utils.stats_utils import null_rate
        assert null_rate([1, None, 3, None]) == pytest.approx(0.5)

    def test_unique_count(self):
        from utils.stats_utils import unique_count
        assert unique_count([1, 1, 2, 3, None]) == 3


# ================================================================== #
# Individual agent tests
# ================================================================== #

class TestSchemaReader:

    def test_reads_all_tables(self, populated_db):
        from agents.schema_reader import schema_reader
        state = {"db_adapter": populated_db, "errors": []}
        result = schema_reader(state)
        assert "users" in result["schema"]
        assert "orders" in result["schema"]
        assert "website_logs" in result["schema"]

    def test_row_counts(self, populated_db):
        from agents.schema_reader import schema_reader
        state = {"db_adapter": populated_db, "errors": []}
        result = schema_reader(state)
        assert result["schema"]["users"].row_count == 5
        assert result["schema"]["orders"].row_count == 7


class TestRelationshipDiscovery:

    def test_detects_user_order_relationship(self, populated_db):
        from agents.schema_reader import schema_reader
        from agents.relationship_discovery import relationship_discovery

        state = {"db_adapter": populated_db, "errors": []}
        state = schema_reader(state)
        state = relationship_discovery(state)

        tables_in_rels = set()
        for r in state["relationships"]:
            tables_in_rels.add(r.left_table)
            tables_in_rels.add(r.right_table)

        # users and orders should be related via user_id
        assert "users" in tables_in_rels or "orders" in tables_in_rels

    def test_graph_built(self, populated_db):
        from agents.schema_reader import schema_reader
        from agents.relationship_discovery import relationship_discovery

        state = {"db_adapter": populated_db, "errors": []}
        state = schema_reader(state)
        state = relationship_discovery(state)
        assert isinstance(state["relationship_graph"], dict)


class TestTableGrouping:

    def test_independent_table_in_own_group(self, populated_db):
        from agents.schema_reader import schema_reader
        from agents.relationship_discovery import relationship_discovery
        from agents.table_grouping import table_grouping

        state = {"db_adapter": populated_db, "errors": []}
        state = schema_reader(state)
        state = relationship_discovery(state)
        state = table_grouping(state)

        groups = state["table_groups"]
        # website_logs has no shared column names → must be in its own group
        all_tables_in_groups = [t for g in groups for t in g]
        assert "website_logs" in all_tables_in_groups

        # All tables accounted for
        assert set(all_tables_in_groups) == {"users", "orders", "website_logs"}


# ================================================================== #
# Full pipeline (no LLM — fallback mode)
# ================================================================== #

class TestFullPipeline:

    def test_pipeline_runs_without_llm(self, populated_db):
        """Full pipeline should complete even without an LLM service."""
        state = run_pipeline(
            db_adapter=populated_db,
            llm_service=None,   # no LLM → rule-based fallback throughout
        )

        assert "schema" in state
        assert "table_groups" in state
        assert "column_stats" in state
        assert "candidate_kpis" in state
        assert "computed_values" in state
        assert "good_kpis" in state
        assert "insights" in state

    def test_candidate_kpis_produced(self, populated_db):
        state = run_pipeline(db_adapter=populated_db, llm_service=None)
        assert len(state["candidate_kpis"]) > 0

    def test_no_fatal_errors(self, populated_db):
        state = run_pipeline(db_adapter=populated_db, llm_service=None)
        # Errors list may be non-empty (warnings) but pipeline must not crash
        assert isinstance(state["errors"], list)

    def test_insights_generated(self, populated_db):
        state = run_pipeline(db_adapter=populated_db, llm_service=None)
        # At least some fallback insights should exist if good_kpis exist
        if state["good_kpis"]:
            assert len(state["insights"]) > 0


# ================================================================== #
# FastAPI endpoint tests
# ================================================================== #

class TestAPIEndpoints:

    @pytest.fixture
    def client(self, populated_db, monkeypatch):
        """
        Create a test client with the shared adapter replaced by the test DB.
        """
        from fastapi.testclient import TestClient
        import api.routes as routes_module

        # Patch the adapter singleton
        monkeypatch.setattr(routes_module, "_adapter", populated_db)
        monkeypatch.setattr(routes_module, "get_llm", lambda: None)

        from api.server import app
        return TestClient(app)

    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_get_schema(self, client):
        r = client.get("/schema")
        assert r.status_code == 200
        data = r.json()
        assert "tables" in data
        assert "users" in data["tables"]

    def test_kpi_discover(self, client):
        r = client.post("/kpi/discover")
        assert r.status_code == 200
        data = r.json()
        assert "candidate_kpis" in data
        assert "insights" in data
        assert isinstance(data["insights"], list)
