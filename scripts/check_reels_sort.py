#!/usr/bin/env python3
"""Check why reels might not appear - created_time issue"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
    print("Checking Reels Sorting Issue")
    print("=" * 60)
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    # Check if reels join to facebook_posts properly
    print("\n1. Reels JOIN to facebook_posts:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            COUNT(*) as total_reels,
            COUNT(p.id) as matched_to_posts,
            COUNT(p.created_time) as with_created_time
        FROM facebook_posts_performance pp
        LEFT JOIN facebook_posts p ON pp.post_id = p.id
        WHERE pp.post_type = 'reel'
    """)
    row = cursor.fetchone()
    print(f"  Total reels: {row['total_reels']}")
    print(f"  Matched to facebook_posts: {row['matched_to_posts']}")
    print(f"  With created_time: {row['with_created_time']}")
    
    # If no created_time, reels will be at the end with NULLS LAST
    print("\n2. Where do reels appear in the sorted list?")
    print("-" * 40)
    cursor.execute("""
        WITH ranked AS (
            SELECT 
                pp.id,
                pp.post_type,
                p.created_time,
                ROW_NUMBER() OVER (ORDER BY p.created_time DESC NULLS LAST) as rank
            FROM facebook_posts_performance pp
            LEFT JOIN facebook_posts p ON pp.post_id = p.id
        )
        SELECT 
            post_type,
            MIN(rank) as first_rank,
            MAX(rank) as last_rank,
            COUNT(*) as count
        FROM ranked
        GROUP BY post_type
        ORDER BY first_rank
    """)
    for row in cursor.fetchall():
        print(f"  {row['post_type'] or 'NULL'}: ranks {row['first_rank']} to {row['last_rank']} ({row['count']} posts)")
    
    # Check if pp.created_time exists and has data for reels
    print("\n3. Does facebook_posts_performance have its own created_time?")
    print("-" * 40)
    cursor.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'facebook_posts_performance'
        AND column_name LIKE '%time%' OR column_name LIKE '%date%' OR column_name LIKE '%created%'
    """)
    cols = cursor.fetchall()
    for row in cols:
        print(f"  {row['column_name']}: {row['data_type']}")
    
    # Check pp.created_time for reels
    print("\n4. Checking pp columns with time data for reels:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(created_time) as with_pp_created_time,
            MIN(created_time) as oldest,
            MAX(created_time) as newest
        FROM facebook_posts_performance
        WHERE post_type = 'reel'
    """)
    row = cursor.fetchone()
    print(f"  Total reels: {row['total']}")
    print(f"  With pp.created_time: {row['with_pp_created_time']}")
    print(f"  Oldest: {row['oldest']}")
    print(f"  Newest: {row['newest']}")
    
    # Test the actual query used in the API
    print("\n5. Simulating API query (first 10 results):")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            pp.id,
            pp.post_type,
            p.created_time as p_created,
            pp.created_time as pp_created
        FROM facebook_posts_performance pp
        LEFT JOIN facebook_posts p ON pp.post_id = p.id
        ORDER BY p.created_time DESC NULLS LAST
        LIMIT 10
    """)
    for i, row in enumerate(cursor.fetchall(), 1):
        print(f"  {i}. type={row['post_type']}, p.created={row['p_created']}, pp.created={row['pp_created']}")
    
    # Check if we should use pp.created_time instead
    print("\n6. Compare: Sort by pp.created_time vs p.created_time:")
    print("-" * 40)
    cursor.execute("""
        SELECT 
            'Using pp.created_time' as method,
            post_type,
            COUNT(*) as in_top_50
        FROM (
            SELECT pp.post_type
            FROM facebook_posts_performance pp
            ORDER BY pp.created_time DESC NULLS LAST
            LIMIT 50
        ) sub
        GROUP BY post_type
        ORDER BY in_top_50 DESC
    """)
    print("  If sorted by pp.created_time:")
    for row in cursor.fetchall():
        print(f"    {row['post_type']}: {row['in_top_50']} in top 50")
    
    cursor.execute("""
        SELECT 
            'Using p.created_time' as method,
            post_type,
            COUNT(*) as in_top_50
        FROM (
            SELECT pp.post_type
            FROM facebook_posts_performance pp
            LEFT JOIN facebook_posts p ON pp.post_id = p.id
            ORDER BY p.created_time DESC NULLS LAST
            LIMIT 50
        ) sub
        GROUP BY post_type
        ORDER BY in_top_50 DESC
    """)
    print("\n  If sorted by p.created_time:")
    for row in cursor.fetchall():
        print(f"    {row['post_type']}: {row['in_top_50']} in top 50")
    
    cursor.close()
    conn.close()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
