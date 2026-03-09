import psycopg2
from config import DATABASE_URL

def test_connection():
    """Test PostgreSQL connection to Neon."""
    try:
        print("Attempting to connect to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Test query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        
        print("✓ Connection successful!")
        print(f"PostgreSQL version: {version[0]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print("✗ Connection failed!")
        print(f"Error: {e}")

if __name__ == "__main__":
    test_connection()
