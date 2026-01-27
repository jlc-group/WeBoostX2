#!/usr/bin/env python3
"""Check CPR breakdown structure"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect(host='localhost', port=5433, database='postgres', user='postgres', password='Ais@9894')
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("CPR Breakdown Analysis")
print("=" * 60)

# Check ads_cost_per_result_breakdown structure
print("\n1. Sample CPR breakdown data:")
cur.execute("""
    SELECT 
        post_id,
        ads_count,
        ads_total_media_cost,
        ads_avg_cost_per_result,
        ads_cost_per_result_breakdown,
        ads_details
    FROM facebook_posts_performance
    WHERE ads_cost_per_result_breakdown IS NOT NULL
    AND ads_count > 0
    ORDER BY ads_total_media_cost DESC
    LIMIT 3
""")

for r in cur.fetchall():
    print(f"\n  Post: {r['post_id'][:50]}...")
    print(f"    ads_count: {r['ads_count']}")
    print(f"    total_cost: {r['ads_total_media_cost']}")
    print(f"    avg_cpr: {r['ads_avg_cost_per_result']}")
    
    if r['ads_cost_per_result_breakdown']:
        breakdown = r['ads_cost_per_result_breakdown']
        print(f"    cpr_breakdown keys: {list(breakdown.keys())}")
        for obj_type, obj_data in breakdown.items():
            print(f"\n    {obj_type}:")
            if isinstance(obj_data, dict):
                print(f"      keys: {list(obj_data.keys())}")
                if 'total_cpr' in obj_data:
                    print(f"      total_cpr: {obj_data['total_cpr']}")
                if 'total_spend' in obj_data:
                    print(f"      total_spend: {obj_data['total_spend']}")
                if 'total_results' in obj_data:
                    print(f"      total_results: {obj_data['total_results']}")
                if 'ads' in obj_data:
                    print(f"      ads count: {len(obj_data['ads'])}")
                    for ad in obj_data['ads'][:1]:
                        print(f"        sample ad: {json.dumps(ad, indent=8)[:500]}...")

# Check what objectives exist
print("\n\n2. All objective types in CPR breakdown:")
cur.execute("""
    SELECT DISTINCT jsonb_object_keys(ads_cost_per_result_breakdown) as obj_type
    FROM facebook_posts_performance
    WHERE ads_cost_per_result_breakdown IS NOT NULL
""")
for r in cur.fetchall():
    print(f"  - {r['obj_type']}")

# Check ads_details structure for results
print("\n3. Sample ads_details with results:")
cur.execute("""
    SELECT 
        post_id,
        ads_details
    FROM facebook_posts_performance
    WHERE ads_details IS NOT NULL
    AND ads_count > 0
    ORDER BY ads_total_media_cost DESC
    LIMIT 1
""")
r = cur.fetchone()
if r and r['ads_details']:
    print(f"  Post: {r['post_id'][:50]}...")
    for ad in r['ads_details'][:2]:
        print(f"\n  Ad keys: {list(ad.keys())}")
        print(f"  Ad data: {json.dumps(ad, indent=4)}")

conn.close()
print("\n" + "=" * 60)
