#!/usr/bin/env python3
"""
Facebook Ads Insights Sync Script - By Date Range
Sync insights data for specific date ranges to avoid overloading Facebook API

Usage:
    python sync_fb_insights_by_range.py --start 2025-10-01 --end 2025-10-31
    python sync_fb_insights_by_range.py --start 2025-11-01 --end 2025-11-30
    python sync_fb_insights_by_range.py --start 2025-12-01 --end 2025-12-31
    
    # หรือ sync หลายเดือนพร้อมกัน
    python sync_fb_insights_by_range.py --months "2025-10,2025-11,2025-12"
"""

import os
import psycopg2
import requests
import json
import time
import argparse
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from sku_utils import extract_sku_codes  # ← เพิ่มสำหรับดึง SKU codes

load_dotenv()

# Database configuration
PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

# Facebook API configuration
FB_USER_ACCESS_TOKEN = os.getenv("FB_USER_ACCESS_TOKEN")
COMPANY_AD_ACCOUNT_IDS = ["599000711226225", "486765798095431"]
API_VERSION = "v23.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

def log_message(message):
    """Log message with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        print(f"[{timestamp}] {message}")
    except UnicodeEncodeError:
        print(f"[{timestamp}] {message.encode('ascii', 'ignore').decode('ascii')}")

def handle_api_response(response, url):
    """Handle API response with proper error checking"""
    if response.status_code == 200:
        return response.json()
    elif response.status_code == 400:
        error_data = response.json()
        log_message(f"❌ API Error 400: {error_data.get('error', {}).get('message', 'Bad Request')}")
        log_message(f"URL: {url}")
        return None
    elif response.status_code == 429:
        log_message("⏳ Rate limit reached, waiting 60 seconds...")
        time.sleep(60)
        return None
    else:
        log_message(f"❌ API Error {response.status_code}: {response.text}")
        return None

def fetch_with_retry(url, params=None, max_retries=5, timeout=90):
    """Fetch data with exponential backoff retry logic"""
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            return response
        except requests.exceptions.Timeout:
            wait_time = (2 ** attempt) * 5  # 5, 10, 20, 40, 80 seconds
            if attempt < max_retries - 1:
                log_message(f"⏳ Timeout on attempt {attempt + 1}/{max_retries}, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                log_message(f"❌ Max retries reached after {max_retries} attempts")
                raise
        except requests.exceptions.RequestException as e:
            wait_time = (2 ** attempt) * 3
            if attempt < max_retries - 1:
                log_message(f"⚠️ Request error on attempt {attempt + 1}/{max_retries}: {e}")
                log_message(f"   Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                log_message(f"❌ Max retries reached: {e}")
                raise
    return None

def fetch_with_pagination(url, params=None):
    """Fetch data from Facebook API with pagination support"""
    all_data = []
    next_url = url
    page_count = 0
    consecutive_errors = 0  # 🔧 นับ error ติดต่อกัน
    max_consecutive_errors = 3  # 🔧 ยอมให้ error ติดต่อกันได้ไม่เกิน 3 ครั้ง
    
    while next_url:
        try:
            page_count += 1
            
            response = fetch_with_retry(next_url, params=params if next_url == url else None)
            if response is None:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    log_message(f"⚠️ Too many consecutive errors ({consecutive_errors}), stopping pagination")
                    break
                log_message(f"⚠️ Response is None, continuing with existing data ({len(all_data)} records)")
                continue  # ลองต่อแทนที่จะ break ทันที
                
            data = handle_api_response(response, next_url)
            
            if data is None:
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    log_message(f"⚠️ Too many consecutive errors ({consecutive_errors}), stopping pagination")
                    break
                log_message(f"⚠️ Data is None, continuing with existing data ({len(all_data)} records)")
                continue  # ลองต่อแทนที่จะ break ทันที
            
            # 🎉 Reset error counter on successful response
            consecutive_errors = 0
                
            if 'data' in data:
                all_data.extend(data['data'])
                log_message(f"   ✅ Page {page_count}: Got {len(data['data'])} records (total: {len(all_data)})")
                
            # Check for next page
            if 'paging' in data and 'next' in data['paging']:
                next_url = data['paging']['next']
                params = None  # Parameters are included in the next URL
            else:
                next_url = None
                
            # Rate limiting - be respectful to Facebook API
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            consecutive_errors += 1
            log_message(f"❌ Request error (attempt {consecutive_errors}/{max_consecutive_errors}): {e}")
            if consecutive_errors >= max_consecutive_errors:
                log_message(f"⚠️ Max consecutive errors reached, stopping pagination")
                break
            time.sleep(2)  # รอก่อนลองใหม่
            continue
    
    if len(all_data) > 0:
        log_message(f"✅ Pagination completed: {page_count} pages, {len(all_data)} total records")
    
    return all_data

def safe_float_convert(value, default=0.0):
    """Safely convert value to float"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default

