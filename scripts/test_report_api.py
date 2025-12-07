"""
Test TikTok Report API response time - EXACT same method as old system
"""
import time
import requests
import json
import os
from dotenv import load_dotenv

# Load .env
load_dotenv()

# Use same env var as old system
ACCESS_TOKEN = os.getenv('TIKTOK_AD_TOKEN') or os.getenv('TIKTOK_ACCESS_TOKEN')
ADVERTISER_ID = os.getenv('ADVERTISER_ID_IDAC_MAIN')

print(f"=== TikTok Report API Test ===")
print(f"Advertiser ID: {ADVERTISER_ID}")
print(f"Token available: {bool(ACCESS_TOKEN)}")
print(f"Token first 20 chars: {ACCESS_TOKEN[:20] if ACCESS_TOKEN else 'N/A'}...")

# EXACT same API call as old system's fetch_ads_data_by_advertiser_id
url = "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/"
params = {
    "advertiser_id": ADVERTISER_ID,
    "report_type": "BASIC",
    "data_level": "AUCTION_AD",
    "dimensions": json.dumps(["ad_id"]),
    "metrics": json.dumps(["spend"]),
    "query_lifetime": True,
    "page_size": 1000,
    "page": 1
}

headers = {
    "Access-Token": ACCESS_TOKEN
}

print(f"\nCalling API...")
start = time.time()

try:
    response = requests.get(url, headers=headers, params=params, timeout=60)
    elapsed = time.time() - start
    
    data = response.json()
    print(f"\n=== Response ===")
    print(f"Status: {response.status_code}")
    print(f"Code: {data.get('code')}")
    print(f"Message: {data.get('message')}")
    
    ads_list = data.get("data", {}).get("list", [])
    print(f"Ads count: {len(ads_list)}")
    print(f"Time: {elapsed:.2f} seconds")
    
    # Show sample if available
    if ads_list:
        print(f"\nSample ad spend (first 5):")
        for ad in ads_list[:5]:
            dims = ad.get('dimensions', {})
            metrics = ad.get('metrics', {})
            print(f"  ad_id: {dims.get('ad_id')}, spend: {metrics.get('spend')}")
except requests.exceptions.Timeout:
    print(f"TIMEOUT after 60 seconds!")
except Exception as e:
    print(f"Error: {e}")

