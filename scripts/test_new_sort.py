#!/usr/bin/env python3
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host='localhost', port=5433, database='postgres', user='postgres', password='Ais@9894')
cur = conn.cursor(cursor_factory=RealDictCursor)

print("Top 20 posts with NEW sorting (COALESCE):")
print("=" * 60)
cur.execute("""
    SELECT 
        pp.id,
        pp.post_type,
        COALESCE(p.created_time, pp.create_time) as created_at,
        pp.caption
    FROM facebook_posts_performance pp
    LEFT JOIN facebook_posts p ON pp.post_id = p.id
    ORDER BY COALESCE(p.created_time, pp.create_time) DESC NULLS LAST
    LIMIT 20
""")
for i, r in enumerate(cur.fetchall(), 1):
    caption = (r['caption'] or '')[:40].replace('\n', ' ')
    print(f"{i:2}. [{r['post_type']:6}] {r['created_at']} | {caption}...")

print("\nPost type distribution in top 50:")
cur.execute("""
    SELECT post_type, COUNT(*) as count
    FROM (
        SELECT pp.post_type
        FROM facebook_posts_performance pp
        LEFT JOIN facebook_posts p ON pp.post_id = p.id
        ORDER BY COALESCE(p.created_time, pp.create_time) DESC NULLS LAST
        LIMIT 50
    ) sub
    GROUP BY post_type
    ORDER BY count DESC
""")
for r in cur.fetchall():
    print(f"  {r['post_type']}: {r['count']}")

conn.close()
