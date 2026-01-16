"""
Script ทดสอบดึง Ads จาก TikTok API โดยตรง
"""
import os
import sys
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import httpx
from datetime import datetime, timedelta

# TikTok API settings
BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"
ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN") or os.getenv("TIKTOK_AD_TOKEN")

def fetch_ads_test(advertiser_id: str, days: int = -1):
    """ทดสอบดึง ads จาก TikTok API"""
    
    if not ACCESS_TOKEN:
        print("ERROR: TIKTOK_ACCESS_TOKEN not set!")
        return None
    
    print(f"Access Token: {ACCESS_TOKEN[:20]}...")
    print(f"Advertiser ID: {advertiser_id}")
    print(f"Days: {days} (-1 = fetch all)")
    print("=" * 50)
    
    all_ads = []
    page = 1
    
    with httpx.Client(timeout=60.0) as client:
        while True:
            params = {
                "advertiser_id": advertiser_id,
                "fields": json.dumps([
                    "advertiser_id", "campaign_id", "adgroup_id", "ad_id",
                    "tiktok_item_id", "ad_name", "operation_status",
                    "create_time", "modify_time"
                ]),
                "page": page,
                "page_size": 100,
            }
            
            # Add date filter only if days > 0
            if days > 0:
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)
                filtering = {
                    "creation_filter_start_time": start_date.strftime("%Y-%m-%d %H:%M:%S"),
                    "creation_filter_end_time": end_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
                params["filtering"] = json.dumps(filtering)
                print(f"Filtering: {filtering}")
            else:
                print("No date filter - fetching ALL ads")
            
            url = f"{BASE_URL}/ad/get/"
            print(f"\nCalling: {url}")
            print(f"Params: {params}")
            
            resp = client.get(
                url,
                headers={"Access-Token": ACCESS_TOKEN},
                params=params
            )
            
            print(f"\nStatus: {resp.status_code}")
            
            if resp.status_code != 200:
                print(f"Error: {resp.text}")
                break
            
            data = resp.json()
            print(f"Response code: {data.get('code')}")
            print(f"Response message: {data.get('message')}")
            
            if data.get('code') != 0:
                print(f"API Error: {data}")
                break
            
            d = data.get("data", {})
            ads = d.get("list", [])
            page_info = d.get("page_info", {})
            
            print(f"\nPage {page}/{page_info.get('total_page', 1)}")
            print(f"Ads in this page: {len(ads)}")
            print(f"Total number: {page_info.get('total_number', 0)}")
            
            if not ads:
                print("No more ads")
                break
            
            # แสดง ads บางตัว
            for i, ad in enumerate(ads[:5]):  # แสดงแค่ 5 ตัวแรก
                print(f"\n  Ad #{i+1}:")
                print(f"    ad_id: {ad.get('ad_id')}")
                print(f"    tiktok_item_id: {ad.get('tiktok_item_id')}")
                print(f"    ad_name: {ad.get('ad_name')[:50] if ad.get('ad_name') else None}...")
                print(f"    create_time: {ad.get('create_time')}")
            
            all_ads.extend(ads)
            
            # Check if we have more pages
            total_page = page_info.get("total_page", 1)
            if page >= total_page:
                break
            page += 1
    
    print("\n" + "=" * 50)
    print(f"Total ads fetched: {len(all_ads)}")
    
    # หา ads ที่มี tiktok_item_id
    ads_with_item = [a for a in all_ads if a.get("tiktok_item_id")]
    print(f"Ads with tiktok_item_id: {len(ads_with_item)}")
    
    # ค้นหา item_id ที่ต้องการ
    target_item_id = "7581911860388089106"
    matching_ads = [a for a in all_ads if a.get("tiktok_item_id") == target_item_id]
    print(f"\nAds matching item_id {target_item_id}: {len(matching_ads)}")
    for ad in matching_ads:
        print(f"  - ad_id: {ad.get('ad_id')}, name: {ad.get('ad_name')}")
    
    return all_ads


def get_advertiser_ids():
    """ดึง advertiser_id จาก database"""
    try:
        from app.core.database import SessionLocal
        from app.models import AdAccount
        from app.models.enums import Platform as PlatformEnum, AdAccountStatus
        
        db = SessionLocal()
        accounts = db.query(AdAccount).filter(
            AdAccount.platform == PlatformEnum.TIKTOK,
            AdAccount.status == AdAccountStatus.ACTIVE,
        ).all()
        
        result = [(acc.external_account_id, acc.name) for acc in accounts]
        db.close()
        return result
    except Exception as e:
        print(f"Error getting advertisers: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    print("TikTok Ads Fetch Test")
    print("=" * 50)
    
    # Get advertisers
    advertisers = get_advertiser_ids()
    if not advertisers:
        print("No advertisers found! Using hardcoded test ID...")
        # ใส่ advertiser_id ที่ต้องการทดสอบ
        advertisers = [("YOUR_ADVERTISER_ID", "Test")]
    
    print(f"\nFound {len(advertisers)} advertiser(s):")
    for adv_id, name in advertisers:
        print(f"  - {adv_id}: {name}")
    
    # ทดสอบกับ advertiser แรก
    if advertisers:
        adv_id, name = advertisers[0]
        print(f"\n\nTesting with: {name} ({adv_id})")
        print("=" * 50)
        
        # ทดสอบ fetch ALL ads (no date filter)
        print("\n>>> TEST 1: Fetch ALL ads (days=-1)")
        ads = fetch_ads_test(adv_id, days=-1)

