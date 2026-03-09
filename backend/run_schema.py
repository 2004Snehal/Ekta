import psycopg2
from config import DATABASE_URL

def run_schema():
    """Execute the schema.sql file to create all tables."""
    try:
        print("Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("Reading schema.sql...")
        with open('schema.sql', 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        print("Executing schema...")
        cursor.execute(schema_sql)
        conn.commit()
        
        print("✓ Schema executed successfully!")
        
        # List created tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        print(f"\n✓ Created {len(tables)} tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # List materialized views
        cursor.execute("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public'
            ORDER BY matviewname;
        """)
        views = cursor.fetchall()
        
        if views:
            print(f"\n✓ Created {len(views)} materialized views:")
            for view in views:
                print(f"  - {view[0]}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print("✗ Schema execution failed!")
        print(f"Error: {e}")
        
        # Try to provide more helpful error info
        if "already exists" in str(e):
            print("\nNote: Some objects may already exist. Drop them first if you want to recreate.")

if __name__ == "__main__":
    run_schema()
