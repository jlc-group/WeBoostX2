import os
import psycopg2
import requests
import json
import time
import argparse  # ← เพิ่ม argparse
from datetime import datetime, timedelta
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
        # Fallback to ASCII-safe output
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
    
    while next_url:
        try:
            page_count += 1
            log_message(f"📄 Fetching page {page_count}...")
            
            response = fetch_with_retry(next_url, params=params if next_url == url else None)
            if response is None:
                break
                
            data = handle_api_response(response, next_url)
            
            if data is None:
                break
                
            if 'data' in data:
                all_data.extend(data['data'])
                log_message(f"   ✅ Got {len(data['data'])} records (total: {len(all_data)})")
                
            # Check for next page
            if 'paging' in data and 'next' in data['paging']:
                next_url = data['paging']['next']
                params = None  # Parameters are included in the next URL
            else:
                next_url = None
                
            # Rate limiting - be respectful to Facebook API
            time.sleep(0.5)
            
        except requests.exceptions.RequestException as e:
            log_message(f"❌ Request error: {e}")
            break
            
    return all_data

def insert_ad_account(conn, account):
    """Insert or update ad account data"""
    with conn.cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO facebook_ad_accounts (
                    id, name, currency, account_status, business_id,
                    created_time, updated_time, created_at, updated_at
                ) VALUES (
                    %(id)s, %(name)s, %(currency)s, %(account_status)s, %(business_id)s,
                    %(created_time)s, %(updated_time)s, NOW(), NOW()
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    currency = EXCLUDED.currency,
                    account_status = EXCLUDED.account_status,
                    business_id = EXCLUDED.business_id,
                    created_time = EXCLUDED.created_time,
                    updated_time = EXCLUDED.updated_time,
                    updated_at = NOW();
            """, account)
            log_message(f"✅ Account {account['id']} inserted/updated successfully")
        except Exception as e:
            log_message(f"❌ Error inserting account {account.get('id')}: {e}")

def insert_campaign(conn, campaign):
    """Insert or update campaign data"""
    with conn.cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO facebook_campaigns (
                    campaign_id, account_id, name, objective, status,
                    daily_budget, lifetime_budget, start_time, stop_time,
                    created_time, updated_time, created_at, updated_at
                ) VALUES (
                    %(campaign_id)s, %(account_id)s, %(name)s, %(objective)s, %(status)s,
                    %(daily_budget)s, %(lifetime_budget)s, %(start_time)s, %(stop_time)s,
                    %(created_time)s, %(updated_time)s, NOW(), NOW()
                )
                ON CONFLICT (campaign_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    objective = EXCLUDED.objective,
                    status = EXCLUDED.status,
                    daily_budget = EXCLUDED.daily_budget,
                    lifetime_budget = EXCLUDED.lifetime_budget,
                    start_time = EXCLUDED.start_time,
                    stop_time = EXCLUDED.stop_time,
                    created_time = EXCLUDED.created_time,
                    updated_time = EXCLUDED.updated_time,
                    updated_at = NOW();
            """, campaign)
        except Exception as e:
            log_message(f"❌ Error inserting campaign {campaign.get('campaign_id')}: {e}")

def insert_ad(conn, ad):
    """Insert or update ad data"""
    with conn.cursor() as cur:
        try:
            cur.execute("""
                INSERT INTO facebook_ads (
                    ad_id, adset_id, name, status, creative, preview_url, post_id,
                    created_time, updated_time, created_at, updated_at
                ) VALUES (
                    %(ad_id)s, %(adset_id)s, %(name)s, %(status)s, %(creative)s, %(preview_url)s, %(post_id)s,
                    %(created_time)s, %(updated_time)s, NOW(), NOW()
                )
                ON CONFLICT (ad_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    status = EXCLUDED.status,
                    creative = EXCLUDED.creative,
                    preview_url = EXCLUDED.preview_url,
                    post_id = COALESCE(EXCLUDED.post_id, facebook_ads.post_id),  -- เก็บ post_id เดิมถ้า API ไม่ส่งมา
                    created_time = EXCLUDED.created_time,
                    updated_time = EXCLUDED.updated_time,
                    updated_at = NOW();
            """, ad)
        except Exception as e:
            log_message(f"❌ Error inserting ad {ad.get('ad_id')}: {e}")

