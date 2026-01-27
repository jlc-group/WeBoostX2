#!/usr/bin/env python3
"""Check ads detail structure for posts"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect(host='localhost', port=5433, database='postgres', user='postgres', password='Ais@9894')
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("Ads Detail Analysis")
print("=" * 60)

# Check ads-related columns in facebook_posts_performance
print("\n1. Ads-related columns in facebook_posts_performance:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'facebook_posts_performance'
    AND column_name LIKE '%ads%'
    ORDER BY column_name
""")
for r in cur.fetchall():
    print(f"  {r['column_name']}: {r['data_type']}")

# Check ads_detail column content
print("\n2. Sample ads_details data (first 5 with ads):")
cur.execute("""
    SELECT 
        post_id,
        ads_count,
        ads_details,
        ads_cost_per_result_breakdown,
        ads_total_media_cost,
        ads_avg_cost_per_result
    FROM facebook_posts_performance
    WHERE ads_count > 0
    ORDER BY ads_count DESC
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"\n  Post: {r['post_id'][:40]}...")
    print(f"    ads_count: {r['ads_count']}")
    print(f"    ads_total_cost: {r['ads_total_media_cost']}")
    print(f"    ads_avg_cpr: {r['ads_avg_cost_per_result']}")
    if r['ads_details']:
        try:
            detail = r['ads_details']
            print(f"    ads_details type: {type(detail)}")
            if isinstance(detail, dict):
                print(f"    ads_details keys: {list(detail.keys())}")
                for k, v in list(detail.items())[:3]:
                    print(f"      - {k}: {str(v)[:100]}...")
            elif isinstance(detail, list):
                print(f"    ads_details has {len(detail)} items")
                for item in detail[:2]:
                    print(f"      - {str(item)[:150]}...")
        except Exception as e:
            print(f"    ads_details parse error: {e}")
            print(f"    raw: {str(r['ads_details'])[:200]}...")
    else:
        print(f"    ads_details: NULL")
    if r['ads_cost_per_result_breakdown']:
        print(f"    cpr_breakdown: {str(r['ads_cost_per_result_breakdown'])[:200]}...")

# Check facebook_ads table structure
print("\n\n3. facebook_ads table columns:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'facebook_ads'
    ORDER BY ordinal_position
    LIMIT 20
""")
for r in cur.fetchall():
    print(f"  {r['column_name']}: {r['data_type']}")

# Check facebook_ads_insights table structure
print("\n4. facebook_ads_insights table columns:")
cur.execute("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'facebook_ads_insights'
    ORDER BY ordinal_position
    LIMIT 25
""")
for r in cur.fetchall():
    print(f"  {r['column_name']}: {r['data_type']}")

# Check how ads link to posts
print("\n5. How ads link to posts (facebook_ads.post_id):")
cur.execute("""
    SELECT COUNT(*) as total_ads,
           COUNT(DISTINCT post_id) as unique_posts_with_ads
    FROM facebook_ads
    WHERE post_id IS NOT NULL
""")
r = cur.fetchone()
print(f"  Total ads: {r['total_ads']}")
print(f"  Unique posts with ads: {r['unique_posts_with_ads']}")

# Sample ads for a post with multiple ads
print("\n6. Sample: Post with multiple ads:")
cur.execute("""
    SELECT pp.post_id, pp.ads_count
    FROM facebook_posts_performance pp
    WHERE pp.ads_count > 1
    ORDER BY pp.ads_count DESC
    LIMIT 1
""")
sample = cur.fetchone()
if sample:
    print(f"  Post: {sample['post_id']}")
    print(f"  Ads count: {sample['ads_count']}")
    
    cur.execute("""
        SELECT 
            a.id as ad_id,
            a.name,
            a.status,
            a.adset_id
        FROM facebook_ads a
        WHERE a.post_id = %s
        LIMIT 5
    """, (sample['post_id'],))
    
    print(f"  Linked ads:")
    for ad in cur.fetchall():
        print(f"    - {ad['ad_id']}: {(ad['name'] or '')[:50]}... (status: {ad['status']})")

conn.close()
print("\n" + "=" * 60)