def safe_int_convert(value, default=0):
    """Safely convert value to int"""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default

def extract_post_saves(actions_data):
    """
    Extract post_saves count from actions array
    
    🎯 CRITICAL: Facebook API returns these action_types for post saves:
    - 'onsite_conversion.post_save' = Actual post saves (paid ads)
    - 'post_save' = Alternative save metric (rarely used)
    - DO NOT include 'video_save', 'link_save', or other save types
    """
    if not actions_data or not isinstance(actions_data, list):
        return 0
    
    # Valid post save action types
    valid_save_types = ['onsite_conversion.post_save', 'post_save']
    
    total_saves = 0
    for action in actions_data:
        action_type = action.get('action_type', '')
        
        # Only count valid post save action types
        if action_type in valid_save_types:
            value = action.get('value', 0)
            total_saves += safe_int_convert(value)
    
    return total_saves

def upsert_insight(conn, insight):
    """Insert or update insight data"""
    with conn.cursor() as cur:
        # 🛡️ Safety check: Verify ad exists in facebook_ads table
        ad_id = insight.get("ad_id")
        if not ad_id:
            log_message(f"⚠️ Skipping insight: missing ad_id")
            return {"success": False, "action": "skipped", "reason": "missing_ad_id"}
        
        try:
            cur.execute("SELECT 1 FROM facebook_ads WHERE ad_id = %s", (ad_id,))
            if not cur.fetchone():
                log_message(f"⚠️ Skipping insight for ad {ad_id}: ad not found in facebook_ads table")
                return {"success": False, "action": "skipped", "reason": "ad_not_found"}
        except Exception as e:
            log_message(f"⚠️ Error checking ad existence for {ad_id}: {e}")
            return {"success": False, "action": "skipped", "reason": "check_error"}
        
        # Parse results field
        results_value = 0
        results_indicator = None
        results_raw = insight.get("results", [])
        
        if results_raw and isinstance(results_raw, list) and len(results_raw) > 0:
            result_data = results_raw[0]
            if isinstance(result_data, dict):
                results_indicator = result_data.get('indicator')
                values = result_data.get('values', [])
                if values and len(values) > 0:
                    results_value = safe_int_convert(values[0].get('value', 0))
        
        # Parse cost_per_result
        cost_per_result = 0.0
        cost_per_result_raw = insight.get("cost_per_result", [])
        
        if cost_per_result_raw:
            try:
                if isinstance(cost_per_result_raw, list) and len(cost_per_result_raw) > 0:
                    first_result = cost_per_result_raw[0]
                    if isinstance(first_result, dict):
                        if 'values' in first_result and len(first_result['values']) > 0:
                            cost_per_result = safe_float_convert(first_result['values'][0].get('value'))
                        elif 'value' in first_result:
                            cost_per_result = safe_float_convert(first_result.get('value'))
            except Exception as e:
                log_message(f"⚠️ Error parsing cost_per_result: {e}")
        
        # Extract post_saves
        actions_data = insight.get("actions", [])
        post_saves = extract_post_saves(actions_data)
        
        # ดึง ad_name จาก facebook_ads และคำนวณ sku_codes
        ad_name = None
        sku_codes_json = None
        try:
            cur.execute("SELECT name FROM facebook_ads WHERE ad_id = %s", (insight.get("ad_id"),))
            ad_record = cur.fetchone()
            if ad_record:
                ad_name = ad_record[0]
                sku_codes = extract_sku_codes(ad_name) if ad_name else []
                sku_codes_json = json.dumps(sku_codes) if sku_codes else None
        except Exception as e:
            log_message(f"⚠️ Warning: Could not fetch ad_name for ad_id {insight.get('ad_id')}: {e}")
        
        insight_data = {
            "ad_id": insight.get("ad_id"),
            "adset_id": insight.get("adset_id"),
            "campaign_id": insight.get("campaign_id"),
            "account_id": insight.get("account_id"),
            "impressions": safe_int_convert(insight.get("impressions")),
            "reach": safe_int_convert(insight.get("reach")),
            "clicks": safe_int_convert(insight.get("clicks")),
            "spend": safe_float_convert(insight.get("spend")),
            "cpm": safe_float_convert(insight.get("cpm")),
            "cpp": safe_float_convert(insight.get("cpp")),
            "ctr": safe_float_convert(insight.get("ctr")),
            "frequency": safe_float_convert(insight.get("frequency")),
            "cost_per_result": cost_per_result,
            "post_saves": post_saves,
            "results": results_value,
            "results_indicator": results_indicator,
            "ad_name": ad_name,
            "sku_codes": sku_codes_json,
            "date_start": insight.get("date_start"),
            "date_stop": insight.get("date_stop"),
            "actions": json.dumps(insight.get("actions", [])),
            "action_values": json.dumps(insight.get("action_values", [])),
            "video_actions": json.dumps(insight.get("video_actions", []))
        }
        
        try:
            # Check if record exists
            cur.execute("""
                SELECT 1 FROM facebook_ads_insights 
                WHERE ad_id = %s AND date_start = %s AND date_stop = %s
            """, (insight_data["ad_id"], insight_data["date_start"], insight_data["date_stop"]))
            existing_record = cur.fetchone()
            
            cur.execute("""
                INSERT INTO facebook_ads_insights (
                    ad_id, adset_id, campaign_id, account_id,
                    impressions, reach, clicks, spend, cpm, cpp, ctr, frequency,
                    cost_per_result, post_saves, results, results_indicator,
                    ad_name, sku_codes,
                    date_start, date_stop,
                    actions, action_values, video_actions,
                    created_at, updated_at
                ) VALUES (
                    %(ad_id)s, %(adset_id)s, %(campaign_id)s, %(account_id)s,
                    %(impressions)s, %(reach)s, %(clicks)s, %(spend)s, 
                    %(cpm)s, %(cpp)s, %(ctr)s, %(frequency)s,
                    %(cost_per_result)s, %(post_saves)s, %(results)s, %(results_indicator)s,
                    %(ad_name)s, %(sku_codes)s,
                    %(date_start)s, %(date_stop)s,
                    %(actions)s, %(action_values)s, %(video_actions)s,
                    NOW(), NOW()
                )
                ON CONFLICT (ad_id, date_start, date_stop) DO UPDATE SET
                    adset_id = EXCLUDED.adset_id,
                    campaign_id = EXCLUDED.campaign_id,
                    account_id = EXCLUDED.account_id,
                    impressions = EXCLUDED.impressions,
                    reach = EXCLUDED.reach,
                    clicks = EXCLUDED.clicks,
                    spend = EXCLUDED.spend,
                    cpm = EXCLUDED.cpm,
                    cpp = EXCLUDED.cpp,
                    ctr = EXCLUDED.ctr,
                    frequency = EXCLUDED.frequency,
                    cost_per_result = EXCLUDED.cost_per_result,
                    actions = EXCLUDED.actions,
                    post_saves = EXCLUDED.post_saves,
                    results = EXCLUDED.results,
                    results_indicator = EXCLUDED.results_indicator,
                    ad_name = EXCLUDED.ad_name,
                    sku_codes = EXCLUDED.sku_codes,
                    action_values = EXCLUDED.action_values,
                    video_actions = EXCLUDED.video_actions,
                    updated_at = NOW()
            """, insight_data)
            
            action = "updated" if existing_record else "inserted"
            return {"success": True, "action": action}
            
        except Exception as e:
            log_message(f"❌ Error upserting insight for ad {insight_data.get('ad_id')}: {e}")
            raise  # Re-raise exception so outer try-catch can handle rollback

