#!/usr/bin/env python3
"""Check total_results in ads_details"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(host='localhost', port=5433, database='postgres', user='postgres', password='Ais@9894')
cur = conn.cursor(cursor_factory=RealDictCursor)

post_id = '107038946030147_952763240413227'

print(f"Checking post: {post_id}")
print("=" * 60)

cur.execute("""
    SELECT ads_details
    FROM facebook_posts_performance
    WHERE post_id = %s
""", (post_id,))

r = cur.fetchone()
if r and r['ads_details']:
    for i, ad in enumerate(r['ads_details']):
        print(f"\nAd {i+1}:")
        print(f"  ad_id: {ad.get('ad_id')}")
        print(f"  spend: {ad.get('spend')}")
        print(f"  total_results: {ad.get('total_results')}")
        print(f"  cost_per_result: {ad.get('cost_per_result')}")
        
        # Calculate what CPR should be
        spend = ad.get('spend', 0)
        results = ad.get('total_results', 0)
        if results and results > 0:
            calc_cpr = spend / results
            print(f"  calculated CPR (spend/results): {calc_cpr:.4f}")
        else:
            print(f"  calculated CPR: N/A (no results)")

conn.close()
