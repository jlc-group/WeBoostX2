"""
Analyze Facebook Database Schema
Get detailed column info for mapping to WeBoostX 2.0 models
"""
import psycopg2

def main():
    print("\n" + "=" * 70)
    print("WeBoostX 2.0 - Facebook Schema Analysis")
    print("=" * 70)
    
    params = {
        "host": "localhost",
        "port": 5433,
        "user": "postgres",
        "password": "Ais@9894",
        "database": "postgres"
    }
    
    # Key tables to analyze for mapping
    tables_to_analyze = [
        "facebook_pages",
        "facebook_posts",
        "facebook_posts_performance",
        "facebook_post_insights",
        "facebook_video_posts",
        "facebook_campaigns",
        "facebook_adsets",
        "facebook_ads",
        "facebook_ads_insights",
        "products",
    ]
    
    try:
        conn = psycopg2.connect(**params)
        cursor = conn.cursor()
        
        for table in tables_to_analyze:
            print(f"\n{'=' * 70}")
            print(f"TABLE: {table}")
            print("=" * 70)
            
            # Get columns
            cursor.execute(f"""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = '{table}'
                ORDER BY ordinal_position;
            """)
            columns = cursor.fetchall()
            
            print(f"\nColumns ({len(columns)}):")
            for col_name, data_type, nullable, default in columns:
                null_str = "NULL" if nullable == "YES" else "NOT NULL"
                default_str = f" DEFAULT {default}" if default else ""
                print(f"  - {col_name:35} {data_type:20} {null_str}{default_str}")
            
            # Get row count
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"\nTotal rows: {count:,}")
            
            # Get sample row
            if count > 0:
                cursor.execute(f"SELECT * FROM {table} LIMIT 1;")
                row = cursor.fetchone()
                col_names = [desc[0] for desc in cursor.description]
                
                print(f"\nSample row:")
                for i, (col, val) in enumerate(zip(col_names, row)):
                    val_str = str(val)[:80] if val else "NULL"
                    print(f"  {col}: {val_str}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 70)
        print("[DONE] Schema analysis completed!")
        print("=" * 70)
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