def sync_insights_by_range(conn, account_id, start_date, end_date):
    """Sync insights data for specific date range"""
    log_message(f"🔄 Syncing insights for account {account_id}")
    log_message(f"📅 Date range: {start_date} to {end_date}")
    
    api_account_id = f"act_{account_id}"
    url = f"{BASE_URL}/{api_account_id}/insights"
    params = {
        'fields': 'ad_id,adset_id,campaign_id,account_id,impressions,reach,clicks,spend,cpm,cpp,ctr,frequency,actions,cost_per_action_type,cost_per_result,results,date_start,date_stop',
        'level': 'ad',
        'time_range': json.dumps({
            'since': start_date,
            'until': end_date
        }),
        'time_increment': 1,  # Daily breakdown
        'access_token': FB_USER_ACCESS_TOKEN,
        'limit': 100
    }
    
    log_message(f"📡 Fetching insights from Facebook API...")
    insights = fetch_with_pagination(url, params)
    
    if not insights:
        log_message(f"⚠️ No insights data returned for this date range")
        return {"inserted": 0, "updated": 0}
    
    log_message(f"✅ Fetched {len(insights)} insight records")
    
    insights_count = 0
    inserted_count = 0
    updated_count = 0
    skipped_count = 0
    
    for insight in insights:
        try:
            result = upsert_insight(conn, insight)
            if result["success"]:
                if result["action"] == "inserted":
                    inserted_count += 1
                elif result["action"] == "updated":
                    updated_count += 1
                insights_count += 1
                conn.commit()  # Commit each successful insert/update
            elif result["action"] == "skipped":
                skipped_count += 1
        except Exception as e:
            log_message(f"❌ Error processing insight for ad {insight.get('ad_id')}: {e}")
            conn.rollback()  # Rollback failed transaction
            continue
    
    log_message(f"✅ Processed {insights_count} insights records:")
    log_message(f"   ➕ New records inserted: {inserted_count}")
    log_message(f"   🔄 Existing records updated: {updated_count}")
    if skipped_count > 0:
        log_message(f"   ⏭️  Records skipped (ad not found): {skipped_count}")
    
    return {"inserted": inserted_count, "updated": updated_count, "skipped": skipped_count}

