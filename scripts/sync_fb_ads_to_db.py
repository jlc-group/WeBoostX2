import os
import requests
import psycopg2
import json
import time
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

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

def safe_convert_datetime(value):
    """Safely convert datetime string to timestamp"""
    if not value:
        return None
    try:
        # Facebook API returns ISO 8601 format
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

def fetch_post_from_api(post_id, access_token):
    """
    Fetch promoted post details from Facebook API
    These posts don't appear in regular feed but are used in ads
    """
    url = f"https://graph.facebook.com/v22.0/{post_id}"
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

def fetch_creative_details(creative_id, access_token):
    """Fetch creative details separately for better post_id extraction reliability"""
    if not creative_id:
        return {}
    
    try:
        url = f"https://graph.facebook.com/v22.0/{creative_id}"
        params = {
            'fields': 'object_story_id,effective_object_story_id,name,title,object_id',
            'access_token': access_token
        }
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"      ⚠️  Failed to fetch creative {creative_id}: HTTP {response.status_code}")
            return {}
            
    except Exception as e:
        print(f"      ⚠️  Error fetching creative {creative_id}: {e}")
        return {}

def insert_or_update_ad(conn, ad_data):
    """Insert or update Facebook ad with UPSERT"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO facebook_ads (
                ad_id, adset_id, name, status, creative, preview_url, post_id,
                created_time, updated_time, created_at, updated_at
            ) VALUES (
                %(ad_id)s, %(adset_id)s, %(name)s, %(status)s, %(creative)s, 
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
                updated_at = NOW();
        """, ad_data)

def fetch_ads_from_account(access_token, ad_account_id):
    """Fetch ALL ads from a specific Facebook ad account (API doesn't support date filtering)"""
    url = f"https://graph.facebook.com/v22.0/{ad_account_id}/ads"

    # Facebook API fields for ads - Request creative ID only, then fetch details separately
    # Note: creative{...} nested fields often fail to return, better to fetch separately
    fields = [
        'id',                    # Ad ID
        'adset_id',              # Ad Set ID
        'name',                  # Ad name
        'status',                # Ad status (ACTIVE, PAUSED, etc.)
        'creative',              # Just get creative ID, will fetch details separately
        'preview_shareable_link', # Preview URL
        'created_time',          # Creation time
        'updated_time'           # Last update time
    ]

    params = {
        'fields': ','.join(fields),
        'access_token': access_token,
        'limit': 100  # Fetch 100 ads per request
    }

    all_ads = []

    try:
        page_num = 0
        while url:
            page_num += 1
            response = requests.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            if 'error' in data:
                print(f"❌ Facebook API Error: {data['error']}")
                break

            ads = data.get('data', [])
            all_ads.extend(ads)
            
            if page_num % 5 == 0:  # Report every 5 pages
                print(f"  📄 Fetched {len(all_ads):,} ads so far...")

            # Check for pagination
            paging = data.get('paging', {})
            url = paging.get('next')
            params = None  # URL already contains all parameters

            # Rate limiting - Facebook allows 200 calls per hour per user
            time.sleep(0.5)  # Wait 0.5 seconds between requests

    except requests.exceptions.RequestException as e:
        print(f"❌ Request error for {ad_account_id}: {e}")
    except Exception as e:
        print(f"❌ Unexpected error for {ad_account_id}: {e}")

    print(f"\n✅ Total ads fetched: {len(all_ads):,}")
    return all_ads