def insert_ad_insight(conn, insight):
    """Insert or update ad insights data with UPSERT for accurate dashboard data"""
    with conn.cursor() as cur:
        try:
            
            # 🔧 Safety Check: ตรวจสอบว่า ad_id มีอยู่ใน facebook_ads table และดึง ad_name
            cur.execute("SELECT ad_id, name FROM facebook_ads WHERE ad_id = %s", (insight['ad_id'],))
            ad_record = cur.fetchone()
            if not ad_record:
                log_message(f"⚠️ Warning: ad_id {insight['ad_id']} not found in facebook_ads table, skipping insight")
                return {"success": False, "action": "skipped", "reason": "ad_not_found"}
            
            # ดึง ad_name และแปลงเป็น SKU codes
            ad_name = ad_record[1]  # name column
            sku_codes = extract_sku_codes(ad_name) if ad_name else []
            sku_codes_json = json.dumps(sku_codes) if sku_codes else None
            
            # เช็คว่าข้อมูลมีอยู่แล้วหรือไม่
            cur.execute("""
                SELECT id FROM facebook_ads_insights 
                WHERE ad_id = %s AND date_start = %s AND date_stop = %s
            """, (insight['ad_id'], insight['date_start'], insight['date_stop']))
            existing_record = cur.fetchone()
            
            # ✅ แก้ไข: เพิ่ม UPSERT โดยใช้ ON CONFLICT เพื่อความแม่นยำของ Dashboard
            # เพิ่ม ad_name และ sku_codes ลงใน insight dict
            insight['ad_name'] = ad_name
            insight['sku_codes'] = sku_codes_json
            
            cur.execute("""
                INSERT INTO facebook_ads_insights (
                    ad_id, adset_id, campaign_id, account_id,
                    impressions, reach, clicks, spend, cpm, cpp, ctr, frequency,
                    cost_per_result, actions, post_saves, results, results_indicator,
                    action_values, video_actions,
                    ad_name, sku_codes,
                    date_start, date_stop, created_at, updated_at
                ) VALUES (
                    %(ad_id)s, %(adset_id)s, %(campaign_id)s, %(account_id)s,
                    %(impressions)s, %(reach)s, %(clicks)s, %(spend)s, %(cpm)s, %(cpp)s, %(ctr)s, %(frequency)s,
                    %(cost_per_result)s, %(actions)s, %(post_saves)s, %(results)s, %(results_indicator)s,
                    %(action_values)s, %(video_actions)s,
                    %(ad_name)s, %(sku_codes)s,
                    %(date_start)s, %(date_stop)s, NOW(), NOW()
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
                    action_values = EXCLUDED.action_values,
                    video_actions = EXCLUDED.video_actions,
                    ad_name = EXCLUDED.ad_name,
                    sku_codes = EXCLUDED.sku_codes,
                    updated_at = NOW()
            """, insight)
            
            action = "updated" if existing_record else "inserted"
            return {"success": True, "action": action}
            
        except Exception as e:
            log_message(f"❌ Error upserting insight for ad {insight.get('ad_id')}: {e}")
            return {"success": False, "action": "error", "reason": str(e)}

def get_date_ranges(days_back=30):
    """Generate date ranges for data fetching"""
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days_back)
    
    return {
        "since": start_date.strftime("%Y-%m-%d"),
        "until": end_date.strftime("%Y-%m-%d")
    }

