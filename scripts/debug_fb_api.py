"""
Debug Facebook Dashboard API
Test each component step by step
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_step(name, func):
    """Run a test step and report result"""
    print(f"\n[TEST] {name}")
    print("-" * 50)
    try:
        result = func()
        print(f"[OK] Success: {result}")
        return True
    except Exception as e:
        print(f"[FAIL] Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("Facebook Dashboard API Debug")
    print("=" * 60)
    
    # Step 1: Test psycopg2 import
    def test_psycopg2():
        import psycopg2
        return f"psycopg2 version: {psycopg2.__version__}"
    
    if not test_step("Import psycopg2", test_psycopg2):
        return
    
    # Step 2: Test direct database connection
    def test_db_connection():
        import psycopg2
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            user="postgres",
            password="Ais@9894",
            database="postgres"
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return f"Connection OK, test query returned: {result}"
    
    if not test_step("Database Connection", test_db_connection):
        return
    
    # Step 3: Test table exists
    def test_tables():
        import psycopg2
        conn = psycopg2.connect(
            host="localhost",
            port=5433,
            user="postgres",
            password="Ais@9894",
            database="postgres"
        )
        cursor = conn.cursor()
        cursor.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name LIKE 'facebook%'
            ORDER BY table_name
        """)
        tables = [row[0] for row in cursor.fetchall()]
        cursor.close()
        conn.close()
        return f"Found {len(tables)} facebook tables: {tables[:5]}..."
    
    if not test_step("Check Facebook Tables", test_tables):
        return
    
    # Step 4: Test FacebookLegacyDB class
    def test_legacy_db():
        from app.services.facebook.fb_legacy_mapper import FacebookLegacyDB
        db = FacebookLegacyDB()
        result = db.query_one("SELECT COUNT(*) as c FROM facebook_pages")
        return f"FacebookLegacyDB works, pages count: {result}"
    
    if not test_step("FacebookLegacyDB Class", test_legacy_db):
        return
    
    # Step 5: Test mapper
    def test_mapper():
        from app.services.facebook.fb_legacy_mapper import get_legacy_mapper
        mapper = get_legacy_mapper()
        pages = mapper.get_pages()
        return f"Mapper works, found {len(pages)} pages"
    
    if not test_step("Legacy Mapper", test_mapper):
        return
    
    # Step 6: Test summary
    def test_summary():
        from app.services.facebook.fb_legacy_mapper import get_legacy_mapper
        mapper = get_legacy_mapper()
        summary = mapper.get_dashboard_summary()
        return f"Summary: {summary}"
    
    if not test_step("Dashboard Summary", test_summary):
        return
    
    print("\n" + "=" * 60)
    print("[SUCCESS] All tests passed!")
    print("=" * 60)
    print("\nThe API should work. Check server logs for more details.")


if __name__ == "__main__":
    main()
