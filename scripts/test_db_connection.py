"""
Test Database Connection - Read Only
Check connection and list existing tables/data
"""
import psycopg2

def main():
    print("\n" + "=" * 60)
    print("WeBoostX 2.0 - Database Connection Test (Read Only)")
    print("=" * 60)
    
    # Connection params
    params = {
        "host": "localhost",
        "port": 5433,
        "user": "postgres",
        "password": "Ais@9894",
        "database": "postgres"
    }
    
    try:
        # Connect
        print(f"\n[1] Connecting to {params['host']}:{params['port']}/{params['database']}...")
        conn = psycopg2.connect(**params)
        print("[OK] Connected successfully!")
        
        cursor = conn.cursor()
        
        # Get PostgreSQL version
        cursor.execute("SELECT version();")
        version = cursor.fetchone()[0]
        print(f"\n[2] PostgreSQL Version:")
        print(f"    {version[:60]}...")
        
        # List all tables in public schema
        print(f"\n[3] Tables in 'public' schema:")
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        if tables:
            for i, (table,) in enumerate(tables, 1):
                # Get row count
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                print(f"    {i:2}. {table:40} ({count:,} rows)")
        else:
            print("    (No tables found)")
        
        # Check for Facebook-related tables
        print(f"\n[4] Looking for Facebook-related data...")
        fb_keywords = ['facebook', 'fb_', 'page', 'post', 'ad_account', 'campaign', 'content']
        
        for (table,) in tables:
            table_lower = table.lower()
            if any(kw in table_lower for kw in fb_keywords):
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                if count > 0:
                    print(f"    [FB?] {table}: {count:,} rows")
                    
                    # Show sample columns
                    cursor.execute(f"""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = '{table}' 
                        LIMIT 10;
                    """)
                    cols = cursor.fetchall()
                    print(f"         Columns: {', '.join([c[0] for c in cols])}")
        
        # Show sample data from tables with 'content' or 'post'
        print(f"\n[5] Sample data preview:")
        for (table,) in tables:
            if 'content' in table.lower() or 'post' in table.lower():
                cursor.execute(f"SELECT COUNT(*) FROM {table};")
                count = cursor.fetchone()[0]
                if count > 0:
                    print(f"\n    Table: {table} ({count:,} rows)")
                    cursor.execute(f"SELECT * FROM {table} LIMIT 3;")
                    rows = cursor.fetchall()
                    col_names = [desc[0] for desc in cursor.description]
                    print(f"    Columns: {col_names[:8]}...")
                    for row in rows:
                        print(f"    Row: {str(row)[:100]}...")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("[SUCCESS] Connection test completed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Connection failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
