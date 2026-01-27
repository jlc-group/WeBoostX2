#!/usr/bin/env python3
"""
Script to sync Facebook Campaigns and AdSets data to PostgreSQL database
Compliant with Facebook Marketing API v23.0 documentation
"""

import os
import json
import time
import requests
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Facebook API Configuration
FB_USER_ACCESS_TOKEN = os.getenv("FB_USER_ACCESS_TOKEN")

# Database Configuration
PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

# Company Ad Account IDs (อ่านจาก .env file)
FB_AD_ACCOUNT_IDS = os.getenv("FB_AD_ACCOUNT_IDS", "").split(",")
COMPANY_AD_ACCOUNT_IDS = [f"act_{account_id.strip()}" for account_id in FB_AD_ACCOUNT_IDS if account_id.strip()]

def safe_convert_datetime(value):
    """Safely convert datetime string to timestamp"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except:
        return None

def safe_convert_json(value):
    """Safely convert value to JSON string"""
    if not value:
        return None
    try:
        return json.dumps(value) if isinstance(value, (dict, list)) else value
    except:
        return None

def insert_campaign(conn, campaign):
    """Insert or update campaign data in database"""
    query = """
    INSERT INTO facebook_campaigns (
        campaign_id, account_id, name, objective, status,
        daily_budget, lifetime_budget, start_time, stop_time,
        created_time, updated_time
    ) VALUES (
        %(campaign_id)s, %(account_id)s, %(name)s, %(objective)s, %(status)s,
        %(daily_budget)s, %(lifetime_budget)s, %(start_time)s, %(stop_time)s,
        %(created_time)s, %(updated_time)s
    ) ON CONFLICT (campaign_id) 
    DO UPDATE SET
        name = EXCLUDED.name,
        objective = EXCLUDED.objective,
        status = EXCLUDED.status,
        daily_budget = EXCLUDED.daily_budget,
        lifetime_budget = EXCLUDED.lifetime_budget,
        start_time = EXCLUDED.start_time,
        stop_time = EXCLUDED.stop_time,
        updated_time = EXCLUDED.updated_time
    """
    
    with conn.cursor() as cursor:
        cursor.execute(query, campaign)

def insert_adset(conn, adset):
    """Insert or update adset data in database"""
    query = """
    INSERT INTO facebook_adsets (
        adset_id, campaign_id, name, status, daily_budget, lifetime_budget,
        start_time, end_time, targeting, created_time, updated_time
    ) VALUES (
        %(adset_id)s, %(campaign_id)s, %(name)s, %(status)s, %(daily_budget)s,
        %(lifetime_budget)s, %(start_time)s, %(end_time)s, %(targeting)s,
        %(created_time)s, %(updated_time)s
    ) ON CONFLICT (adset_id)
    DO UPDATE SET
        name = EXCLUDED.name,
        status = EXCLUDED.status,
        daily_budget = EXCLUDED.daily_budget,
        lifetime_budget = EXCLUDED.lifetime_budget,
        start_time = EXCLUDED.start_time,
        end_time = EXCLUDED.end_time,
        targeting = EXCLUDED.targeting,
        updated_time = EXCLUDED.updated_time
    """
    
    with conn.cursor() as cursor:
        cursor.execute(query, adset)

def main():
    """Main function to sync Facebook campaigns and adsets"""
    print("🚀 Starting Facebook Campaigns & AdSets Sync Process...")
    
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASSWORD
        )
        conn.autocommit = True
        print("✅ Database connection established")

        total_campaigns = 0
        total_adsets = 0
        start_time = datetime.now()

        for account_id in COMPANY_AD_ACCOUNT_IDS:
            print(f"\n📊 Processing account: {account_id}")
            
            # ดึง campaign ด้วย fields ที่ครบถ้วนตาม Facebook API Documentation
            campaigns_fields = [
                'id', 'name', 'objective', 'status', 'effective_status',
                'daily_budget', 'lifetime_budget', 'budget_remaining',
                'start_time', 'stop_time', 'created_time', 'updated_time',
                'special_ad_categories', 'buying_type'
            ]
            campaigns_url = f"https://graph.facebook.com/v23.0/{account_id}/campaigns"
            campaigns_params = {
                'fields': ','.join(campaigns_fields),
                'access_token': FB_USER_ACCESS_TOKEN,
                'limit': 100
            }
            
            try:
                resp = requests.get(campaigns_url, params=campaigns_params)
                
                if resp.status_code != 200:
                    print(f"❌ Error fetching campaigns for {account_id}: {resp.status_code} {resp.text}")
                    continue
                    
                campaigns_json = resp.json()
                if 'error' in campaigns_json:
                    print(f"❌ Facebook API Error: {campaigns_json['error']}")
                    continue
                    
                campaigns_data = campaigns_json.get("data", [])
                print(f"📋 Found {len(campaigns_data)} campaigns for {account_id}")
                
                for camp in campaigns_data:
                    try:
                        campaign = {
                            "campaign_id": camp.get("id"),
                            "account_id": account_id,
                            "name": camp.get("name"),
                            "objective": camp.get("objective"),
                            "status": camp.get("status"),
                            "daily_budget": camp.get("daily_budget"),
                            "lifetime_budget": camp.get("lifetime_budget"),
                            "start_time": safe_convert_datetime(camp.get("start_time")),
                            "stop_time": safe_convert_datetime(camp.get("stop_time")),
                            "created_time": safe_convert_datetime(camp.get("created_time")),
                            "updated_time": safe_convert_datetime(camp.get("updated_time"))
                        }
                        
                        insert_campaign(conn, campaign)
                        total_campaigns += 1
                        print(f"  ✓ Synced campaign: {campaign['campaign_id']} - {campaign['name']}")
                        
                        # Rate limiting
                        time.sleep(0.2)
                        
                    except Exception as e:
                        print(f"  ❌ Error processing campaign {camp.get('id', 'unknown')}: {e}")
                        continue

                    # ดึง adsets ด้วย fields ที่ครบถ้วนตาม Facebook API Documentation
                    adsets_fields = [
                        'id', 'name', 'status', 'effective_status',
                        'daily_budget', 'lifetime_budget', 'budget_remaining',
                        'start_time', 'end_time', 'targeting', 'optimization_goal',
                        'billing_event', 'bid_amount', 'created_time', 'updated_time'
                    ]
                    adsets_url = f"https://graph.facebook.com/v23.0/{camp.get('id')}/adsets"
                    adsets_params = {
                        'fields': ','.join(adsets_fields),
                        'access_token': FB_USER_ACCESS_TOKEN,
                        'limit': 100
                    }
                    
                    try:
                        adsets_resp = requests.get(adsets_url, params=adsets_params)
                        
                        if adsets_resp.status_code != 200:
                            print(f"    ❌ Error fetching adsets for campaign {camp.get('id')}: {adsets_resp.status_code}")
                            continue
                            
                        adsets_json = adsets_resp.json()
                        if 'error' in adsets_json:
                            print(f"    ❌ Facebook API Error for adsets: {adsets_json['error']}")
                            continue
                            
                        adsets_data = adsets_json.get("data", [])
                        print(f"    📦 Found {len(adsets_data)} adsets for campaign {camp.get('id')}")
                        
                        for ad in adsets_data:
                            try:
                                adset = {
                                    "adset_id": ad.get("id"),
                                    "campaign_id": camp.get("id"),
                                    "name": ad.get("name"),
                                    "status": ad.get("status"),
                                    "daily_budget": ad.get("daily_budget"),
                                    "lifetime_budget": ad.get("lifetime_budget"),
                                    "start_time": safe_convert_datetime(ad.get("start_time")),
                                    "end_time": safe_convert_datetime(ad.get("end_time")),
                                    "targeting": safe_convert_json(ad.get("targeting")),
                                    "created_time": safe_convert_datetime(ad.get("created_time")),
                                    "updated_time": safe_convert_datetime(ad.get("updated_time"))
                                }
                                
                                insert_adset(conn, adset)
                                total_adsets += 1
                                
                                if total_adsets % 10 == 0:
                                    print(f"      ✓ Synced {total_adsets} adsets...")
                                    
                                # Rate limiting
                                time.sleep(0.1)
                                
                            except Exception as e:
                                print(f"      ❌ Error processing adset {ad.get('id', 'unknown')}: {e}")
                                continue
                                
                    except Exception as e:
                        print(f"    ❌ Error fetching adsets for campaign {camp.get('id')}: {e}")
                        continue
                        
            except Exception as e:
                print(f"❌ Error processing account {account_id}: {e}")
                continue

        # Summary
        end_time = datetime.now()
        duration = end_time - start_time
        
        print(f"\n🎉 Sync Process Completed!")
        print(f"📊 Total campaigns synced: {total_campaigns}")
        print(f"📦 Total adsets synced: {total_adsets}")
        print(f"⏱️  Duration: {duration}")
        print(f"🏁 Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔌 Database connection closed")

if __name__ == "__main__":
    main()
