"""
Check actual database schema - list all tables and columns
"""
import psycopg2

def main():
    params = {
        "host": "localhost",
        "port": 5433,
        "user": "postgres",
        "password": "Ais@9894",
        "database": "postgres"
    }
    
    try:
        conn = psycopg2.connect(**params)
        cursor = conn.cursor()
        
        print("=" * 80)
        print("DATABASE SCHEMA ANALYSIS")
        print("=" * 80)
        
        # List all tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = [row[0] for row in cursor.fetchall()]
        
        print(f"\nTotal tables: {len(tables)}")
        print("\nTables and their columns:")
        print("-" * 80)
        
        for table in tables:
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM \"{table}\";")
            count = cursor.fetchone()[0]
            
            # Get columns
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_name = '{table}' 
                ORDER BY ordinal_position;
            """)
            columns = cursor.fetchall()
            
            print(f"\n{table} ({count} rows)")
            for col_name, data_type, nullable in columns:
                print(f"  - {col_name}: {data_type} {'(nullable)' if nullable == 'YES' else ''}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 80)
        print("Schema analysis complete!")
        print("=" * 80)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