def sync_ad_accounts(conn):
    """Sync ad account information first"""
    log_message("🔄 Syncing ad accounts...")
    
    for account_id in COMPANY_AD_ACCOUNT_IDS:
        try:
            # Use act_ prefix for API calls but store without prefix
            api_account_id = f"act_{account_id}"
            url = f"{BASE_URL}/{api_account_id}"
            params = {
                'fields': 'id,name,currency,account_status,business',
                'access_token': FB_USER_ACCESS_TOKEN
            }
            
            response = fetch_with_retry(url, params=params, timeout=90)
            if response is None:
                continue
                
            data = handle_api_response(response, url)
            
            if data:
                account_data = {
                    "id": account_id,  # Store without act_ prefix
                    "name": data.get("name", "Unknown Account"),
                    "currency": data.get("currency", "USD"),
                    "account_status": str(data.get("account_status", 1)),
                    "business_id": data.get("business", {}).get("id") if data.get("business") else None,
                    "created_time": datetime.now().isoformat(),
                    "updated_time": datetime.now().isoformat()
                }
                insert_ad_account(conn, account_data)
                
        except Exception as e:
            log_message(f"❌ Error syncing account {account_id}: {e}")
            # Create basic account record anyway
            account_data = {
                "id": account_id,
                "name": f"Account {account_id}",
                "currency": "USD",
                "account_status": "1",
                "business_id": None,
                "created_time": datetime.now().isoformat(),
                "updated_time": datetime.now().isoformat()
            }
            insert_ad_account(conn, account_data)

def sync_campaigns(conn, account_id):
    """Sync campaigns for an account"""
    log_message(f"🔄 Syncing campaigns for {account_id}")
    
    api_account_id = f"act_{account_id}"
    url = f"{BASE_URL}/{api_account_id}/campaigns"
    params = {
        'fields': 'id,account_id,name,objective,status,daily_budget,lifetime_budget,start_time,stop_time,created_time,updated_time',
        'access_token': FB_USER_ACCESS_TOKEN,
        'limit': 100
    }
    
    campaigns = fetch_with_pagination(url, params)
    
    success_count = 0
    for campaign in campaigns:
        campaign_data = {
            "campaign_id": campaign.get("id"),
            "account_id": account_id,  # Use account_id without prefix
            "name": campaign.get("name"),
            "objective": campaign.get("objective"),
            "status": campaign.get("status"),
            "daily_budget": campaign.get("daily_budget"),
            "lifetime_budget": campaign.get("lifetime_budget"),
            "start_time": campaign.get("start_time"),
            "stop_time": campaign.get("stop_time"),
            "created_time": campaign.get("created_time"),
            "updated_time": campaign.get("updated_time")
        }
        insert_campaign(conn, campaign_data)
        success_count += 1
    
    log_message(f"✅ Synced {success_count} campaigns")
    return campaigns

def sync_ads(conn, account_id):
    """Sync ads for an account"""
    log_message(f"🔄 Syncing ads for {account_id}")
    
    api_account_id = f"act_{account_id}"
    url = f"{BASE_URL}/{api_account_id}/ads"
    params = {
        'fields': 'id,adset_id,name,status,creative,preview_url,created_time,updated_time',
        'access_token': FB_USER_ACCESS_TOKEN,
        'limit': 100
    }
    
    ads = fetch_with_pagination(url, params)
    
    success_count = 0
    for ad in ads:
        ad_data = {
            "ad_id": ad.get("id"),
            "adset_id": ad.get("adset_id"),
            "name": ad.get("name"),
            "status": ad.get("status"),
            "creative": json.dumps(ad.get("creative")) if ad.get("creative") else None,
            "preview_url": ad.get("preview_url"),
            "post_id": ad.get("post_id"),
            "created_time": ad.get("created_time"),
            "updated_time": ad.get("updated_time")
        }
        insert_ad(conn, ad_data)
        success_count += 1
    
    log_message(f"✅ Synced {success_count} ads")
    return ads

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
    
    Args:
        actions_data: List of action objects from Facebook API
        
    Returns:
        int: Total post saves count
    
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

