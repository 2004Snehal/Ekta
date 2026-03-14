import psycopg2
import socket
from urllib.parse import urlparse, parse_qs
from backend_config import DATABASE_URL

def test_connection():
    """Test PostgreSQL connection with basic network diagnostics."""
    try:
        parsed = urlparse(DATABASE_URL)
        host = parsed.hostname
        port = parsed.port or 5432
        sslmode = parse_qs(parsed.query).get("sslmode", ["not-set"])[0]

        print("Attempting to connect to database...")
        print(f"Host: {host}")
        print(f"Port: {port}")
        print(f"Database: {parsed.path.lstrip('/') or 'unknown'}")
        print(f"SSL mode: {sslmode}")

        # Fast socket probe so network-level failures are obvious.
        try:
            with socket.create_connection((host, port), timeout=5):
                print("✓ TCP socket reachable")
        except OSError as sock_err:
            print("✗ TCP socket not reachable")
            print(f"Socket error: {sock_err}")
            return

        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
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
        print("Hint: if host is private (10.x/172.16-31.x/192.168.x), ensure VPN or network route is active.")

if __name__ == "__main__":
    test_connection()
