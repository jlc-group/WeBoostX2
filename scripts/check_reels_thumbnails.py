#!/usr/bin/env python3
"""Check reels thumbnails specifically"""

import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': 'localhost',
    'port': 5433,
    'database': 'postgres',
    'user': 'postgres',
    'password': 'Ais@9894'
}

def main():
    print("=" * 60)
    print("Checking Reels Thumbnails")
    print("=" * 60)
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check reels thumbnail URL patterns
    print("\n1. Reels Thumbnail URL Patterns:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            CASE 
                WHEN thumbnail_url LIKE 'https://%' THEN 'HTTPS CDN'
                WHEN thumbnail_url LIKE 'http://localhost:8000%' THEN 'localhost:8000'
                WHEN thumbnail_url LIKE 'http://localhost%' THEN 'localhost (other)'
                WHEN thumbnail_url IS NULL THEN 'NULL'
                ELSE 'Other'
            END as url_type,
            COUNT(*) as count
        FROM facebook_posts_performance
        WHERE post_type = 'reel'
        GROUP BY url_type
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row['url_type']}: {row['count']} reels")
    
    # Check if reels have local_thumbnail_id
    print("\n2. Reels with local_thumbnail_id:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(local_thumbnail_id) as with_local_id,
            COUNT(CASE WHEN ms.is_stored_in_db = TRUE THEN 1 END) as stored_in_db
        FROM facebook_posts_performance pp
        LEFT JOIN media_storage ms ON pp.local_thumbnail_id = ms.id
        WHERE pp.post_type = 'reel'
    """)
    row = cursor.fetchone()
    print(f"  Total reels: {row['total']}")
    print(f"  With local_thumbnail_id: {row['with_local_id']}")
    print(f"  Stored in DB: {row['stored_in_db']}")
    
    # Sample some reels
    print("\n3. Sample Reels (first 5):")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            pp.id,
            pp.caption,
            pp.thumbnail_url,
            pp.video_views,
            pp.impressions,
            pp.reach,
            pp.local_thumbnail_id,
            p.created_time
        FROM facebook_posts_performance pp
        LEFT JOIN facebook_posts p ON pp.post_id = p.id
        WHERE pp.post_type = 'reel'
        ORDER BY pp.video_views DESC NULLS LAST
        LIMIT 5
    """)
    for i, row in enumerate(cursor.fetchall(), 1):
        print(f"\n  Reel {i}:")
        print(f"    ID: {row['id']}")
        print(f"    Caption: {(row['caption'] or '')[:50]}...")
        print(f"    Thumbnail: {(row['thumbnail_url'] or 'NULL')[:60]}...")
        print(f"    Views: {row['video_views']:,}" if row['video_views'] else "    Views: 0")
        print(f"    Impressions: {row['impressions']:,}" if row['impressions'] else "    Impressions: 0")
        print(f"    local_thumbnail_id: {row['local_thumbnail_id']}")
        print(f"    Created: {row['created_time']}")
    
    # Check why reels might not show - check created_time
    print("\n4. Reels created_time distribution:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            COUNT(*) as count,
            COUNT(p.created_time) as with_created_time,
            MIN(p.created_time) as oldest,
            MAX(p.created_time) as newest
        FROM facebook_posts_performance pp
        LEFT JOIN facebook_posts p ON pp.post_id = p.id
        WHERE pp.post_type = 'reel'
    """)
    row = cursor.fetchone()
    print(f"  Total reels: {row['count']}")
    print(f"  With created_time: {row['with_created_time']}")
    print(f"  Oldest: {row['oldest']}")
    print(f"  Newest: {row['newest']}")
    
    # The default sort is by p.created_time - check if reels have this
    print("\n5. Reels without created_time (won't sort properly):")
    print("-" * 40)
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM facebook_posts_performance pp
        LEFT JOIN facebook_posts p ON pp.post_id = p.id
        WHERE pp.post_type = 'reel'
        AND p.created_time IS NULL
    """)
    row = cursor.fetchone()
    print(f"  Reels without created_time: {row['count']}")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
