#!/usr/bin/env python3
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host='localhost', port=5433, database='postgres', user='postgres', password='Ais@9894')
cur = conn.cursor(cursor_factory=RealDictCursor)

print("Columns in facebook_posts_performance with time/date:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'facebook_posts_performance' 
    AND (column_name LIKE '%time%' OR column_name LIKE '%date%' OR column_name LIKE '%create%')
    ORDER BY column_name
""")
for r in cur.fetchall():
    print(f"  {r['column_name']}: {r['data_type']}")

print("\nChecking create_time for reels:")
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(create_time) as with_create_time,
        MIN(create_time) as oldest,
        MAX(create_time) as newest
    FROM facebook_posts_performance
    WHERE post_type = 'reel'
""")
r = cur.fetchone()
print(f"  Total reels: {r['total']}")
print(f"  With create_time: {r['with_create_time']}")
print(f"  Oldest: {r['oldest']}")
print(f"  Newest: {r['newest']}")

print("\nSample reels sorted by create_time DESC:")
cur.execute("""
    SELECT id, post_type, create_time
    FROM facebook_posts_performance
    WHERE post_type = 'reel'
    ORDER BY create_time DESC
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  {r['id']}: {r['create_time']}")

conn.close()
