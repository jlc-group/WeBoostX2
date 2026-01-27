#!/usr/bin/env python3
"""
Complete Facebook Data Sync Script (Non-Video Posts Only)
Syncs Facebook posts, attachments, and insights to PostgreSQL database
Designed to work perfectly with the ER diagram schema
Compatible with Facebook Graph API v23.0

Note: Video posts are handled by separate sync_fb_video_posts_to_db.py script
This script handles: text posts, photo posts, link posts, album posts, etc.
"""

import os
import sys
import requests
import psycopg2
import json
import argparse
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from database_media_manager import DatabaseMediaManager

# Load environment variables
load_dotenv()

# Database Configuration
PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

# Facebook API Configuration
FB_PAGE_ACCESS_TOKENS = os.getenv("FB_PAGE_ACCESS_TOKENS", "").split(',')
FB_PAGE_IDS = os.getenv("FB_PAGE_IDS", "").split(',')

class FacebookSync:
    def __init__(self):
        """Initialize database connection and setup"""
        self.conn = None
        self.setup_database()
        # Initialize Database-Only Media Manager
        self.media_manager = DatabaseMediaManager()
    
    def is_video_post(self, post_id, permalink_url, message, story):
        """
        ตรวจสอบว่าเป็น video post หรือไม่ด้วยหลายวิธี
        Return: (is_video: bool, detection_method: str)
        """
        
        # 1. ตรวจสอบจาก permalink_url (แม่นยำที่สุด)
        if permalink_url:
            video_url_patterns = [
                '/videos/',
                'facebook.com/watch',
                'facebook.com/video',
                'fb.watch',
                '/reel/',
                'facebook.com/reel'
            ]
            
            for pattern in video_url_patterns:
                if pattern in permalink_url:
                    return True, f"permalink_url pattern: {pattern}"
        
        # 2. ตรวจสอบ URL patterns ใน message/story content
        full_text = f"{message or ''} {story or ''}".lower()
        
        content_video_patterns = [
            'facebook.com/watch',
            'facebook.com/video', 
            '/videos/',
            'fb.watch',
            'www.facebook.com/reel',
            'youtube.com/watch',
            'youtu.be/'
        ]
        
        for pattern in content_video_patterns:
            if pattern in full_text:
                return True, f"content URL pattern: {pattern}"
        
        # 3. ตรวจสอบ video keywords (ภาษาไทยและอังกฤษ)
        video_keywords_th = ['วิดีโอ', 'รูปเคลื่อนไหว', 'คลิป', 'วีดีโอ', 'คลิ๊ป']
        video_keywords_en = ['video', 'clip', 'watch', 'reel', 'movie', 'film']
        
        # ตรวจสอบ exact word match เพื่อลด false positive
        import re
        
        for keyword in video_keywords_th:
            if re.search(r'\b' + re.escape(keyword) + r'\b', full_text):
                return True, f"Thai keyword: {keyword}"
                
        for keyword in video_keywords_en:
            if re.search(r'\b' + keyword + r'\b', full_text):
                return True, f"English keyword: {keyword}"
        
        return False, "not detected as video"
    
    def check_video_attachments(self, post_id, access_token):
        """
        ตรวจสอบ attachments ว่ามี video หรือไม่
        Return: (has_video: bool, video_types: list)
        """
        try:
            attachments = self.fetch_post_attachments(post_id, access_token)
            video_types = []
            
            for attachment in attachments:
                attachment_type = attachment.get('type', '')
                if attachment_type in ['video_inline', 'video', 'video_autoplay', 'video_share']:
                    video_types.append(attachment_type)
            
            return len(video_types) > 0, video_types
            
        except Exception as e:
            print(f"    ⚠️  Could not check attachments for {post_id}: {e}")
            return False, []
    
    def setup_database(self):
        """Setup database connection"""
        try:
            self.conn = psycopg2.connect(
                host=PG_HOST,
                port=PG_PORT,
                dbname=PG_DB,
                user=PG_USER,
                password=PG_PASSWORD
            )
            # เปลี่ยนเป็น autocommit=True เพื่อหลีกเลี่ยงปัญหา transaction block
            self.conn.autocommit = True
            print("✅ Database connection established")
            
            # Set search path
            with self.conn.cursor() as cursor:
                cursor.execute("SET search_path TO public;")
            
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            sys.exit(1)
    
    def safe_datetime_convert(self, datetime_str):
        """Safely convert Facebook datetime string to Python datetime"""
        if not datetime_str:
            return None
        try:
            # Facebook format: 2023-12-17T10:30:00+0000
            return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
        except:
            return None
    
    def insert_post(self, post_data):
        """Insert or update Facebook post with proper UPSERT"""
        query = """
        INSERT INTO facebook_posts (
            id, page_id, message, story, 
            created_time, is_published, is_hidden, permalink_url,
            picture_url, full_picture_url,
            local_picture_id, local_full_picture_id,
            created_at, updated_at
        ) VALUES (
            %(id)s, %(page_id)s, %(message)s, %(story)s,
            %(created_time)s, %(is_published)s, %(is_hidden)s, %(permalink_url)s,
            %(picture_url)s, %(full_picture_url)s,
            %(local_picture_id)s, %(local_full_picture_id)s,
            NOW(), NOW()
        ) ON CONFLICT (id) 
        DO UPDATE SET
            message = EXCLUDED.message,
            story = EXCLUDED.story,
            is_published = EXCLUDED.is_published,
            is_hidden = EXCLUDED.is_hidden,
            permalink_url = EXCLUDED.permalink_url,
            picture_url = EXCLUDED.picture_url,
            full_picture_url = EXCLUDED.full_picture_url,
            local_picture_id = EXCLUDED.local_picture_id,
            local_full_picture_id = EXCLUDED.local_full_picture_id,
            updated_at = NOW()
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, post_data)
            print(f"  ✅ Post {post_data['id']} inserted/updated")
            return True
        except Exception as e:
            print(f"  ❌ Error inserting post {post_data.get('id', 'unknown')}: {e}")
            return False
    
    def insert_attachment(self, attachment_data):
        """Insert attachment with safe error handling and media download"""
        query = """
        INSERT INTO facebook_post_attachments (
            post_id, type, media_url, thumbnail_url, 
            description, title, 
            local_media_id, local_thumbnail_id,
            created_at
        ) VALUES (
            %(post_id)s, %(type)s, %(media_url)s, %(thumbnail_url)s,
            %(description)s, %(title)s, 
            %(local_media_id)s, %(local_thumbnail_id)s,
            NOW()
        ) ON CONFLICT DO NOTHING
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, attachment_data)
            print(f"    📎 Attachment processed for post {attachment_data['post_id']}")
            return True
        except Exception as e:
            print(f"    ⚠️  Attachment error (continuing): {str(e)[:100]}")
            return False
    
    def insert_insight(self, insight_data):
        """Insert insight with safe error handling"""
        query = """
        INSERT INTO facebook_post_insights (
            post_id, metric_name, value_numeric, value_json, date_recorded, created_at
        ) VALUES (
            %(post_id)s, %(metric_name)s, %(value_numeric)s, %(value_json)s,
            %(date_recorded)s, NOW()
        ) ON CONFLICT DO NOTHING
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, insight_data)
            return True
        except Exception as e:
            print(f"      ⚠️  Insight error (continuing): {str(e)[:100]}")
            # ไม่ raise error - ให้ process ต่อไป
            return False
    
    def fetch_posts(self, page_id, access_token, days_back=365):
        """Fetch posts from Facebook page with v23.0 compatible fields (default: 1 year back)"""
        
        # คำนวณวันที่ที่ต้องการ
        if days_back:
            since_date = datetime.now() - timedelta(days=days_back)
            since_timestamp = int(since_date.timestamp())
            print(f"  📅 Fetching posts from last {days_back} days (since {since_date.strftime('%Y-%m-%d')})")
        else:
            since_timestamp = None
            print(f"  📅 Fetching ALL posts (no date limit)")
        
        posts_url = f"https://graph.facebook.com/v23.0/{page_id}/feed"
        params = {
            'fields': 'id,created_time,message,story,is_published,is_hidden,permalink_url',  # เพิ่ม permalink_url สำหรับ click-through
            'limit': 100,
            'access_token': access_token
        }
        
        # เพิ่ม since parameter ถ้ามีการจำกัดวันที่
        if since_timestamp:
            params['since'] = since_timestamp
        
        all_posts = []
        
        try:
            while posts_url:
                response = requests.get(posts_url, params=params if params else {})
                
                if response.status_code != 200:
                    print(f"  ❌ API Error {response.status_code}: {response.text}")
                    break
                
                data = response.json()
                
                if 'error' in data:
                    print(f"  ❌ Facebook API Error: {data['error']['message']}")
                    break
                
                posts = data.get('data', [])
                all_posts.extend(posts)
                
                # Check for next page
                paging = data.get('paging', {})
                posts_url = paging.get('next')
                params = None  # Next URL already contains all parameters
                
                print(f"  📄 Fetched {len(posts)} posts (Total: {len(all_posts)})")
                
        except Exception as e:
            print(f"  ❌ Error fetching posts: {e}")
        
        return all_posts
    
    def fetch_post_attachments(self, post_id, access_token):
        """Fetch attachments for a specific post"""
        try:
            url = f"https://graph.facebook.com/v23.0/{post_id}/attachments"
            params = {
                'fields': 'media,type,description,title',
                'access_token': access_token
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code != 200:
                return []
                
            data = response.json()
            
            if 'error' in data:
                return []
                
            return data.get('data', [])
            
        except Exception as e:
            print(f"    ⚠️  Error fetching attachments: {e}")
            return []
    
    def fetch_post_insights(self, post_id, access_token, created_time):
        """Fetch insights for a specific post with safe error handling"""
        # API Metrics ที่ปลอดภัย (ไม่ deprecated)
        # NOTE: 'post_saves' is NOT available in Post Insights API
        # Save data only comes from Ads Insights API (action_type: post)
        safe_metrics = [
            'post_impressions',
            'post_impressions_unique',
            'post_clicks',
            'post_reactions_by_type_total'
            # post_saves removed - not supported in Post Insights API v20.0+
        ]
        
        insights = []
        
        # Fetch API metrics
        for metric in safe_metrics:
            try:
                url = f"https://graph.facebook.com/v23.0/{post_id}/insights"
                params = {
                    'metric': metric,
                    'access_token': access_token
                }
                
                response = requests.get(url, params=params)
                
                if response.status_code != 200:
                    if metric == 'post_saves':
                        print(f"      ❌ API Error {response.status_code} for {metric}")
                    continue
                
                data = response.json()
                
                # 🆕 Debug logging for post_saves
                if metric == 'post_saves':
                    print(f"      📊 post_saves API response: {json.dumps(data, indent=2)[:500]}...")
                
                if 'error' in data:
                    if metric == 'post_saves':
                        print(f"      ❌ API Error: {data['error'].get('message', 'Unknown error')}")
                    continue
                
                insight_data = data.get('data', [])
                
                for insight in insight_data:
                    values = insight.get('values', [{}])
                    if values:
                        value_obj = values[0].get('value', 0)
                        end_time = values[0].get('end_time', '')
                        
                        # สร้าง date_recorded
                        if end_time:
                            date_recorded = end_time[:10]
                        elif created_time:
                            date_recorded = created_time[:10]
                        else:
                            date_recorded = datetime.now().strftime('%Y-%m-%d')
                        
                        # จัดการ value ตาม type
                        if isinstance(value_obj, (dict, list)):
                            insight_record = {
                                'post_id': post_id,
                                'metric_name': insight.get('name'),
                                'value_numeric': None,
                                'value_json': json.dumps(value_obj),
                                'date_recorded': date_recorded
                            }
                        else:
                            insight_record = {
                                'post_id': post_id,
                                'metric_name': insight.get('name'),
                                'value_numeric': value_obj,
                                'value_json': None,
                                'date_recorded': date_recorded
                            }
                        
                        insights.append(insight_record)
                        
            except Exception as e:
                print(f"      ⚠️  Error fetching metric {metric}: {e}")
                continue
        
        # Fetch additional engagement data
        try:
            url = f"https://graph.facebook.com/v23.0/{post_id}"
            params = {
                'fields': 'shares,comments.summary(true),likes.summary(true)',
                'access_token': access_token
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                # วันที่สำหรับ engagement metrics
                date_recorded = created_time[:10] if created_time else datetime.now().strftime('%Y-%m-%d')
                
                # Share count
                share_count = data.get('shares', {}).get('count', 0)
                insights.append({
                    'post_id': post_id,
                    'metric_name': 'share_count',
                    'value_numeric': share_count,
                    'value_json': None,
                    'date_recorded': date_recorded
                })
                
                # Comment count
                comment_count = data.get('comments', {}).get('summary', {}).get('total_count', 0)
                insights.append({
                    'post_id': post_id,
                    'metric_name': 'comment_count',
                    'value_numeric': comment_count,
                    'value_json': None,
                    'date_recorded': date_recorded
                })
                
                # Like count
                like_count = data.get('likes', {}).get('summary', {}).get('total_count', 0)
                insights.append({
                    'post_id': post_id,
                    'metric_name': 'like_count',
                    'value_numeric': like_count,
                    'value_json': None,
                    'date_recorded': date_recorded
                })
                
        except Exception as e:
            print(f"      ⚠️  Error fetching engagement data: {e}")
        
        return insights
    
    def sync_page_data(self, page_id, access_token, days_back=365):
        """Sync all data for a specific Facebook page"""
        print(f"\n🔄 Syncing data for page: {page_id}")
        
        # 1. Fetch posts
        posts = self.fetch_posts(page_id, access_token, days_back)
        
        if not posts:
            print(f"  ⚠️  No posts found for page {page_id}")
            return
        
        success_count = 0
        error_count = 0
        video_skipped_count = 0
        
        for post in posts:
            post_id = post.get('id')
            created_time = post.get('created_time')
            message = post.get('message', '')
            story = post.get('story', '')
            is_published = post.get('is_published', True)
            is_hidden = post.get('is_hidden', False)
            permalink_url = post.get('permalink_url')  # เพิ่มการดึง permalink_url
            
            print(f"\n  📝 Processing post: {post_id}")
            
            # 🚫 กรอง video posts ออก - ให้ sync_fb_video_posts_to_db.py จัดการ
            # 🔍 ใช้ระบบตรวจสอบหลายระดับ
            
            # 1. ตรวจสอบจาก content และ URL patterns
            is_video, detection_method = self.is_video_post(post_id, permalink_url, message, story)
            
            if is_video:
                print(f"  ⏭️  Skipping video post {post_id} ({detection_method})")
                video_skipped_count += 1
                continue
            
            # 2. ตรวจสอบ attachments เพิ่มเติม (ถ้าไม่แน่ใจจากข้อ 1)
            has_video_attachment, video_types = self.check_video_attachments(post_id, access_token)
            
            if has_video_attachment:
                print(f"  ⏭️  Skipping video post {post_id} (attachment types: {', '.join(video_types)})")
                video_skipped_count += 1
                continue
            
            try:
                # 2. Insert/Update post with available non-deprecated fields only
                post_data = {
                    'id': post_id,
                    'page_id': page_id,
                    'message': message,
                    'story': story,
                    'created_time': self.safe_datetime_convert(created_time),
                    'is_published': is_published,
                    'is_hidden': is_hidden,
                    'permalink_url': permalink_url,  # เพิ่ม permalink_url สำหรับ click-through
                    'picture_url': None,  # จะอัปเดตจาก attachments
                    'full_picture_url': None,  # จะอัปเดตจาก attachments  
                    'local_picture_id': None,  # จะอัปเดตจาก attachments
                    'local_full_picture_id': None  # จะอัปเดตจาก attachments
                }
                
                if not self.insert_post(post_data):
                    error_count += 1
                    continue
                
                # 3. Fetch and insert attachments (exclude video attachments)
                attachments = self.fetch_post_attachments(post_id, access_token)
                
                attachment_success = 0
                main_picture_url = None
                main_full_picture_url = None
                main_picture_media_id = None
                main_full_picture_media_id = None
                
                for attachment in attachments:
                    try:
                        # แยก transaction สำหรับแต่ละ attachment
                        media = attachment.get('media', {})
                        attachment_type = attachment.get('type', 'photo')
                        media_url = media.get('source') or media.get('image', {}).get('src')
                        
                        # 🚫 ข้าม video attachments - ให้ video script จัดการ
                        if attachment_type in ['video_inline', 'video']:
                            print(f"    ⏭️  Skipping video attachment (handled by video sync script)")
                            continue
                        
                        # ดาวน์โหลดรูปภาพหลักและ thumbnail
                        local_media_id = None
                        local_thumbnail_id = None
                        thumbnail_url = media.get('image', {}).get('src')
                        
                        # ดาวน์โหลด main media
                        if media_url:
                            print(f"    🖼️  Downloading main media to database...")
                            local_media_id = self.media_manager.store_media_from_url(
                                media_url, 
                                category="attachments",
                                source_post_id=post_id,  # เชื่อมโยงกับ post_id
                                source_type="facebook_post"
                            )
                            
                        # ดาวน์โหลด thumbnail (ถ้าต่างจาก main media)
                        if thumbnail_url and thumbnail_url != media_url:
                            print(f"    🖼️  Downloading thumbnail to database...")
                            local_thumbnail_id = self.media_manager.store_media_from_url(
                                thumbnail_url, 
                                category="thumbnails",
                                source_post_id=post_id,  # เชื่อมโยงกับ post_id
                                source_type="facebook_post"
                            )
                        
                        # เก็บ picture URLs สำหรับอัปเดต post
                        if attachment_type == 'photo' and media_url:
                            if not main_picture_url:  # เก็บรูปแรกเป็น main picture
                                main_picture_url = thumbnail_url or media_url
                                main_full_picture_url = media_url
                                main_picture_media_id = local_thumbnail_id or local_media_id
                                main_full_picture_media_id = local_media_id
                        
                        attachment_data = {
                            'post_id': post_id,
                            'type': attachment_type,
                            'media_url': media_url,
                            'thumbnail_url': thumbnail_url,
                            'description': attachment.get('description'),
                            'title': attachment.get('title'),
                            'local_media_id': local_media_id,
                            'local_thumbnail_id': local_thumbnail_id
                        }
                        
                        if self.insert_attachment(attachment_data):
                            attachment_success += 1
                            
                        # ไม่ต้อง commit เพราะใช้ autocommit=True แล้ว
                        
                    except Exception as e:
                        print(f"    ⚠️  Attachment error (skipping): {e}")
                        continue
                
                # อัปเดต post ด้วย picture URLs และ media IDs จาก attachments
                if main_picture_url or main_full_picture_url:
                    try:
                        with self.conn.cursor() as cursor:
                            cursor.execute("""
                                UPDATE facebook_posts 
                                SET picture_url = %s, full_picture_url = %s,
                                    local_picture_id = %s, local_full_picture_id = %s
                                WHERE id = %s
                            """, (
                                main_picture_url, main_full_picture_url,
                                main_picture_media_id, main_full_picture_media_id,
                                post_id
                            ))
                        print(f"    🖼️  Picture URLs and local media IDs updated")
                    except Exception as e:
                        print(f"    ⚠️  Picture URL update failed: {e}")
                
                # 4. Fetch and insert insights
                insights = self.fetch_post_insights(post_id, access_token, created_time)
                
                insight_success = 0
                for insight in insights:
                    try:
                        # แยก operation สำหรับแต่ละ insight
                        if self.insert_insight(insight):
                            insight_success += 1
                            
                        # ไม่ต้อง commit เพราะใช้ autocommit=True แล้ว
                        
                    except Exception as e:
                        print(f"    ⚠️  Insight error (skipping): {e}")
                        continue
                
                print(f"    📊 {insight_success} insights processed")
                print(f"    📎 {attachment_success} attachments processed")
                
                success_count += 1
                
                # ใช้ autocommit แล้ว ไม่ต้องมี manual commit/rollback
                
            except Exception as e:
                print(f"    ❌ Error processing post {post_id}: {e}")
                error_count += 1
                # ด้วย autocommit=True จะไม่มีปัญหา transaction block
                continue
        
        print(f"\n✅ Page {page_id} sync completed:")
        print(f"   📊 {success_count} posts processed successfully")
        print(f"   ⏭️  {video_skipped_count} video posts skipped (handled by video sync script)")
        print(f"   ❌ {error_count} posts failed")
    
    def run_sync(self, days_back=365):
        """Main sync process for all configured pages (default: 1 year back)"""
        print("🚀 Starting Complete Facebook Data Sync (Non-Video Posts Only)...")
        print("📺 Video posts will be handled by sync_fb_video_posts_to_db.py")
        
        if days_back:
            print(f"📅 Date Range: Last {days_back} days ({(datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')})")
        else:
            print("📅 Date Range: ALL available data (no limit)")
            
        print("=" * 60)
        
        if not FB_PAGE_IDS or not FB_PAGE_ACCESS_TOKENS:
            print("❌ Missing Facebook configuration. Check .env file.")
            return
        
        if len(FB_PAGE_IDS) != len(FB_PAGE_ACCESS_TOKENS):
            print("❌ Mismatch between FB_PAGE_IDS and FB_PAGE_ACCESS_TOKENS count")
            return
        
        total_pages = len(FB_PAGE_IDS)
        
        for i, (page_id, access_token) in enumerate(zip(FB_PAGE_IDS, FB_PAGE_ACCESS_TOKENS), 1):
            if not page_id.strip() or not access_token.strip():
                print(f"⚠️  Skipping empty page_id or token (item {i})")
                continue
                
            print(f"\n📄 Processing page {i}/{total_pages}")
            self.sync_page_data(page_id.strip(), access_token.strip(), days_back)
        
        print("\n" + "=" * 60)
        print("🎉 Non-Video Facebook Data Sync finished!")
        print("💡 Remember to run sync_fb_video_posts_to_db.py for video content")
        
        # แสดงสถิติ media storage
        print("\n📊 Media Storage Statistics:")
        if hasattr(self, 'media_manager'):
            self.media_manager.get_storage_stats()
    
    def __del__(self):
        """Clean up database connection"""
        if self.conn:
            self.conn.close()

def main():
    """Main function with command line argument support"""
    # Fix Windows Unicode encoding issue
    import sys
    if sys.platform.startswith('win'):
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    # Setup command line argument parser
    parser = argparse.ArgumentParser(
        description='Complete Facebook Data Sync Script (Non-Video Posts Only)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_facebook_complete.py                    # Sync last 365 days (default)
  python sync_facebook_complete.py --days-back 30     # Sync last 30 days
  python sync_facebook_complete.py --days-back 7      # Sync last 7 days
  python sync_facebook_complete.py --all              # Sync all available data (no time limit)
  
Date Range Options:
  --days-back 365  → Sync last 1 year (recommended for first run)
  --days-back 90   → Sync last 3 months
  --days-back 30   → Sync last 1 month
  --days-back 7    → Sync last 1 week
  --all            → Sync all available data (no time limit)
        """
    )
    
    # Add mutually exclusive group for date options
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        '--days-back',
        type=int,
        default=365,
        help='Number of days to sync back from today (default: 365)'
    )
    date_group.add_argument(
        '--all',
        action='store_true',
        help='Sync all available data with no time limit'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Determine days_back value
    if args.all:
        days_back = None
        print("📅 Mode: Sync ALL available data (no time limit)")
    else:
        days_back = args.days_back
        print(f"📅 Mode: Sync last {days_back} days")
    
    try:
        sync = FacebookSync()
        sync.run_sync(days_back=days_back)
    except KeyboardInterrupt:
        print("\n⚠️  Sync interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()