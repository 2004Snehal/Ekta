"""
Reset password for demo@frammer.ai user.
Usage: python reset_password.py
"""

import psycopg2
from passlib.context import CryptContext
from dotenv import load_dotenv
import os

load_dotenv()

# Database connection
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env")
    exit(1)

# Manual extraction to handle special chars in password
# Format: postgresql://user:password@host:port/dbname
try:
    url = DATABASE_URL.replace("postgresql://", "")
    user_pass, host_db = url.split("@")
    user, password = user_pass.split(":", 1)
    host_port, database = host_db.split("/", 1)
    
    if ":" in host_port:
        host, port = host_port.split(":")
        port = int(port)
    else:
        host = host_port
        port = 5432
except Exception as e:
    print(f"ERROR parsing DATABASE_URL: {e}")
    exit(1)

conn = psycopg2.connect(
    host=host,
    port=port,
    database=database,
    user=user,
    password=password
)

# Create password hash
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
NEW_PASSWORD = "DemoPassword123"
password_hash = pwd_context.hash(NEW_PASSWORD)

# Update the user
cur = conn.cursor()

try:
    cur.execute(
        "UPDATE internal.users SET password_hash = %s WHERE email = %s",
        (password_hash, 'demo@frammer.ai')
    )
    conn.commit()
    
    if cur.rowcount > 0:
        print("SUCCESS: Password reset!")
        print(f"Email: demo@frammer.ai")
        print(f"Password: {NEW_PASSWORD}")
    else:
        print("ERROR: User demo@frammer.ai not found")
except Exception as e:
    print(f"ERROR: {e}")
    conn.rollback()
finally:
    cur.close()
    conn.close()
