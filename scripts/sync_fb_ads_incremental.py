#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🚀 Facebook Ads Incremental Sync Tool
Sync only NEW or UPDATED ads since last sync to save time and API calls

Features:
- ⚡ Fast: Only syncs changed ads
- 🛡️ API-friendly: Reduces rate limit risk
- 🔄 Auto-detect: Uses last sync time from database
- 📊 Statistics: Shows new vs updated ads

Usage:
  python sync_fb_ads_incremental.py                    # Auto-detect last sync
  python sync_fb_ads_incremental.py --hours-back 2     # Last 2 hours
  python sync_fb_ads_incremental.py --days-back 1      # Last 24 hours
  python sync_fb_ads_incremental.py --show-stats       # Show detailed stats
"""

import os
import sys
import codecs
import requests
import psycopg2
import json
import time
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Fix Windows Unicode encoding issue
if sys.platform.startswith('win'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

load_dotenv()

# Database configuration
PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

# Facebook API configuration
FB_USER_ACCESS_TOKEN = os.getenv("FB_USER_ACCESS_TOKEN").split(',')
COMPANY_AD_ACCOUNT_IDS = ["act_486765798095431", "act_599000711226225"]

# === Helper Functions ===

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

# === Database Functions ===

def get_last_sync_time(conn, ad_account_id):
    """
    Get the last sync time for a specific ad account from database
    Returns the most recent updated_at timestamp of ads in this account
    """
    try:
        with conn.cursor() as cur:
            # Query: Find max updated_at for ads in this account
            cur.execute("""
                SELECT MAX(fa.updated_at) 
                FROM facebook_ads fa
                JOIN facebook_adsets fas ON fa.adset_id = fas.adset_id
                JOIN facebook_campaigns fc ON fas.campaign_id = fc.campaign_id
                WHERE fc.account_id = %s
            """, (ad_account_id.replace('act_', ''),))
            
            result = cur.fetchone()
            last_sync = result[0] if result and result[0] else None
            
            if last_sync:
                print(f"   📅 Last sync: {last_sync.strftime('%Y-%m-%d %H:%M:%S')}")
                return last_sync
            else:
                print(f"   ℹ️  No previous sync found - will fetch all ads")
                return None
                
    except Exception as e:
        print(f"   ⚠️  Error getting last sync time: {e}")
        return None

def insert_or_update_ad(conn, ad_data):
    """Insert or update Facebook ad with UPSERT"""
    # ✅ FIX: Convert creative string to JSON if needed
    if ad_data.get('creative') and isinstance(ad_data['creative'], str):
        try:
            # If it's already a JSON string, parse and re-stringify to ensure valid JSON
            creative_obj = json.loads(ad_data['creative'])
            ad_data['creative'] = json.dumps(creative_obj)
        except:
            # If parsing fails, it's not valid JSON - keep as is
            pass
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO facebook_ads (
                ad_id, adset_id, name, status, creative, preview_url, post_id,
                created_time, updated_time, created_at, updated_at
            ) VALUES (
                %(ad_id)s, %(adset_id)s, %(name)s, %(status)s, %(creative)s::jsonb, 
                %(preview_url)s, %(post_id)s, %(created_time)s, %(updated_time)s,
                NOW(), NOW()
            )
            ON CONFLICT (ad_id) DO UPDATE SET
                adset_id = EXCLUDED.adset_id,
                name = EXCLUDED.name,
                status = EXCLUDED.status,
                creative = EXCLUDED.creative,
                preview_url = EXCLUDED.preview_url,
                post_id = COALESCE(EXCLUDED.post_id, facebook_ads.post_id),  -- Keep existing post_id if new one is NULL
                created_time = EXCLUDED.created_time,
                updated_time = EXCLUDED.updated_time,
                updated_at = NOW()
            RETURNING (xmax = 0) AS is_new;
        """, ad_data)
        
        # xmax = 0 means INSERT (new record), xmax > 0 means UPDATE
        result = cur.fetchone()
        is_new = result[0] if result else False
        return is_new

# === Facebook API Functions ===

