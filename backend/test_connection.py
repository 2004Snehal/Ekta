import psycopg2
from backend_config import DATABASE_URL


def test_connection():
    """Test Supabase PostgreSQL connection."""
    print("Testing Supabase connection...")
    print(f"URL: {DATABASE_URL[:40]}..." if DATABASE_URL else "ERROR: DATABASE_URL not set")

    try:
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
        cursor = conn.cursor()

        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✓ Connected! PostgreSQL version: {version[0]}")

        cursor.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('internal', 'data') ORDER BY schema_name;")
        schemas = [row[0] for row in cursor.fetchall()]
        print(f"✓ Schemas found: {schemas}")

        cursor.execute("SELECT COUNT(*) FROM data.shortened_filtered_data;")
        count = cursor.fetchone()[0]
        print(f"✓ data.shortened_filtered_data rows: {count:,}")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"✗ Connection failed: {e}")


if __name__ == "__main__":
    test_connection()
