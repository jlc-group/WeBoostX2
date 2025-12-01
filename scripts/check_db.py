"""Check existing databases"""
import psycopg2

try:
    conn = psycopg2.connect(
        host='localhost', 
        port=5432, 
        user='postgres', 
        password='julaherb789!', 
        database='postgres'
    )
    cur = conn.cursor()
    cur.execute("SELECT datname FROM pg_database WHERE datname IN ('weboostx', 'weorder')")
    databases = [row[0] for row in cur.fetchall()]
    print('Databases found:', databases)
    
    # Check tables in weboostx if exists
    if 'weboostx' in databases:
        conn.close()
        conn = psycopg2.connect(
            host='localhost', 
            port=5432, 
            user='postgres', 
            password='julaherb789!', 
            database='weboostx'
        )
        cur = conn.cursor()
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        tables = [row[0] for row in cur.fetchall()]
        print(f'Tables in weboostx ({len(tables)}): {tables}')
    
    conn.close()
except Exception as e:
    print(f'Error: {e}')