def sync_promoted_posts(conn, access_token, limit=100):
    """
    Sync promoted posts that are referenced by ads but don't exist in facebook_posts
    
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
                    if error_count <= 3:
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
                
                # Rate limiting
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

def sync_ads_for_account(conn, access_token, ad_account_id):
    """Sync all ads for a specific ad account with enhanced creative fetching"""
    print(f"\n🔄 Syncing ads for account: {ad_account_id}")
    
    ads = fetch_ads_from_account(access_token, ad_account_id)
    
    if not ads:
        print(f"No ads found for account {ad_account_id}")
        return 0
    
    synced_count = 0
    fetched_creatives_count = 0
    
    for ad in ads:
        try:
            # Extract creative information
            creative_info = ad.get('creative', {})
            post_id = None
            
            # If creative is just an ID (string), fetch full details
            if isinstance(creative_info, str):
                creative_id = creative_info
                creative_details = fetch_creative_details(creative_id, access_token)
                if creative_details:
                    # Merge creative ID with fetched details
                    creative_info = {'id': creative_id, **creative_details}
                    post_id = creative_details.get('effective_object_story_id') or creative_details.get('object_story_id')
                    fetched_creatives_count += 1
                else:
                    creative_info = {'id': creative_id}
            
            # If creative is dict but missing post_id fields, fetch details
            elif isinstance(creative_info, dict):
                creative_id = creative_info.get('id')
                post_id = creative_info.get('effective_object_story_id') or creative_info.get('object_story_id')
                
                # Fetch details if we have ID but no post_id
                if creative_id and not post_id:
                    creative_details = fetch_creative_details(creative_id, access_token)
                    if creative_details:
                        creative_info.update(creative_details)
                        post_id = creative_details.get('effective_object_story_id') or creative_details.get('object_story_id')
                        fetched_creatives_count += 1
            
            # Prepare ad data for database
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
            
            insert_or_update_ad(conn, ad_data)
            synced_count += 1
            
            # Progress with creative fetch count
            if synced_count % 100 == 0:
                print(f"  ✓ Synced {synced_count}/{len(ads)} ads ({fetched_creatives_count} creatives fetched separately)...")
                
        except Exception as e:
            print(f"Error processing ad {ad.get('id', 'unknown')}: {e}")
            continue
    
    # Final stats
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM facebook_ads WHERE ad_id IN %s AND post_id IS NOT NULL",
                   (tuple(ad.get('id') for ad in ads),))
        ads_with_posts_count = cur.fetchone()[0]
    
    print(f"✅ Completed syncing {synced_count} ads for {ad_account_id}")
    print(f"   🔍 Fetched {fetched_creatives_count} creative details separately")
    print(f"   🔗 Ads with post_id: {ads_with_posts_count}/{len(ads)} ({ads_with_posts_count/max(len(ads),1)*100:.1f}%)")
    
    # Add rate limiting after batch
    time.sleep(1)
    
    return synced_count

def main():
    """Main function to sync Facebook ads to database with enhanced post_id tracking"""
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='🎯 Facebook Ads Sync Tool - Enhanced Post Connection Tracking',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
📌 Examples:
  python sync_fb_ads_to_db.py                    # Sync all ads with post connections
  python sync_fb_ads_to_db.py --show-stats       # Show post-ads connection statistics
  python sync_fb_ads_to_db.py --check-posts      # Check which posts have ads
  
⚠️  Note: Facebook Ads API fetches ALL ads (no date filter available)
        This ensures complete post_id tracking for performance analysis.
        """
    )

    parser.add_argument('--show-stats', 
                        action='store_true', 
                        help='Show post-ads connection statistics after sync')
    
    parser.add_argument('--check-posts', 
                        action='store_true', 
                        help='Show which posts have ads connected')
    
    args = parser.parse_args()
    
    print("🚀 Facebook Ads Sync with Enhanced Post Tracking...")
    print("🔗 Tracking ads-to-posts connections for performance analysis")
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASSWORD
        )
        conn.autocommit = True
        print("✅ Database connection established")
        
        total_synced = 0
        total_with_posts = 0
        promoted_posts_synced = 0
        start_time = datetime.now()
        
        # Process each access token
        for i, token in enumerate(FB_USER_ACCESS_TOKEN, 1):
            print(f"\n📋 Processing access token {i}/{len(FB_USER_ACCESS_TOKEN)}")
            
            # Process each company ad account
            for ad_account_id in COMPANY_AD_ACCOUNT_IDS:
                try:
                    synced = sync_ads_for_account(conn, token, ad_account_id)
                    total_synced += synced
                    
                except Exception as e:
                    print(f"❌ Error syncing {ad_account_id}: {e}")
                    continue
            
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
        
        # Count ads with post connections
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM facebook_ads WHERE post_id IS NOT NULL")
            total_with_posts = cur.fetchone()[0]
        
        # Summary
        end_time = datetime.now()
        duration = end_time - start_time
        
        print(f"\n🎉 Sync Process Completed!")
        print(f"📊 Total ads synced: {total_synced}")
        print(f"🔗 Ads with post connections: {total_with_posts}")
        print(f"📈 Post connection rate: {(total_with_posts/max(total_synced,1)*100):.1f}%")
        
        if promoted_posts_synced > 0:
            print(f"\n📢 Promoted Posts Summary:")
            print(f"   ✅ Synced {promoted_posts_synced} promoted posts")
            print(f"   💡 These posts can now be matched with ads in performance sync")
        
        print(f"⏱️  Duration: {duration}")
        print(f"🏁 Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Show additional statistics if requested
        if args.show_stats or args.check_posts:
            show_post_stats(conn, args.check_posts)
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔌 Database connection closed")

def show_post_stats(conn, show_posts=False):
    """Show post-ads connection statistics"""
    print(f"\n📊 Post-Ads Connection Analysis:")
    print("=" * 50)
    
    try:
        with conn.cursor() as cur:
            # Basic stats
            cur.execute("""
                SELECT 
                    COUNT(*) as total_ads,
                    COUNT(CASE WHEN post_id IS NOT NULL THEN 1 END) as ads_with_posts,
                    COUNT(DISTINCT post_id) as unique_posts_used
                FROM facebook_ads
            """)
            stats = cur.fetchone()
            total_ads, ads_with_posts, unique_posts = stats
            
            print(f"📊 Total Ads: {total_ads:,}")
            print(f"🔗 Ads with Posts: {ads_with_posts:,}")
            print(f"📄 Unique Posts Used: {unique_posts:,}")
            print(f"📈 Connection Rate: {(ads_with_posts/max(total_ads,1)*100):.1f}%")
            
            # Top posts by ad count
            cur.execute("""
                SELECT 
                    post_id,
                    COUNT(*) as ads_count,
                    COUNT(DISTINCT adset_id) as adsets_count
                FROM facebook_ads 
                WHERE post_id IS NOT NULL
                GROUP BY post_id
                ORDER BY ads_count DESC
                LIMIT 10
            """)
            
            top_posts = cur.fetchall()
            if top_posts:
                print(f"\n🏆 Top Posts by Ad Count:")
                print("-" * 30)
                for post_id, ads_count, adsets_count in top_posts:
                    print(f"📄 {post_id}: {ads_count} ads, {adsets_count} adsets")
            
            # Show detailed posts if requested
            if show_posts and unique_posts > 0:
                print(f"\n📋 All Posts with Ads:")
                print("-" * 40)
                cur.execute("""
                    SELECT 
                        fa.post_id,
                        COUNT(fa.ad_id) as ads_count,
                        fp.message,
                        fp.created_time
                    FROM facebook_ads fa
                    LEFT JOIN facebook_posts fp ON fa.post_id = fp.post_id
                    WHERE fa.post_id IS NOT NULL
                    GROUP BY fa.post_id, fp.message, fp.created_time
                    ORDER BY ads_count DESC
                """)
                
                posts_with_ads = cur.fetchall()
                for post_id, ads_count, message, created_time in posts_with_ads:
                    message_preview = (message[:50] + "...") if message and len(message) > 50 else (message or "No message")
                    created_str = created_time.strftime('%Y-%m-%d') if created_time else "Unknown"
                    print(f"📄 {post_id} ({ads_count} ads) - {created_str}")
                    print(f"   💬 {message_preview}")
                
    except Exception as e:
        print(f"❌ Error showing stats: {e}")

if __name__ == "__main__":
    main()
