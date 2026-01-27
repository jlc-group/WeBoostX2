#!/usr/bin/env python3
"""Check CPR detail for specific post"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import psycopg2
from psycopg2.extras import RealDictCursor
import json

conn = psycopg2.connect(host='localhost', port=5433, database='postgres', user='postgres', password='Ais@9894')
cur = conn.cursor(cursor_factory=RealDictCursor)

# Check specific post from screenshot
post_id = '107038946030147_952763240413227'

print("=" * 60)
print(f"Checking post: {post_id}")
print("=" * 60)

cur.execute("""
    SELECT 
        post_id,
        ads_count,
        ads_total_media_cost,
        ads_avg_cost_per_result,
        ads_details,
        ads_cost_per_result_breakdown
    FROM facebook_posts_performance
    WHERE post_id = %s
""", (post_id,))

r = cur.fetchone()
if r:
    print(f"\n1. Basic info:")
    print(f"   ads_count: {r['ads_count']}")
    print(f"   total_cost: {r['ads_total_media_cost']}")
    print(f"   avg_cpr: {r['ads_avg_cost_per_result']}")
    
    print(f"\n2. ads_details:")
    if r['ads_details']:
        for i, ad in enumerate(r['ads_details']):
            print(f"\n   Ad {i+1}:")
            print(f"     ad_id: {ad.get('ad_id')}")
            print(f"     ad_name: {ad.get('ad_name', '')[:60]}...")
            print(f"     spend: {ad.get('spend')}")
            print(f"     reach: {ad.get('reach')}")
            print(f"     clicks: {ad.get('clicks')}")
            print(f"     cost_per_result: {ad.get('cost_per_result')}")
            # Check if there's a results field
            if 'results' in ad:
                print(f"     results: {ad.get('results')}")
            # Check all keys
            print(f"     all keys: {list(ad.keys())}")
    
    print(f"\n3. ads_cost_per_result_breakdown:")
    if r['ads_cost_per_result_breakdown']:
        breakdown = r['ads_cost_per_result_breakdown']
        print(f"   Keys: {list(breakdown.keys())}")
        for obj_type, obj_data in breakdown.items():
            print(f"\n   {obj_type}:")
            print(f"     total_spend: {obj_data.get('total_spend')}")
            print(f"     total_results: {obj_data.get('total_results')}")
            print(f"     overall_cost_per_result: {obj_data.get('overall_cost_per_result')}")
            if 'ads' in obj_data:
                print(f"     ads in breakdown:")
                for ad in obj_data['ads']:
                    print(f"       - ad_id: {ad.get('ad_id')}")
                    print(f"         spend: {ad.get('spend')}")
                    print(f"         results: {ad.get('results')}")
                    print(f"         cost_per_result: {ad.get('cost_per_result')}")
    else:
        print("   No breakdown data")
else:
    print("Post not found!")

# Check another post with data
print("\n\n" + "=" * 60)
print("Checking a post with CPR breakdown")
print("=" * 60)

cur.execute("""
    SELECT 
        post_id,
        ads_count,
        ads_total_media_cost,
        ads_details,
        ads_cost_per_result_breakdown
    FROM facebook_posts_performance
    WHERE ads_cost_per_result_breakdown IS NOT NULL
    AND ads_count > 0
    ORDER BY ads_total_media_cost DESC
    LIMIT 1
""")

r = cur.fetchone()
if r:
    print(f"\nPost: {r['post_id']}")
    print(f"ads_count: {r['ads_count']}")
    
    if r['ads_cost_per_result_breakdown']:
        breakdown = r['ads_cost_per_result_breakdown']
        for obj_type, obj_data in breakdown.items():
            print(f"\n{obj_type}:")
            print(f"  total_results: {obj_data.get('total_results')}")
            if 'ads' in obj_data and obj_data['ads']:
                print(f"  First ad results: {obj_data['ads'][0].get('results')}")

conn.close()
print("\n" + "=" * 60)