def sync_insights(conn, account_id, time_range=None):
    """Sync insights data using account-level insights API"""
    log_message(f"🔄 Syncing insights for {account_id}")
    
    if not time_range:
        time_range = get_date_ranges(7)  # Default 7 days if not provided
    
    api_account_id = f"act_{account_id}"
    url = f"{BASE_URL}/{api_account_id}/insights"
    params = {
        # ✅ เพิ่ม cost_per_result และ results ใน fields เพื่อดึงข้อมูลจาก Facebook API
        'fields': 'ad_id,adset_id,campaign_id,account_id,impressions,reach,clicks,spend,cpm,cpp,ctr,frequency,actions,cost_per_action_type,cost_per_result,results,date_start,date_stop',
        'level': 'ad',  # Get insights at ad level
        'time_range': json.dumps(time_range),
        'time_increment': 1,  # ⭐ แยกข้อมูลเป็นรายวัน (daily breakdown)
        'access_token': FB_USER_ACCESS_TOKEN,
        'limit': 100
    }
    
    insights = fetch_with_pagination(url, params)
    
    insights_count = 0
    updated_count = 0  # 🔧 เพิ่มตัวแปรนับจำนวน insights ที่ update
    skipped_count = 0  # 🔧 เพิ่มตัวแปรนับจำนวน insights ที่ skip
    for insight in insights:
        try:
            # 🔍 Debug: แสดงข้อมูล raw จาก API (แสดง 3 record แรก)
            if insights_count < 3:
                log_message(f"🔍 DEBUG - Insight #{insights_count + 1} data from API (account {account_id}):")
                log_message(f"   ad_id: {insight.get('ad_id')}")
                log_message(f"   ALL KEYS: {list(insight.keys())}")
                log_message(f"   spend: {insight.get('spend')}")
                log_message(f"   cost_per_result (raw): {insight.get('cost_per_result')}")
                log_message(f"   results (raw): {insight.get('results')}")
                log_message(f"   cost_per_result type: {type(insight.get('cost_per_result'))}")
                log_message(f"   actions: {insight.get('actions')}")
                log_message(f"   cost_per_action_type: {insight.get('cost_per_action_type')}")
            
            # 🔧 ปรับปรุง cost_per_result parsing logic
            cost_per_result = 0.0
            actions_data = insight.get("actions", [])
            cost_per_action_data = insight.get("cost_per_action_type", [])
            cost_per_result_raw = insight.get("cost_per_result", [])
            
            # Method 1: ลองดึงจาก cost_per_result array (Primary method)
            if cost_per_result_raw:
                try:
                    if isinstance(cost_per_result_raw, list) and len(cost_per_result_raw) > 0:
                        first_result = cost_per_result_raw[0]
                        if isinstance(first_result, dict):
                            if 'values' in first_result and len(first_result['values']) > 0:
                                cost_per_result = safe_float_convert(first_result['values'][0].get('value'))
                            elif 'value' in first_result:
                                cost_per_result = safe_float_convert(first_result.get('value'))
                    elif isinstance(cost_per_result_raw, dict):
                        # Sometimes API returns dict instead of array
                        if 'value' in cost_per_result_raw:
                            cost_per_result = safe_float_convert(cost_per_result_raw.get('value'))
                    elif isinstance(cost_per_result_raw, (int, float, str)):
                        # Sometimes API returns direct value
                        cost_per_result = safe_float_convert(cost_per_result_raw)
                        
                    if cost_per_result > 0 and insights_count < 3:
                        log_message(f"   ✅ Got cost_per_result from cost_per_result field: {cost_per_result}")
                except Exception as e:
                    if insights_count < 3:
                        log_message(f"   ⚠️ Error parsing cost_per_result: {e}")
            
            # Method 2: ถ้ายังไม่ได้ค่า ลองดึงจาก cost_per_action_type (Fallback method)
            if cost_per_result == 0.0 and cost_per_action_data:
                # ลอง prioritize conversion actions ต่าง ๆ ตาม campaign objective
                priority_actions = [
                    'offsite_conversion.fb_pixel_purchase',
                    'offsite_conversion.fb_pixel_lead',
                    'offsite_conversion.fb_pixel_complete_registration',
                    'offsite_conversion',
                    'onsite_conversion.purchase',
                    'onsite_conversion.lead',
                    'onsite_conversion',
                    'link_click',
                    'post_engagement', 
                    'page_engagement',
                    'video_view',
                    'post_interaction_gross',
                    'post'
                ]
                
                selected_action_type = None
                for action_type in priority_actions:
                    matching_action = next((a for a in cost_per_action_data if a.get('action_type') == action_type), None)
                    if matching_action and matching_action.get('value'):
                        cost_per_result = safe_float_convert(matching_action.get('value'))
                        selected_action_type = action_type
                        break
                
                # ถ้ายังหาไม่เจอ ใช้ตัวแรกที่มีค่า
                if cost_per_result == 0.0 and len(cost_per_action_data) > 0:
                    for action in cost_per_action_data:
                        if action.get('value'):
                            cost_per_result = safe_float_convert(action.get('value'))
                            selected_action_type = action.get('action_type')
                            break
                
                if insights_count < 3 and selected_action_type:
                    log_message(f"   ✅ Got cost_per_result from cost_per_action_type ({selected_action_type}): {cost_per_result}")
            
            # Method 3: Ultimate fallback - calculate from spend/conversions
            if cost_per_result == 0.0:
                spend = safe_float_convert(insight.get("spend", 0))
                # Try to find any conversion action count
                conversion_count = 0
                for action in actions_data:
                    action_type = action.get('action_type', '')
                    if any(conv in action_type for conv in ['conversion', 'purchase', 'lead', 'complete_registration']):
                        conversion_count += safe_float_convert(action.get('value', 0))
                        break
                
                if conversion_count > 0 and spend > 0:
                    cost_per_result = spend / conversion_count
                    if insights_count < 3:
                        log_message(f"   ✅ Calculated cost_per_result (spend/conversions): {cost_per_result}")
                elif insights_count < 3:
                    log_message(f"   ⚠️ Cannot calculate cost_per_result: spend={spend}, conversions={conversion_count}")
            
            # Extract post_saves จาก actions
            post_saves_count = extract_post_saves(actions_data)
            
            # 🔍 DEBUG: Show all action_types for troubleshooting (first 3 records only)
            if insights_count < 3:
                if actions_data:
                    action_types = [a.get('action_type') for a in actions_data if isinstance(a, dict)]
                    log_message(f"   🔍 All action_types in actions: {action_types}")
                    
                    # Show save-related actions specifically
                    save_actions = [a for a in actions_data if isinstance(a, dict) and 'save' in a.get('action_type', '').lower()]
                    if save_actions:
                        log_message(f"   💾 Save-related actions found:")
                        for action in save_actions:
                            log_message(f"      - {action.get('action_type')}: {action.get('value')}")
                
                if post_saves_count > 0:
                    log_message(f"   ✅ Final post_saves count: {post_saves_count}")
            
            # Parse results field from API response
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
            
            # Clean and validate data with safe conversion
            insight_data = {
                "ad_id": insight.get("ad_id"),
                "adset_id": insight.get("adset_id"),
                "campaign_id": insight.get("campaign_id"),
                "account_id": account_id,
                "impressions": safe_int_convert(insight.get("impressions")),
                "reach": safe_int_convert(insight.get("reach")),
                "clicks": safe_int_convert(insight.get("clicks")),
                "spend": safe_float_convert(insight.get("spend")),
                "cpm": safe_float_convert(insight.get("cpm")),
                "cpp": safe_float_convert(insight.get("cpp")),
                "ctr": safe_float_convert(insight.get("ctr")),
                "frequency": safe_float_convert(insight.get("frequency")),
                "cost_per_result": cost_per_result,  # ✅ ใช้ค่าที่คำนวณจาก cost_per_action_type
                "results": results_value,  # ✅ เพิ่ม results จาก API
                "results_indicator": results_indicator,  # ✅ เพิ่ม results_indicator
                "actions": json.dumps(actions_data) if actions_data else None,
                "post_saves": post_saves_count,  # ✅ เพิ่ม post_saves
                "action_values": None,  # ไม่ใช้แล้ว
                "video_actions": None,  # ไม่รองรับแล้ว
                "date_start": insight.get("date_start"),
                "date_stop": insight.get("date_stop")
            }
            
            if insight_data["ad_id"] and insight_data["date_start"] and insight_data["date_stop"]:
                # 🔧 เรียกใช้ insert_ad_insight และตรวจสอบผลลัพธ์
                result = insert_ad_insight(conn, insight_data)
                if result["success"]:
                    if result["action"] == "inserted":
                        insights_count += 1
                    elif result["action"] == "updated":
                        updated_count += 1
                else:
                    skipped_count += 1
                
                # 🔍 Debug: แสดงผลลัพธ์ที่จะ upsert (แสดงแค่ 3 records แรก)
                processed_count = insights_count + updated_count
                if processed_count <= 3:
                    action_emoji = "➕" if result["action"] == "inserted" else "🔄" if result["action"] == "updated" else "⚠️"
                    log_message(f"🔍 DEBUG #{processed_count} - {action_emoji} {result['action'].title()} insight data:")
                    log_message(f"   ad_id: {insight_data['ad_id']}")
                    log_message(f"   spend: ${insight_data['spend']}")
                    log_message(f"   cost_per_result: ${insight_data['cost_per_result']}")
                    log_message(f"   date: {insight_data['date_start']} to {insight_data['date_stop']}")
                
        except Exception as e:
            log_message(f"❌ Error processing insight: {e}")
            log_message(f"   Insight data: {insight}")
            continue
    
    total_processed = insights_count + updated_count
    log_message(f"✅ Processed {total_processed} insights records:")
    log_message(f"   ➕ New records inserted: {insights_count}")
    log_message(f"   🔄 Existing records updated: {updated_count}")
    if skipped_count > 0:
        log_message(f"   ⚠️ Skipped records: {skipped_count} (ads not found in database)")
    return total_processed