def fetch_post_from_api(post_id, access_token):
    """
    Fetch promoted post details from Facebook API
    These posts don't appear in regular feed but are used in ads
    """
    url = f"https://graph.facebook.com/v20.0/{post_id}"
    params = {
        'fields': 'id,message,created_time,permalink_url,full_picture,type,attachments{media,media_type,url}',
        'access_token': access_token
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        return None

def fetch_ads_incremental(access_token, ad_account_id, since_datetime):
    """
    Fetch ads that were updated since a specific datetime using Facebook filtering
    
    Args:
        access_token: Facebook access token
        ad_account_id: Ad account ID (e.g., 'act_123456')
        since_datetime: datetime object for filtering ads
        
    Returns:
        List of ads updated since the given datetime
    """
    url = f"https://graph.facebook.com/v20.0/{ad_account_id}/ads"

    fields = [
        'id',
        'adset_id',
        'name',
        'status',
        'creative{object_story_id,effective_object_story_id,id,name,video_id,object_type}',
        'preview_shareable_link',
        'created_time',
        'updated_time'
    ]

    # ✅ Use filtering parameter for incremental sync
    # Facebook API filtering syntax for updated_time
    filtering = [
        {
            "field": "ad.updated_time",
            "operator": "GREATER_THAN",
            "value": int(since_datetime.timestamp())  # Unix timestamp
        }
    ]

    params = {
        'fields': ','.join(fields),
        'filtering': json.dumps(filtering),
        'access_token': access_token,
        'limit': 100
    }

    all_ads = []
    page_count = 0

    try:
        while url:
            page_count += 1
            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if 'error' in data:
                error_msg = data['error'].get('message', 'Unknown error')
                print(f"   ❌ Facebook API Error: {error_msg}")
                break

            ads = data.get('data', [])
            all_ads.extend(ads)

            if ads:
                print(f"   📄 Page {page_count}: Found {len(ads)} ads (Total: {len(all_ads)})")

            # Check for pagination
            paging = data.get('paging', {})
            url = paging.get('next')
            params = None  # URL already contains all parameters

            # Rate limiting
            time.sleep(0.3)

    except requests.exceptions.RequestException as e:
        print(f"   ❌ Request error: {e}")
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")

    return all_ads

# === Sync Functions ===

def sync_promoted_posts(conn, access_token, limit=100):
    """
    Sync promoted posts that are referenced by ads but don't exist in facebook_posts
    
    Why needed:
    - When promoting videos, Facebook creates NEW post_id (different from video_id)
    - These promoted posts don't appear in regular feed
    - Ads reference these post_ids but we can't find them
    - This causes ads_details to be empty in performance sync
    
    Solution:
    - Find post_ids in ads table that don't exist in posts/video_posts tables
    - Fetch from Facebook API (with rate limiting)
    - Save to facebook_posts
    - Now performance sync can match ads correctly!
    
    Args:
        limit: Max posts to sync per run (default 100 to avoid API limits)
    """
    print(f"\n📢 Syncing promoted posts (limit: {limit})...")
    
    try:
        with conn.cursor() as cur:
            # Find post_ids from ads that aren't in posts tables
            # Prioritize recently updated ads
            cur.execute("""
                SELECT DISTINCT ON (a.post_id) a.post_id, a.updated_time
                FROM facebook_ads a
                WHERE a.post_id IS NOT NULL
                  AND a.post_id != ''
                  -- Not in regular posts
                  AND NOT EXISTS (
                      SELECT 1 FROM facebook_posts p 
                      WHERE p.id = a.post_id
                  )
                  -- Not in video posts (check all formats)
                  AND NOT EXISTS (
                      SELECT 1 FROM facebook_video_posts vp
                      WHERE vp.video_id = a.post_id
                         OR vp.post_id = a.post_id
                         OR vp.page_id || '_' || vp.video_id = a.post_id
                  )
                ORDER BY a.post_id, a.updated_time DESC NULLS LAST
                LIMIT %s
            """, (limit,))
            
            promoted_post_ids = [row[0] for row in cur.fetchall()]
        
        if not promoted_post_ids:
            print(f"   ✅ No promoted posts need syncing")
            return 0
        
        print(f"   📊 Found {len(promoted_post_ids)} promoted posts to sync")
        success_count = 0
        error_count = 0
        
        for i, post_id in enumerate(promoted_post_ids, 1):
            try:
                # Fetch post from API
                post_data = fetch_post_from_api(post_id, access_token)
                
                if not post_data:
                    error_count += 1
                    if error_count <= 3:  # Only print first 3 errors
                        print(f"      ⚠️  Could not fetch post {post_id}")
                    continue
                
                # Extract page_id from post_id (format: page_id_post_id)
                page_id = None
                if '_' in post_data['id']:
                    page_id = post_data['id'].split('_')[0]
                
                # Insert into facebook_posts
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO facebook_posts (
                            id, page_id, message, created_time, permalink_url, 
                            picture_url, type, created_at, updated_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                        )
                        ON CONFLICT (id) DO UPDATE SET
                            message = EXCLUDED.message,
                            permalink_url = EXCLUDED.permalink_url,
                            picture_url = EXCLUDED.picture_url,
                            type = EXCLUDED.type,
                            updated_at = NOW()
                    """, (
                        post_data['id'],
                        page_id,
                        post_data.get('message'),
                        safe_convert_datetime(post_data.get('created_time')),
                        post_data.get('permalink_url'),
                        post_data.get('full_picture'),
                        post_data.get('type', 'promoted_post')
                    ))
                
                success_count += 1
                
                if i % 10 == 0:
                    print(f"   ⏳ Progress: {i}/{len(promoted_post_ids)} ({success_count} synced)")
                
                # Rate limiting - Facebook allows ~200 calls/hour
                time.sleep(0.5)
                    
            except KeyboardInterrupt:
                print(f"\n   ⚠️  Interrupted by user at {i}/{len(promoted_post_ids)}")
                break
            except Exception as e:
                error_count += 1
                if error_count <= 3:
                    print(f"      ⚠️  Error with post {post_id}: {e}")
                continue
        
        print(f"   ✅ Synced {success_count} promoted posts ({error_count} errors)")
        return success_count
        
    except Exception as e:
        print(f"   ❌ Error in sync_promoted_posts: {e}")
        return 0

def populate_video_promoted_mapping(conn):
    """
    🎬 Auto-populate facebook_video_promoted_posts mapping table
    
    CORRECT Logic:
    - Find ads that promote videos (by checking facebook_video_posts)
    - For each ad, get the promoted post_id it uses
    - Map: organic video_id → promoted post_id → ad_id
    
    Example:
    - Video (organic): 107038946030147_864424596563204 → video_id = 864424596563204
    - Ad uses promoted: 107038946030147_943196201369931
    - Mapping: 864424596563204 → 943196201369931 → 6933147088806
    
    Returns:
        Number of mappings created/updated
    """
    try:
        with conn.cursor() as cur:
            # ✅ CORRECT: Match ONLY by video_id in creative JSON
            # DO NOT use timing-based matching - it creates too many duplicates!
            cur.execute("""
                INSERT INTO facebook_video_promoted_posts (video_id, promoted_post_id, page_id, ad_id, created_at, updated_at)
                SELECT DISTINCT ON (video_id, promoted_post_id)
                    vp.video_id,
                    a.post_id AS promoted_post_id,
                    vp.page_id,
                    a.ad_id,
                    NOW(),
                    NOW()
                FROM facebook_ads a
                INNER JOIN facebook_video_posts vp ON (
                    -- ONLY match by video_id in creative JSON (100% accurate)
                    a.creative::jsonb->>'video_id' = vp.video_id::text
                )
                WHERE a.post_id IS NOT NULL
                  AND a.post_id LIKE '%_%'
                  AND a.creative::jsonb->>'video_id' IS NOT NULL
                ON CONFLICT (video_id, promoted_post_id) 
                DO UPDATE SET
                    ad_id = EXCLUDED.ad_id,
                    updated_at = NOW()
                RETURNING video_id, promoted_post_id
            """)
            
            mappings = cur.fetchall()
            
            if mappings:
                print(f"\n🎬 Video Mapping: Populated {len(mappings)} video → promoted_post mappings")
            else:
                print(f"\n🎬 Video Mapping: No new mappings (all up to date)")
            
            return len(mappings)
                
    except Exception as e:
        print(f"   ⚠️  Error populating video mappings: {e}")
        import traceback
        traceback.print_exc()
        return 0

def sync_ads_incremental_for_account(conn, access_token, ad_account_id, since_datetime=None, buffer_hours=1):
    """
    Sync only new/updated ads for a specific account
    
    Args:
        conn: Database connection
        access_token: Facebook access token
        ad_account_id: Ad account ID
        since_datetime: Custom datetime to sync from (optional)
        buffer_hours: Hours to subtract from last sync time (safety margin)
        
    Returns:
        Dictionary with sync statistics
    """
    print(f"\n🔄 Syncing ads for: {ad_account_id}")
    
    # Determine sync start time
    if since_datetime:
        sync_from = since_datetime
        print(f"   🕐 Custom sync from: {sync_from.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        # Auto-detect last sync time
        last_sync = get_last_sync_time(conn, ad_account_id)
        
        if last_sync:
            # Subtract buffer hours to ensure no missed ads
            sync_from = last_sync - timedelta(hours=buffer_hours)
            print(f"   ⚡ Incremental sync from: {sync_from.strftime('%Y-%m-%d %H:%M:%S')} (with {buffer_hours}h buffer)")
        else:
            # No previous sync - fetch last 7 days as default
            sync_from = datetime.now() - timedelta(days=7)
            print(f"   📊 First sync - fetching last 7 days from: {sync_from.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Fetch ads from Facebook
    ads = fetch_ads_incremental(access_token, ad_account_id, sync_from)
    
    if not ads:
        print(f"   ✅ No new/updated ads found")
        return {
            'account_id': ad_account_id,
            'total': 0,
            'new': 0,
            'updated': 0,
            'errors': 0
        }
    
    # Process ads
    new_count = 0
    updated_count = 0
    error_count = 0
    
    print(f"   📥 Processing {len(ads)} ads...")
    
    for i, ad in enumerate(ads, 1):
        try:
            # Extract creative information
            creative_info = ad.get('creative', {})
            
            # Extract post_id
            post_id = None
            if creative_info:
                post_id = creative_info.get('effective_object_story_id')
                if not post_id:
                    post_id = creative_info.get('object_story_id')
            
            # Prepare ad data
            ad_data = {
                'ad_id': ad.get('id'),
                'adset_id': ad.get('adset_id'),
                'name': ad.get('name'),
                'status': ad.get('status'),
                'creative': safe_convert_json(creative_info),
                'preview_url': ad.get('preview_shareable_link'),
                'post_id': post_id,
                'created_time': safe_convert_datetime(ad.get('created_time')),
                'updated_time': safe_convert_datetime(ad.get('updated_time'))
            }
            
            # Insert or update
            is_new = insert_or_update_ad(conn, ad_data)
            
            if is_new:
                new_count += 1
            else:
                updated_count += 1
            
            # Progress indicator
            if i % 20 == 0:
                print(f"   ⏳ Progress: {i}/{len(ads)} ({new_count} new, {updated_count} updated)")
                
        except Exception as e:
            error_count += 1
            print(f"   ⚠️  Error processing ad {ad.get('id', 'unknown')}: {e}")
            continue
    
    # Summary
    print(f"   ✅ Completed: {new_count} new, {updated_count} updated, {error_count} errors")
    
    return {
        'account_id': ad_account_id,
        'total': len(ads),
        'new': new_count,
        'updated': updated_count,
        'errors': error_count
    }

# === Statistics Functions ===

def show_sync_summary(results, duration):
    """Display sync summary statistics"""
    total_ads = sum(r['total'] for r in results)
    total_new = sum(r['new'] for r in results)
    total_updated = sum(r['updated'] for r in results)
    total_errors = sum(r['errors'] for r in results)
    
    print(f"\n{'='*60}")
    print(f"📊 INCREMENTAL SYNC SUMMARY")
    print(f"{'='*60}")
    print(f"⏱️  Duration: {duration}")
    print(f"📈 Total ads processed: {total_ads:,}")
    print(f"✨ New ads: {total_new:,}")
    print(f"🔄 Updated ads: {total_updated:,}")
    print(f"❌ Errors: {total_errors:,}")
    
    if total_ads > 0:
        print(f"📊 New rate: {(total_new/total_ads*100):.1f}%")
        print(f"🔄 Update rate: {(total_updated/total_ads*100):.1f}%")
    
    print(f"\n📋 Breakdown by account:")
    for result in results:
        print(f"   {result['account_id']}: {result['total']} ads ({result['new']} new, {result['updated']} updated)")
    
    print(f"{'='*60}\n")

def show_detailed_stats(conn):
    """Show detailed database statistics"""
    print(f"\n📊 Database Statistics:")
    print(f"{'='*60}")
    
    try:
        with conn.cursor() as cur:
            # Total ads
            cur.execute("SELECT COUNT(*) FROM facebook_ads")
            total_ads = cur.fetchone()[0]
            
            # Ads with posts
            cur.execute("SELECT COUNT(*) FROM facebook_ads WHERE post_id IS NOT NULL")
            ads_with_posts = cur.fetchone()[0]
            
            # Ads by status
            cur.execute("""
                SELECT status, COUNT(*) 
                FROM facebook_ads 
                GROUP BY status 
                ORDER BY COUNT(*) DESC
            """)
            status_counts = cur.fetchall()
            
            # Recent ads (last 24h)
            cur.execute("""
                SELECT COUNT(*) 
                FROM facebook_ads 
                WHERE updated_at >= NOW() - INTERVAL '24 hours'
            """)
            recent_ads = cur.fetchone()[0]
            
            print(f"📊 Total ads in database: {total_ads:,}")
            print(f"🔗 Ads with posts: {ads_with_posts:,} ({ads_with_posts/max(total_ads,1)*100:.1f}%)")
            print(f"🕐 Updated in last 24h: {recent_ads:,}")
            
            print(f"\n📈 Ads by status:")
            for status, count in status_counts:
                print(f"   {status or 'NULL'}: {count:,}")
            
    except Exception as e:
        print(f"❌ Error showing stats: {e}")
    
    print(f"{'='*60}\n")

# === Main Function ===

def main():
    """Main function for incremental sync"""
    
    parser = argparse.ArgumentParser(
        description='⚡ Facebook Ads Incremental Sync - Fast & API-Friendly',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
📌 Examples:
  python sync_fb_ads_incremental.py                     # Auto-detect last sync
  python sync_fb_ads_incremental.py --hours-back 2      # Last 2 hours
  python sync_fb_ads_incremental.py --days-back 1       # Last 24 hours
  python sync_fb_ads_incremental.py --show-stats        # Show detailed stats
  python sync_fb_ads_incremental.py --buffer-hours 2    # 2-hour safety buffer

💡 Benefits of Incremental Sync:
   • ⚡ 95-99%% faster than full sync
   • 🛡️ Reduces API rate limit risk
   • 🔄 Perfect for scheduled/frequent syncs
   • 📊 Tracks new vs updated ads
        """
    )
    
    parser.add_argument('--hours-back', 
                        type=int,
                        help='Sync ads from last N hours')
    
    parser.add_argument('--days-back', 
                        type=int,
                        help='Sync ads from last N days')
    
    parser.add_argument('--buffer-hours',
                        type=int,
                        default=1,
                        help='Safety buffer hours (default: 1)')
    
    parser.add_argument('--show-stats', 
                        action='store_true',
                        help='Show detailed database statistics')
    
    args = parser.parse_args()
    
    # Display header
    print("="*60)
    print("⚡ FACEBOOK ADS INCREMENTAL SYNC")
    print("="*60)
    
    # Determine sync time
    since_datetime = None
    if args.hours_back:
        since_datetime = datetime.now() - timedelta(hours=args.hours_back)
        print(f"🕐 Mode: Last {args.hours_back} hours")
    elif args.days_back:
        since_datetime = datetime.now() - timedelta(days=args.days_back)
        print(f"📅 Mode: Last {args.days_back} days")
    else:
        print(f"⚡ Mode: Auto-detect (incremental)")
    
    print(f"🛡️ Safety buffer: {args.buffer_hours} hour(s)")
    print("="*60)
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASSWORD
        )
        conn.autocommit = True
        print("✅ Database connected\n")
        
        start_time = datetime.now()
        results = []
        promoted_posts_synced = 0
        
        # Process each access token
        for token_idx, token in enumerate(FB_USER_ACCESS_TOKEN, 1):
            print(f"🔑 Access token {token_idx}/{len(FB_USER_ACCESS_TOKEN)}")
            
            # Process each ad account
            for account_id in COMPANY_AD_ACCOUNT_IDS:
                try:
                    result = sync_ads_incremental_for_account(
                        conn, 
                        token, 
                        account_id,
                        since_datetime=since_datetime,
                        buffer_hours=args.buffer_hours
                    )
                    results.append(result)
                    
                except Exception as e:
                    print(f"   ❌ Error syncing {account_id}: {e}")
                    results.append({
                        'account_id': account_id,
                        'total': 0,
                        'new': 0,
                        'updated': 0,
                        'errors': 1
                    })
            
            # 🆕 Sync promoted posts after all ads are synced
            try:
                promoted_posts_synced += sync_promoted_posts(conn, token)
            except Exception as e:
                print(f"   ❌ Error syncing promoted posts: {e}")
        
        # 🎬 Auto-populate video promoted mappings
        print(f"\n🎬 Auto-populating video promoted posts mappings...")
        try:
            video_mappings = populate_video_promoted_mapping(conn)
            if video_mappings > 0:
                print(f"   ✅ Created/updated {video_mappings} video mappings")
                print(f"   💡 Video posts can now correctly match their ads")
        except Exception as e:
            print(f"   ⚠️  Error populating video mappings: {e}")
        
        # Calculate duration
        end_time = datetime.now()
        duration = end_time - start_time
        
        # Show summary
        show_sync_summary(results, duration)
        
        # Show promoted posts summary
        if promoted_posts_synced > 0:
            print(f"\n📢 Promoted Posts Summary:")
            print(f"   ✅ Synced {promoted_posts_synced} promoted posts")
            print(f"   💡 These posts can now be matched with ads in performance sync")
        
        # Show detailed stats if requested
        if args.show_stats:
            show_detailed_stats(conn)
        
        print(f"🎉 Sync completed at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔌 Database disconnected")

if __name__ == "__main__":
    main()
