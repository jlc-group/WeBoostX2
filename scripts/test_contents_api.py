#!/usr/bin/env python3
"""Test contents API response"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import requests
import json

# Test the contents endpoint
url = "http://localhost:8201/api/v1/fb-dashboard/contents?limit=1"

print(f"Testing: {url}")
print("=" * 60)

try:
    response = requests.get(url, timeout=10)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        if data and len(data) > 0:
            content = data[0]
            print(f"\nFirst content item:")
            print(f"  platform_post_id: {content.get('platform_post_id')}")
            print(f"  ads_count: {content.get('ads_count')}")
            print(f"  ads_total_cost: {content.get('ads_total_cost')}")
            
            ads_details = content.get('ads_details')
            print(f"\n  ads_details type: {type(ads_details)}")
            
            if ads_details:
                print(f"  ads_details count: {len(ads_details)}")
                for i, ad in enumerate(ads_details[:2]):
                    print(f"\n  Ad {i+1}:")
                    print(f"    ad_id: {ad.get('ad_id')}")
                    print(f"    spend: {ad.get('spend')}")
                    print(f"    total_results: {ad.get('total_results')}")
                    print(f"    cost_per_result: {ad.get('cost_per_result')}")
                    print(f"    Keys: {list(ad.keys())[:10]}...")
            else:
                print(f"  ads_details: None or empty")
            
            # Also check cpr_breakdown
            cpr_breakdown = content.get('cpr_breakdown')
            print(f"\n  cpr_breakdown: {cpr_breakdown is not None}")
        else:
            print("No data returned")
    else:
        print(f"Error: {response.text}")
except Exception as e:
    print(f"Exception: {e}")
    print("Make sure the server is running on port 8201")

print("\n" + "=" * 60)
