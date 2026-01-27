#!/usr/bin/env python3
"""Check post types in facebook_posts_performance table"""

import psycopg2
from psycopg2.extras import RealDictCursor

# Database config
DB_CONFIG = {
    'host': 'localhost',
    'port': 5433,
    'database': 'postgres',
    'user': 'postgres',
    'password': 'Ais@9894'
}

def main():
    print("=" * 60)
    print("Checking Post Types in facebook_posts_performance")
    print("=" * 60)
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check post_type distribution
    print("\n1. Post Type Distribution:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            post_type, 
            COUNT(*) as count,
            COUNT(CASE WHEN thumbnail_url IS NOT NULL THEN 1 END) as with_thumbnail
        FROM facebook_posts_performance
        GROUP BY post_type
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row['post_type'] or 'NULL'}: {row['count']} posts ({row['with_thumbnail']} with thumbnails)")
    
    # Check if there are reels specifically
    print("\n2. Looking for Reels (case-insensitive):")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            post_type,
            COUNT(*) as count
        FROM facebook_posts_performance
        WHERE LOWER(post_type) LIKE '%reel%'
        GROUP BY post_type
    """)
    reels = cursor.fetchall()
    if reels:
        for row in reels:
            print(f"  Found: {row['post_type']} = {row['count']} posts")
    else:
        print("  No posts with 'reel' in post_type found")
    
    # Check facebook_posts table for comparison
    print("\n3. Post Types in facebook_posts table:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            type, 
            COUNT(*) as count
        FROM facebook_posts
        GROUP BY type
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row['type'] or 'NULL'}: {row['count']} posts")
    
    # Sample some posts to see actual post_type values
    print("\n4. Sample post_type values (first 20 unique):")
    print("-" * 40)
    cursor.execute("""
        SELECT DISTINCT post_type 
        FROM facebook_posts_performance 
        WHERE post_type IS NOT NULL
        LIMIT 20
    """)
    for row in cursor.fetchall():
        print(f"  - '{row['post_type']}'")
    
    # Check if video posts might be reels
    print("\n5. Video posts breakdown:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            post_type,
            COUNT(*) as count,
            AVG(video_views) as avg_views,
            AVG(video_duration) as avg_duration
        FROM facebook_posts_performance
        WHERE video_views > 0 OR video_duration > 0
        GROUP BY post_type
        ORDER BY count DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row['post_type'] or 'NULL'}: {row['count']} videos, avg views: {row['avg_views'] or 0:.0f}, avg duration: {row['avg_duration'] or 0:.1f}s")
    
    # Check columns that might indicate reels
    print("\n6. Checking for reels-related columns:")
    print("-" * 40)
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'facebook_posts_performance'
        AND (column_name LIKE '%reel%' OR column_name LIKE '%video%' OR column_name LIKE '%type%')
        ORDER BY column_name
    """)
    for row in cursor.fetchall():
        print(f"  {row['column_name']}: {row['data_type']}")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
