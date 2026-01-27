#!/usr/bin/env python3
"""Check media coverage for posts"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host='localhost', port=5433, database='postgres', user='postgres', password='Ais@9894')
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("Media Coverage Analysis")
print("=" * 60)

# Check posts with local_thumbnail_id
print("\n1. Posts with local_thumbnail_id set:")
cur.execute("""
    SELECT 
        COUNT(*) as total_posts,
        COUNT(local_thumbnail_id) as with_local_thumb,
        COUNT(CASE WHEN thumbnail_url IS NOT NULL THEN 1 END) as with_thumb_url
    FROM facebook_posts_performance
""")
r = cur.fetchone()
print(f"  Total posts: {r['total_posts']}")
print(f"  With local_thumbnail_id: {r['with_local_thumb']}")
print(f"  With thumbnail_url: {r['with_thumb_url']}")

# Check media_storage linking options
print("\n2. media_storage by source_post_id:")
cur.execute("""
    SELECT 
        COUNT(*) as total_media,
        COUNT(DISTINCT source_post_id) as unique_posts,
        COUNT(CASE WHEN is_stored_in_db = TRUE THEN 1 END) as stored_in_db
    FROM media_storage
    WHERE source_post_id IS NOT NULL
""")
r = cur.fetchone()
print(f"  Total media records: {r['total_media']}")
print(f"  Unique posts with media: {r['unique_posts']}")
print(f"  Stored in DB: {r['stored_in_db']}")

# Check how many posts could get thumbnails via source_post_id
print("\n3. Posts that could get thumbnails via media_storage.source_post_id:")
cur.execute("""
    SELECT COUNT(DISTINCT pp.post_id) as posts_with_media
    FROM facebook_posts_performance pp
    JOIN media_storage ms ON ms.source_post_id = pp.post_id
    WHERE ms.is_stored_in_db = TRUE
""")
r = cur.fetchone()
print(f"  Posts with media via source_post_id: {r['posts_with_media']}")

# Check thumbnail_url patterns
print("\n4. Posts without any thumbnail option:")
cur.execute("""
    SELECT COUNT(*) as no_thumb
    FROM facebook_posts_performance pp
    WHERE pp.local_thumbnail_id IS NULL
    AND (pp.thumbnail_url IS NULL OR pp.thumbnail_url NOT LIKE 'https://%')
    AND NOT EXISTS (
        SELECT 1 FROM media_storage ms 
        WHERE ms.source_post_id = pp.post_id 
        AND ms.is_stored_in_db = TRUE
    )
""")
r = cur.fetchone()
print(f"  Posts without any thumbnail: {r['no_thumb']}")

# Check media_storage categories
print("\n5. media_storage categories:")
cur.execute("""
    SELECT 
        media_category,
        COUNT(*) as count,
        COUNT(CASE WHEN is_stored_in_db = TRUE THEN 1 END) as in_db
    FROM media_storage
    GROUP BY media_category
    ORDER BY count DESC
    LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r['media_category'] or 'NULL'}: {r['count']} ({r['in_db']} in DB)")

conn.close()
print("\n" + "=" * 60)
