"""
Cleanup tables in weorder database that were created by mistake
"""
import psycopg2

DATABASE_URL = 'postgresql://postgres:julaherb789!@localhost:5432/weorder'

def cleanup():
    print("Connecting to weorder database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    
    # Get all tables created by our app
    our_tables = [
        'abx_budget_logs', 'ad_performance_history', 'budget_optimization_logs',
        'daily_budgets', 'abx_adgroups', 'ads', 'content_score_history',
        'budget_allocations', 'ad_groups', 'product_groups', 'contents',
        'budget_plans', 'campaigns', 'ad_accounts', 'targeting_templates',
        'notifications', 'sync_status', 'task_logs', 'sku_signals',
        'offline_sales_weekly', 'saversure_scans_daily', 'online_sales_daily',
        'products', 'users'
    ]
    
    # Check which tables exist
    cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    existing_tables = [row[0] for row in cur.fetchall()]
    
    tables_to_drop = [t for t in our_tables if t in existing_tables]
    
    if not tables_to_drop:
        print("No tables to drop in weorder database.")
        return
    
    print(f"Found {len(tables_to_drop)} tables to drop: {tables_to_drop}")
    
    # Drop tables in order (respecting foreign keys)
    for table in tables_to_drop:
        try:
            cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
            print(f"  ✅ Dropped: {table}")
        except Exception as e:
            print(f"  ❌ Error dropping {table}: {e}")
    
    conn.close()
    print("\n✅ Cleanup completed!")

if __name__ == "__main__":
    cleanup()