def main():
    """Main sync function"""
    # Setup argument parser
    parser = argparse.ArgumentParser(description='Sync Facebook ads insights to database')
    parser.add_argument('--days-back', type=int, default=7, help='Number of days back to fetch data (default: 7)')
    args = parser.parse_args()
    
    log_message(f"🚀 Starting Facebook Ads and Insights sync for last {args.days_back} days...")
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASSWORD
        )
        conn.autocommit = True
        log_message("✅ Database connection established")
        
        # 🔥 สำคัญ: ต้องสร้าง ad accounts ก่อน!
        sync_ad_accounts(conn)
        
        total_campaigns = 0
        total_ads = 0
        total_insights = 0
        
        # Define time range for insights (using --days-back argument)
        time_range = get_date_ranges(args.days_back)
        log_message(f"📅 Fetching insights from {time_range['since']} to {time_range['until']}")
        
        for account_id in COMPANY_AD_ACCOUNT_IDS:
            log_message(f"\n🏢 Processing account: {account_id}")
            
            try:
                # 1. Sync campaigns
                campaigns = sync_campaigns(conn, account_id)
                total_campaigns += len(campaigns)
                
                # 2. Sync ads
                ads = sync_ads(conn, account_id)
                total_ads += len(ads)
                
                # 3. Sync insights (this is the most important part)
                insights_count = sync_insights(conn, account_id, time_range)
                total_insights += insights_count
                
                log_message(f"✅ Account {account_id} completed successfully")
                
            except Exception as e:
                log_message(f"❌ Error processing account {account_id}: {e}")
                continue
        
        # Summary
        log_message(f"\n🎉 Sync completed successfully!")
        log_message(f"📊 Summary:")
        log_message(f"   - Campaigns: {total_campaigns}")
        log_message(f"   - Ads: {total_ads}")
        log_message(f"   - Insights: {total_insights}")
        
        # Verify data in database
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM facebook_ads_insights")
            insights_in_db = cur.fetchone()[0]
            log_message(f"   - Total insights in DB: {insights_in_db}")
        
        conn.close()
        
    except Exception as e:
        log_message(f"❌ Fatal error: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    if success:
        log_message("✅ Script completed successfully")
    else:
        log_message("❌ Script failed")