def get_month_date_range(year_month_str):
    """
    Convert YYYY-MM string to first and last day of month
    Example: "2025-10" -> ("2025-10-01", "2025-10-31")
    """
    try:
        year, month = map(int, year_month_str.split('-'))
        start_date = datetime(year, month, 1)
        
        # Get last day of month
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(days=1)
        
        return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")
    except Exception as e:
        log_message(f"❌ Error parsing month: {year_month_str}, {e}")
        return None, None

def main():
    parser = argparse.ArgumentParser(description='Sync Facebook Ads Insights by date range')
    parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    parser.add_argument('--months', help='Comma-separated months (YYYY-MM,YYYY-MM,...)')
    parser.add_argument('--account', help='Specific account ID to sync (optional)')
    
    args = parser.parse_args()
    
    # Validate arguments
    if not args.months and (not args.start or not args.end):
        print("❌ Error: Must provide either --months or both --start and --end")
        print("\nExamples:")
        print("  python sync_fb_insights_by_range.py --start 2025-10-01 --end 2025-10-31")
        print("  python sync_fb_insights_by_range.py --months '2025-10,2025-11,2025-12'")
        return
    
    # Connect to database
    try:
        conn = psycopg2.connect(
            host=PG_HOST,
            port=PG_PORT,
            database=PG_DB,
            user=PG_USER,
            password=PG_PASSWORD
        )
        log_message("✅ Connected to database")
    except Exception as e:
        log_message(f"❌ Database connection error: {e}")
        return
    
    # Determine accounts to sync
    accounts = [args.account] if args.account else COMPANY_AD_ACCOUNT_IDS
    
    # Determine date ranges to sync
    date_ranges = []
    
    if args.months:
        # Parse months
        months_list = [m.strip() for m in args.months.split(',')]
        for month_str in months_list:
            start, end = get_month_date_range(month_str)
            if start and end:
                date_ranges.append((start, end, f"Month {month_str}"))
    else:
        # Single date range - validate and swap if needed
        start = args.start
        end = args.end
        
        # ✅ ตรวจสอบและสลับวันที่ถ้าผู้ใช้พิมพ์กลับกัน
        try:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            
            if start_dt > end_dt:
                log_message(f"⚠️  Warning: Start date ({start}) is after end date ({end})")
                log_message(f"   🔄 Automatically swapping dates...")
                start, end = end, start
                log_message(f"   ✅ Corrected range: {start} to {end}")
        except ValueError as e:
            log_message(f"❌ Invalid date format: {e}")
            log_message(f"   Please use YYYY-MM-DD format")
            conn.close()
            return
        
        date_ranges.append((start, end, f"{start} to {end}"))
    
    # Sync each account for each date range
    total_stats = {"inserted": 0, "updated": 0, "skipped": 0}
    
    log_message("="*80)
    log_message("🚀 Starting Facebook Ads Insights Sync by Date Range")
    log_message("="*80)
    
    for account_id in accounts:
        log_message(f"\n🏢 Processing account: {account_id}")
        
        for start_date, end_date, label in date_ranges:
            log_message(f"\n📅 Range: {label}")
            
            try:
                stats = sync_insights_by_range(conn, account_id, start_date, end_date)
                total_stats["inserted"] += stats["inserted"]
                total_stats["updated"] += stats["updated"]
                total_stats["skipped"] += stats.get("skipped", 0)
                
                log_message(f"✅ Account {account_id} - {label} completed")
                
                # Wait between ranges to be respectful to API
                time.sleep(2)
                
            except Exception as e:
                log_message(f"❌ Error syncing {account_id} - {label}: {e}")
                continue
    
    conn.close()
    
    log_message("\n" + "="*80)
    log_message("🎉 Sync completed!")
    log_message("="*80)
    log_message(f"📊 Total Summary:")
    log_message(f"   ➕ New records inserted: {total_stats['inserted']}")
    log_message(f"   🔄 Existing records updated: {total_stats['updated']}")
    if total_stats['skipped'] > 0:
        log_message(f"   ⏭️  Records skipped: {total_stats['skipped']}")
        log_message(f"   💡 Tip: Run ads sync first to import missing ads")
    log_message(f"   📝 Total records processed: {total_stats['inserted'] + total_stats['updated']}")

if __name__ == "__main__":
    main()
