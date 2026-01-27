#!/usr/bin/env python3
"""
Facebook Posts Performance Sync Script
รวบรวมข้อมูลจากแหล่งต่างๆมาใส่ในตาราง facebook_posts_performance

Data Sources Integration:
✅ facebook_posts - ข้อมูลพูิ้นฐาน
✅ facebook_video_posts - video/reels data
✅ facebook_post_insights - engagement metrics  
✅ facebook_ads - ads ที่เกี่ยวข้อง
✅ facebook_ads_insights - ad performance
✅ facebook_campaigns - campaign details
✅ media_storage - thumbnails
✅ products - product association (user mapping)

Performance Calculations:
- Engagement rate = (likes + comments + shares) / reach * 100
- CTR = clicks / impressions * 100  
- Performance score = weighted formula based on engagement, cost efficiency, reach

Usage:
    python sync_facebook_posts_performance.py                    # Sync ทั้งหมด
    python sync_facebook_posts_performance.py --days-back 30     # Sync 30 วันล่าสุด
    python sync_facebook_posts_performance.py --post-id POST_ID  # Sync post เดียว
    python sync_facebook_posts_performance.py --recalculate      # คำนวณ performance ใหม่
"""

import os
import sys
import json
import psycopg2
import requests
import time
import logging
import traceback
from datetime import datetime, timedelta
from decimal import Decimal
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

def setup_logging():
    """ตั้งค่า logging system"""
    # สร้าง logs directory ถ้าไม่มี
    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)
    
    # ตั้งค่า logging format
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # สร้าง logger
    logger = logging.getLogger('facebook_sync')
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # File handler - บันทึกทุกอย่างลงไฟล์
    log_filename = f"logs/facebook_sync_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(log_format, date_format)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Console handler - แสดงเฉพาะ INFO ขึ้นไป
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger

# Initialize logger
logger = setup_logging()

class FacebookPostsPerformanceSync:
    def __init__(self):
        """Initialize sync process"""
        self.conn = None
        self.processed_posts = 0
        self.updated_posts = 0
        self.errors = 0
        self.total_ads = 0
        self.total_campaigns = 0
        self.total_spend = 0
        self.start_time = datetime.now()
        self.ads_connection_verified = False
        self.logger = logging.getLogger('facebook_sync')
        
        # Log session start
        self.logger.info("=" * 60)
        self.logger.info("🎯 Facebook Posts Performance Sync - Session Started")
        self.logger.info(f"🕐 Start time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
    def connect_db(self):
        """Connect to database with validation"""
        try:
            # Validate environment variables
            if not all([PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD]):
                error_msg = "❌ Missing required database environment variables"
                self.logger.error(error_msg)
                self.logger.error("   Please check: PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD")
                print(error_msg)
                print("   Please check: PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD")
                return False
                
            self.conn = psycopg2.connect(
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DB,
                user=PG_USER,
                password=PG_PASSWORD
            )
            self.conn.autocommit = True
            success_msg = "✅ Database connection established"
            self.logger.info(success_msg)
            print(success_msg)
            
            # Verify ads table connectivity
            self.verify_ads_connection()
            return True
        except Exception as e:
            error_msg = f"❌ Database connection failed: {e}"
            self.logger.error(error_msg)
            print(error_msg)
            return False
    
    def verify_ads_connection(self):
        """Verify ads table has post_id connections"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM facebook_ads WHERE post_id IS NOT NULL AND post_id != ''")
                ads_with_posts = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM facebook_ads")
                total_ads = cursor.fetchone()[0]
                
                if total_ads > 0:
                    connection_rate = (ads_with_posts / total_ads) * 100
                    status_msg = f"📊 Ads connection status: {ads_with_posts:,}/{total_ads:,} ({connection_rate:.1f}%) ads have post_id"
                    self.logger.info(status_msg)
                    print(status_msg)
                    
                    if connection_rate < 50:
                        warning_msg = "⚠️  Warning: Low ads-to-posts connection rate. Consider running ads sync first."
                        self.logger.warning(warning_msg)
                        print(warning_msg)
                    else:
                        self.ads_connection_verified = True
                        success_msg = "✅ Good ads connection rate detected"
                        self.logger.info(success_msg)
                        print(success_msg)
                else:
                    info_msg = "ℹ️  No ads data found in database"
                    self.logger.info(info_msg)
                    print(info_msg)
                    
        except Exception as e:
            warning_msg = f"⚠️  Could not verify ads connection: {e}"
            self.logger.warning(warning_msg)
            print(warning_msg)

    def populate_video_promoted_mapping(self):
        """สร้าง/อัปเดต mapping ระหว่าง video_id กับ promoted_post_id
        
        ✅ CORRECT Logic:
        - Extract video_id from promoted_post_id (format: pageId_videoId)
        - Example: 107038946030147_943196201369931 → video_id = 943196201369931
        - Only map if video exists in facebook_video_posts
        """
        try:
            cursor = self.conn.cursor()
            
            # ✅ CORRECT: Match ONLY by video_id in creative JSON
            # DO NOT use timing-based matching - it creates too many duplicates!
            cursor.execute("""
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
            """)
            
            rows = cursor.rowcount
            self.conn.commit()
            
            if rows > 0:
                self.logger.info(f"🎬 Populated {rows} video promoted mappings")
            
            cursor.close()
            return rows
            
        except Exception as e:
            print(f"⚠️  Error populating video-promoted mapping: {e}")
            return 0

    def build_permalink_url(self, page_id, post_id, is_video=False, video_id=None):
        """Build Facebook permalink URL if not available
        
        Args:
            page_id: Facebook page ID
            post_id: Post ID (may include page_id prefix)
            is_video: Whether this is a video/reel post
            video_id: Video ID for video posts
        """
        if not page_id:
            return None
            
        # If is_video and we have video_id, use reel format
        if is_video and video_id:
            return f"https://www.facebook.com/reel/{video_id}/"
        
        # Extract clean post_id (remove page_id prefix if exists)
        clean_post_id = post_id.split('_')[-1] if '_' in post_id else post_id
        
        return f"https://www.facebook.com/{page_id}/posts/{clean_post_id}"

    def check_existing_media(self, image_url):
        """ตรวจสอบว่ามี media อยู่ในระบบแล้วหรือไม่"""
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM media_storage WHERE original_url = %s AND download_status = 'success'",
                    (image_url,)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"    ⚠️  Error checking existing media: {e}")
            return None

    def log_media_error(self, image_url, post_id, error_message):
        """บันทึก error ของการดาวน์โหลด media"""
        try:
            import uuid
            error_id = str(uuid.uuid4())
            
            # Log to file
            self.logger.error(f"Media download failed - Post: {post_id}, URL: {image_url[:50]}..., Error: {error_message}")
            
            query = """
            INSERT INTO media_storage (
                id, original_url, local_filename, local_path, 
                download_status, error_message,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
            
            with self.conn.cursor() as cursor:
                cursor.execute(query, (
                    error_id, image_url, f"failed_{post_id}", f"failed/{post_id}",
                    'failed', error_message
                ))
                log_msg = f"    📝 Logged media error for {post_id}: {error_message[:50]}..."
                self.logger.debug(log_msg)
                print(log_msg)
        except Exception as e:
            error_msg = f"    ⚠️  Failed to log media error: {e}"
            self.logger.error(error_msg)
            print(error_msg)

    def find_existing_media_for_post(self, post_id, thumbnail_url):
        """ค้นหา media ที่มีอยู่แล้วสำหรับ post นี้ (ไม่ดาวน์โหลดใหม่)"""
        try:
            with self.conn.cursor() as cursor:
                # Enhanced search strategy - ลองหาจากหลายแหล่ง
                search_methods = [
                    # 1. ค้นหาจาก source_post_id (exact match)
                    ("source_post_id exact", """
                        SELECT id, download_status, is_stored_in_db, public_url FROM media_storage 
                        WHERE source_post_id = %s AND download_status = 'success'
                        ORDER BY created_at DESC LIMIT 1
                    """, (post_id,)),
                    
                    # 2. ค้นหาจาก original_url (exact match)
                    ("original_url exact", """
                        SELECT id, download_status, is_stored_in_db, public_url FROM media_storage 
                        WHERE original_url = %s AND download_status = 'success'
                        ORDER BY created_at DESC LIMIT 1
                    """, (thumbnail_url,) if thumbnail_url else None),
                    
                    # 3. ค้นหาแบบ partial match สำหรับ orphaned videos
                    ("post_id pattern", """
                        SELECT id, download_status, is_stored_in_db, public_url FROM media_storage 
                        WHERE source_post_id LIKE %s AND download_status = 'success'
                        ORDER BY created_at DESC LIMIT 1
                    """, (f"%{post_id}%",)),
                    
                    # 4. ค้นหาจาก video_id สำหรับ orphaned videos
                    ("video_id search", """
                        SELECT ms.id, ms.download_status, ms.is_stored_in_db, ms.public_url 
                        FROM media_storage ms
                        JOIN facebook_video_posts vp ON ms.source_post_id = vp.video_id
                        WHERE vp.video_id = %s AND ms.download_status = 'success'
                        ORDER BY ms.created_at DESC LIMIT 1
                    """, (post_id,))
                ]
                
                for method_name, query, params in search_methods:
                    if params is None:  # Skip if no thumbnail_url for method 2
                        continue
                        
                    cursor.execute(query, params)
                    result = cursor.fetchone()
                    
                    if result:
                        media_id, status, is_in_db, public_url = result
                        print(f"    🔍 Found media via {method_name}: {media_id} (status: {status}, in_db: {is_in_db})")
                        return media_id
                
                print(f"    ❓ No existing media found for post {post_id}")
                return None
                
        except Exception as e:
            print(f"    ⚠️  Error finding existing media: {e}")
            return None


    def find_thumbnail_by_video_id(self, video_id):
        """ค้นหา thumbnail จาก video_id ใน facebook_video_posts"""
        if not video_id:
            return None
            
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    SELECT local_picture_id, picture
                    FROM facebook_video_posts
                    WHERE video_id = %s
                      AND local_picture_id IS NOT NULL
                    LIMIT 1
                """, (video_id,))
                
                result = cursor.fetchone()
                if result:
                    local_id = result[0]
                    picture_url = result[1]
                    print(f"    🔍 Found thumbnail for video_id {video_id}: local_id={local_id}")
                    return {
                        'local_thumbnail_id': local_id,
                        'thumbnail_url': picture_url
                    }
                return None
        except Exception as e:
            print(f"    ⚠️  Error finding thumbnail for video_id {video_id}: {e}")
            return None

    def find_posts_with_missing_media(self, limit=100):
        """ค้นหา posts ที่มี fbcdn URLs แต่ไม่มี local_thumbnail_id (เพื่อรายงานเท่านั้น)"""
        query = f"""
        SELECT 
            post_id, 
            thumbnail_url,
            local_thumbnail_id
        FROM facebook_posts_performance 
        WHERE thumbnail_url LIKE '%fbcdn.net%' 
        AND local_thumbnail_id IS NULL
        AND thumbnail_url IS NOT NULL
        ORDER BY create_time DESC
        LIMIT {limit}
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchall()
                
                posts_needing_media = []
                for i, row in enumerate(results):
                    try:
                        if len(row) < 3:
                            print(f"⚠️  Row {i} has insufficient columns: {len(row)}")
                            continue
                            
                        posts_needing_media.append({
                            'post_id': row[0],
                            'thumbnail_url': row[1],
                            'local_thumbnail_id': row[2]
                        })
                    except IndexError as e:
                        print(f"⚠️  Error processing row {i}: {e}, row: {row}")
                        continue
                
                print(f"📊 Found {len(posts_needing_media)} posts with missing local media")
                return posts_needing_media
                
        except Exception as e:
            print(f"❌ Error finding posts with missing media: {e}")
            return []

    def suggest_media_sync_commands(self, posts_needing_media):
        """แนะนำคำสั่งสำหรับ sync media"""
        if not posts_needing_media:
            print("✅ All posts have local media linked")
            return
            
        print(f"\n💡 Found {len(posts_needing_media)} posts needing media sync")
        print("📋 Recommended commands to fix missing media:")
        print("   1. For video thumbnails:")
        print("      python sync_fb_video_posts_to_db.py --days-back 30")
        print("   2. For photo attachments:")
        print("      python sync_facebook_complete.py --days-back 30") 
        print("   3. Then re-run performance sync:")
        print("      python sync_facebook_posts_performance.py --days-back 30")

    def generate_media_status_report(self):
        """สร้างรายงานสถานะ media storage พร้อมการเชื่อมโยงกับ posts"""
        try:
            with self.conn.cursor() as cursor:
                # 1. ข้อมูลพื้นฐาน posts
                cursor.execute("SELECT COUNT(*) FROM facebook_posts_performance")
                total_posts = cursor.fetchone()[0]
                
                # Posts with local media
                cursor.execute("""
                    SELECT COUNT(*) FROM facebook_posts_performance 
                    WHERE local_thumbnail_id IS NOT NULL
                """)
                posts_with_local = cursor.fetchone()[0]
                
                # Posts with external URLs
                cursor.execute("""
                    SELECT COUNT(*) FROM facebook_posts_performance 
                    WHERE thumbnail_url LIKE '%fbcdn.net%'
                """)
                posts_with_external = cursor.fetchone()[0]
                
                # Posts needing repair
                cursor.execute("""
                    SELECT COUNT(*) FROM facebook_posts_performance 
                    WHERE thumbnail_url LIKE '%fbcdn.net%' 
                    AND local_thumbnail_id IS NULL
                """)
                posts_needing_repair = cursor.fetchone()[0]
                
                # 2. ข้อมูลพื้นฐาน media storage
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_media,
                        COUNT(CASE WHEN download_status = 'success' THEN 1 END) as successful_downloads,
                        COUNT(CASE WHEN download_status = 'failed' THEN 1 END) as failed_downloads,
                        SUM(CASE WHEN download_status = 'success' THEN file_size ELSE 0 END) as total_size_bytes,
                        COUNT(CASE WHEN source_post_id IS NOT NULL THEN 1 END) as media_with_post_link,
                        COUNT(CASE WHEN source_post_id IS NULL THEN 1 END) as media_without_post_link
                    FROM media_storage
                """)
                media_basic_stats = cursor.fetchone()

                # 3. สถิติตาม media category
                cursor.execute("""
                    SELECT 
                        COALESCE(media_category, 'uncategorized') as category,
                        COUNT(*) as count,
                        COUNT(CASE WHEN download_status = 'success' THEN 1 END) as successful
                    FROM media_storage
                    GROUP BY media_category
                    ORDER BY count DESC
                """)
                category_stats = cursor.fetchall()

                # 4. สถิติตาม source type
                cursor.execute("""
                    SELECT 
                        COALESCE(source_type, 'unknown') as source_type,
                        COUNT(*) as count,
                        COUNT(CASE WHEN download_status = 'success' THEN 1 END) as successful
                    FROM media_storage
                    GROUP BY source_type
                    ORDER BY count DESC
                """)
                source_stats = cursor.fetchall()

                # 5. Top 10 posts ที่มี media มากที่สุด
                cursor.execute("""
                    SELECT 
                        source_post_id,
                        COUNT(*) as media_count,
                        STRING_AGG(DISTINCT COALESCE(media_category, 'uncategorized'), ', ') as categories
                    FROM media_storage
                    WHERE source_post_id IS NOT NULL
                    GROUP BY source_post_id
                    ORDER BY media_count DESC
                    LIMIT 10
                """)
                top_posts = cursor.fetchall()

                # 6. Media storage stats (legacy format for compatibility)
                cursor.execute("""
                    SELECT 
                        download_status,
                        COUNT(*) as count,
                        COALESCE(SUM(file_size), 0) as total_size
                    FROM media_storage 
                    GROUP BY download_status
                """)
                media_stats = cursor.fetchall()
                
                # Generate comprehensive report
                report = {
                    'posts': {
                        'total': total_posts,
                        'with_local_media': posts_with_local,
                        'with_external_urls': posts_with_external,
                        'needing_repair': posts_needing_repair,
                        'local_media_percentage': round((posts_with_local / max(total_posts, 1)) * 100, 1)
                    },
                    'media_basic_stats': media_basic_stats,
                    'category_stats': category_stats,
                    'source_stats': source_stats,
                    'top_posts': top_posts,
                    'media': {}
                }
                
                # Process media stats into dictionary for compatibility
                for status, count, size in media_stats:
                    report['media'][status] = {
                        'count': count,
                        'total_size': size,
                        'size_mb': round(size / (1024 * 1024), 2) if size > 0 else 0
                    }
                
                return report
        except Exception as e:
            print(f"❌ Error generating media report: {e}")
            return None

    def print_media_status_report(self):
        """แสดงรายงานสถานะ media storage"""
        print(f"\n📊 Media Storage Status Report")
        print("=" * 50)
        
        report = self.generate_media_status_report()
        if not report:
            print("❌ Failed to generate report")
            return
        
        # Posts statistics
        posts = report['posts']
        print(f"📄 Posts Overview:")
        print(f"  • Total posts: {posts['total']:,}")
        print(f"  • With local media: {posts['with_local_media']:,} ({posts['local_media_percentage']}%)")
        print(f"  • With external URLs: {posts['with_external_urls']:,}")
        print(f"  • Needing repair: {posts['needing_repair']:,}")
        
        # Media storage statistics
        media = report['media']
        if media:
            print(f"\n💾 Media Storage:")
            for status, stats in media.items():
                print(f"  • {status.title()}: {stats['count']:,} files ({stats['size_mb']:.2f} MB)")
        
        # Recommendations
        if posts['needing_repair'] > 0:
            print(f"\n💡 Recommendations:")
            print(f"  • Run media sync scripts to download missing media for {posts['needing_repair']} posts")
            print(f"  • Commands:")
            print(f"    1. python sync_fb_video_posts_to_db.py --days-back 30")
            print(f"    2. python sync_facebook_complete.py --days-back 30")
            print(f"    3. python sync_facebook_posts_performance.py --days-back 30")
    
    def get_posts_to_sync(self, days_back=None, post_id=None):
        """Get posts from BOTH facebook_posts and facebook_video_posts tables"""
        
        # Build date conditions
        date_condition_posts = ""
        date_condition_videos = ""
        params = []
        
        if post_id:
            # Query specific post from both tables
            # Support both formats: page_id_post_id and video_id
            if '_' in post_id:
                # Format: page_id_post_id
                date_condition_posts = "AND p.id = %s"
                date_condition_videos = "AND (vp.page_id || '_' || vp.video_id) = %s"
                params = [post_id, post_id]
            else:
                # Format: video_id only (legacy)
                date_condition_posts = "AND p.id = %s"
                date_condition_videos = "AND vp.video_id = %s"
                params = [post_id, post_id]
        elif days_back:
            date_filter = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d %H:%M:%S')
            date_condition_posts = "AND p.created_time >= %s"
            date_condition_videos = "AND vp.created_time >= %s"
            params = [date_filter, date_filter]
        
        # 🎯 Query ทั้ง facebook_posts และ facebook_video_posts
        query = f"""
        -- Posts from facebook_posts (photo posts, links, status)
        SELECT DISTINCT
            p.id as post_id,
            p.page_id,
            p.message,
            p.permalink_url,
            p.created_time,
            p.picture_url,
            p.local_picture_id,
            NULL::text as video_id,
            NULL::double precision as video_duration,
            NULL::text as video_title,
            CASE 
                WHEN p.picture_url IS NOT NULL THEN 'photo'
                WHEN p.source IS NOT NULL THEN 'link'
                ELSE 'status'
            END as attachment_type,
            p.source as attachment_url,
            'photo_post' as source_type
        FROM facebook_posts p
        WHERE 1=1 {date_condition_posts}
        
        UNION ALL
        
        -- Reels/Videos from facebook_video_posts
        -- 🎯 FIX: Use DISTINCT ON (video_id) to prevent duplicates
        -- Priority: promoted_post_id > organic post_id
        (
            SELECT DISTINCT ON (vp.video_id)
                COALESCE(
                    -- First try to get promoted_post_id from mapping (for ads matching)
                    (SELECT promoted_post_id 
                     FROM facebook_video_promoted_posts 
                     WHERE video_id = vp.video_id 
                     LIMIT 1),
                    -- Fallback to organic post_id if no promoted version
                    vp.page_id || '_' || vp.video_id
                ) as post_id,
                vp.page_id,
                vp.description as message,
                vp.permalink_url,
                vp.created_time,
                vp.picture as picture_url,
                vp.local_picture_id,
                vp.video_id,
                vp.length as video_duration,
                vp.title as video_title,
                CASE 
                    WHEN vp.length > 60 THEN 'video'
                    ELSE 'reel'
                END as attachment_type,
                vp.source as attachment_url,
                'video_post' as source_type
            FROM facebook_video_posts vp
            WHERE 1=1 {date_condition_videos}
            ORDER BY vp.video_id, vp.created_time DESC
        )
        
        ORDER BY created_time DESC
        """
        
        if not post_id:
            query += " LIMIT 1000"
        
        try:
            with self.conn.cursor() as cursor:
                # Count posts from both facebook_posts and facebook_video_posts
                count_query = f"""
                SELECT COUNT(*) FROM (
                    SELECT DISTINCT p.id FROM facebook_posts p WHERE 1=1 {date_condition_posts}
                    UNION ALL
                    SELECT DISTINCT vp.video_id FROM facebook_video_posts vp WHERE 1=1 {date_condition_videos}
                ) as combined_posts
                """
                
                if post_id:
                    cursor.execute(count_query, [post_id, post_id])
                elif days_back:
                    cursor.execute(count_query, params)
                else:
                    cursor.execute(count_query)
                
                total_posts = cursor.fetchone()[0]
                print(f"📊 Found: {total_posts:,} posts to sync")
                
                # Execute main query
                if post_id:
                    cursor.execute(query, [post_id, post_id])
                elif days_back:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                    
                results = cursor.fetchall()
                
                if not results:
                    print(f"📊 Found: 0 posts")
                    return []
                
                # 🚀 Enhanced media linking for BOTH types
                try:
                    local_ids = [str(r[6]) for r in results if len(r) > 6 and r[6] is not None and str(r[6]).strip() != '']
                    media_map = {}
                    
                    if local_ids:
                        print(f"🔍 Looking up {len(local_ids)} local media references...")
                        media_query = """
                        SELECT id::text, local_filename, public_url, is_stored_in_db 
                        FROM media_storage 
                        WHERE id::text = ANY(%s) AND download_status = 'success'
                        """
                        cursor.execute(media_query, (local_ids,))
                        for media_id, filename, pub_url, is_db in cursor.fetchall():
                            endpoint = pub_url or f"http://localhost:8000/media/{filename}" if filename else None
                            media_map[media_id] = endpoint
                    
                    # Enhance results with proper media URLs
                    if media_map:
                        print(f"✅ Enhanced {len(media_map)} posts with local media URLs")
                        enhanced_results = []
                        for row in results:
                            row_list = list(row)
                            if len(row_list) > 6 and row_list[6] and row_list[6] in media_map:
                                row_list[5] = media_map[row_list[6]]  # Update picture_url
                            enhanced_results.append(tuple(row_list))
                        results = enhanced_results
                        
                except Exception as media_error:
                    print(f"⚠️  Media enhancement failed: {media_error}")
                
                # 📊 Count by source type  
                photo_posts_retrieved = sum(1 for r in results if len(r) > 12 and r[12] == 'photo_post')
                video_posts_retrieved = sum(1 for r in results if len(r) > 12 and r[12] == 'video_post')
                print(f"✅ Retrieved: {photo_posts_retrieved} photo posts + {video_posts_retrieved} video posts = {len(results)} total")
                
                return results
        except Exception as e:
            print(f"❌ Error fetching posts: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def get_post_insights(self, post_id):
        """Get aggregated insights for a post - Enhanced with clicks fallback"""
        query = """
        SELECT 
            SUM(CASE WHEN metric_name = 'post_impressions' THEN value_numeric END) as impressions,
            SUM(CASE WHEN metric_name = 'post_impressions_unique' THEN value_numeric END) as impressions_unique,
            -- Try multiple click metrics (Facebook API has variations)
            COALESCE(
                SUM(CASE WHEN metric_name = 'post_clicks' THEN value_numeric END),
                SUM(CASE WHEN metric_name = 'post_clicks_unique' THEN value_numeric END),
                SUM(CASE WHEN metric_name = 'post_consumptions' THEN value_numeric END),
                0
            ) as clicks,
            SUM(CASE WHEN metric_name = 'like_count' THEN value_numeric END) as likes,
            SUM(CASE WHEN metric_name = 'comment_count' THEN value_numeric END) as comments,
            SUM(CASE WHEN metric_name = 'share_count' THEN value_numeric END) as shares,
            SUM(CASE WHEN metric_name = 'post_saves' THEN value_numeric END) as post_saves,
            (
                SELECT value_json 
                FROM facebook_post_insights 
                WHERE post_id = %s AND metric_name = 'post_reactions_by_type_total' 
                LIMIT 1
            ) as reactions_json
        FROM facebook_post_insights 
        WHERE post_id = %s
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, (post_id, post_id))
                result = cursor.fetchone()
                
                # ⭐ Check if result exists and has data
                if not result or len(result) < 8:
                    print(f"    ⚠️  No insights data found for post {post_id}")
                    return {
                        'impressions': 0,
                        'impressions_unique': 0,
                        'clicks': 0,
                        'likes': 0,
                        'comments': 0,
                        'shares': 0,
                        'post_saves': 0,
                        'reactions': None
                    }
                
                clicks = result[2] or 0
                
                # Debug: ถ้า clicks = 0 แต่มี impressions ให้ log warning
                if clicks == 0 and (result[0] or 0) > 0:
                    # ลองหาว่ามี click metrics อื่นไหม
                    cursor.execute("""
                        SELECT metric_name, value_numeric 
                        FROM facebook_post_insights 
                        WHERE post_id = %s 
                        AND metric_name LIKE '%click%'
                        LIMIT 5
                    """, (post_id,))
                    available_metrics = cursor.fetchall()
                    if available_metrics:
                        print(f"    ⚠️  Post {post_id}: Found click metrics: {available_metrics}")
                
                return {
                    'impressions': result[0] or 0,
                    'impressions_unique': result[1] or 0,
                    'clicks': clicks,
                    'likes': result[3] or 0,
                    'comments': result[4] or 0,
                    'shares': result[5] or 0,
                    'post_saves': result[6] or 0,
                    'reactions': result[7]
                }
        except Exception as e:
            print(f"❌ Error fetching insights for {post_id}: {e}")
            return {}
    
    def extract_video_id_from_url(self, url):
        """Extract video ID from Facebook permalink URL"""
        if not url:
            return None
        
        import re
        match = re.search(r'videos/(\d+)', url)
        return match.group(1) if match else None
    
    def get_video_insights(self, video_id):
        """Get aggregated video insights"""
        if not video_id:
            return {}
            
        # Try to get video insights first
        video_query = """
        SELECT 
            SUM(total_video_views) as video_views,
            SUM(total_video_view_total_time) as total_time_watched,
            AVG(total_video_avg_time_watched) as avg_time_watched
        FROM facebook_video_insights 
        WHERE video_id = %s
        """
        
        # Try to get reels insights 
        reels_query = """
        SELECT 
            SUM(fb_reels_total_plays) as video_views,
            SUM(post_video_view_time) as total_time_watched,
            AVG(post_video_avg_time_watched) as avg_time_watched
        FROM facebook_reels_insights 
        WHERE video_id = %s
        """
        
        try:
            with self.conn.cursor() as cursor:
                # First try video insights
                cursor.execute(video_query, (video_id,))
                video_result = cursor.fetchone()
                
                # Then try reels insights
                cursor.execute(reels_query, (video_id,))
                reels_result = cursor.fetchone()
                
                # Combine the results (prefer video insights if both exist)
                video_views = 0
                total_time = 0
                avg_time = 0
                
                if video_result and video_result[0]:
                    video_views = video_result[0] or 0
                    total_time = video_result[1] or 0
                    avg_time = video_result[2] or 0
                elif reels_result and reels_result[0]:
                    video_views = reels_result[0] or 0
                    total_time = reels_result[1] or 0
                    avg_time = reels_result[2] or 0
                
                return {
                    'video_views': video_views,
                    'total_time_watched': total_time,
                    'average_time_watched': avg_time
                }
        except Exception as e:
            print(f"❌ Error fetching video insights for {video_id}: {e}")
            return {}
    
    def get_video_post_engagement(self, video_id):
        """Get engagement metrics (likes, comments, shares) for video/reels posts from JSON fields
        
        🎯 Purpose:
        Video/reels engagement is stored in facebook_reels_insights table in JSON format:
        - post_video_likes_by_reaction_type: {"REACTION_LIKE": 123, "REACTION_LOVE": 45, ...}
        - post_video_social_actions: {"comment": 89, "share": 12}
        
        This function parses these JSON fields and returns engagement metrics in standard format.
        
        ⚠️ SAFETY:
        - Only called for video posts (video_id must exist)
        - Only when existing insights have no engagement data (likes == 0)
        - Never modifies data for photo posts
        - Returns 0 if no data found (not None to avoid TypeError)
        
        Returns:
            dict: {'likes': int, 'comments': int, 'shares': int}
        """
        if not video_id:
            return {'likes': 0, 'comments': 0, 'shares': 0}
        
        query = """
        SELECT 
            post_video_likes_by_reaction_type,
            post_video_social_actions
        FROM facebook_reels_insights 
        WHERE video_id = %s
        ORDER BY date_start DESC
        LIMIT 1
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, (video_id,))
                result = cursor.fetchone()
                
                if not result:
                    return {'likes': 0, 'comments': 0, 'shares': 0}
                
                likes_json_str = result[0]  # post_video_likes_by_reaction_type (text)
                actions_json_str = result[1]  # post_video_social_actions (text)
                
                # Parse likes JSON string - sum all reaction types
                total_likes = 0
                if likes_json_str:
                    try:
                        likes_data = json.loads(likes_json_str) if isinstance(likes_json_str, str) else likes_json_str
                        if likes_data and isinstance(likes_data, dict):
                            for reaction_type, count in likes_data.items():
                                try:
                                    total_likes += int(count)
                                except (ValueError, TypeError):
                                    continue
                    except json.JSONDecodeError:
                        pass
                
                # Parse comments and shares JSON string
                comments = 0
                shares = 0
                if actions_json_str:
                    try:
                        actions_data = json.loads(actions_json_str) if isinstance(actions_json_str, str) else actions_json_str
                        if actions_data and isinstance(actions_data, dict):
                            # Try both lowercase and uppercase keys
                            comments = int(actions_data.get('COMMENT', actions_data.get('comment', 0)))
                            shares = int(actions_data.get('SHARE', actions_data.get('share', 0)))
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
                
                # Log successful parse
                if total_likes > 0 or comments > 0 or shares > 0:
                    print(f"💙 Video {video_id}: Parsed {total_likes} likes, {comments} comments, {shares} shares")
                
                return {
                    'likes': total_likes,
                    'comments': comments,
                    'shares': shares
                }
                
        except Exception as e:
            print(f"❌ Error fetching video engagement for {video_id}: {e}")
            return {'likes': 0, 'comments': 0, 'shares': 0}
    
    def get_ads_data(self, post_id):
        """Get comprehensive ads data - Simplified approach
        
        🎯 Simple Solution:
        - post_id passed here is ALREADY the correct one:
          * For reels: promoted_post_id (from get_posts_to_sync query)
          * For photos: organic post_id
        - Just search ads using this post_id directly
        - No complex mapping logic needed anymore
        
        Example: 
        - Reel L10: post_id = 107038946030147_943196201369931 (promoted)
          → Finds Ad 6933147088806 directly ✅
        """
        
        # Simple: just use the post_id as-is
        search_post_ids = [post_id]
        print(f"    🔍 Searching ads for post_id: {post_id}")
        
        # 🎯 CRITICAL FIX: Strict matching for reels/video posts
        # Only match ads where post_id is EXACTLY in our list
        # DO NOT use creative JSON fields - they can match unrelated posts
        direct_query = """
        WITH ad_insights_summary AS (
            -- Step 1: Aggregate daily insights for EACH ad_id
            SELECT 
                ad_id,
                SUM(spend) as total_spend,
                SUM(impressions) as total_impressions,
                SUM(clicks) as total_clicks,
                SUM(post_saves) as total_post_saves,
                SUM(reach) as total_reach,
                
                CASE 
                    WHEN SUM(reach) > 0 THEN SUM(impressions)::DECIMAL / SUM(reach)
                    ELSE 0
                END as calculated_frequency,
                
                CASE 
                    WHEN SUM(impressions) > 0 THEN (SUM(spend)::DECIMAL / SUM(impressions)) * 1000
                    ELSE 0
                END as calculated_cpm,
                
                CASE 
                    WHEN SUM(reach) > 0 THEN SUM(spend)::DECIMAL / SUM(reach)
                    ELSE 0
                END as calculated_cpp,
                
                CASE 
                    WHEN SUM(impressions) > 0 THEN (SUM(clicks)::DECIMAL / SUM(impressions))
                    ELSE 0
                END as calculated_ctr,
                
                SUM(COALESCE(results, 0)) as total_results,
                
                CASE 
                    WHEN SUM(COALESCE(results, 0)) > 0 THEN 
                        SUM(spend)::DECIMAL / SUM(COALESCE(results, 0))
                    ELSE 0
                END as calculated_cost_per_result,
                
                MIN(date_start) as first_date,
                MAX(date_stop) as last_date,
                COUNT(*) as insights_days_count,
                MAX(account_id) as account_id
            FROM facebook_ads_insights
            GROUP BY ad_id
        )
        -- Step 2: STRICT matching - only post_id column (most reliable)
        -- DO NOT use creative JSON as it can match wrong posts
        SELECT DISTINCT ON (a.ad_id)
            a.ad_id, a.name as ad_name, a.status as ad_status, a.creative as ad_creative,
            adset.adset_id, adset.name as adset_name, adset.status as adset_status, adset.daily_budget as adset_daily_budget,
            c.campaign_id, c.name as campaign_name, c.status as campaign_status, c.objective as campaign_objective, c.daily_budget as campaign_daily_budget,
            COALESCE(ai.total_spend, 0) as total_spend,
            COALESCE(ai.total_impressions, 0) as total_impressions, 
            COALESCE(ai.total_clicks, 0) as total_clicks, 
            COALESCE(ai.calculated_ctr, 0) as avg_ctr, 
            COALESCE(ai.total_reach, 0) as total_reach,
            COALESCE(ai.calculated_frequency, 0) as avg_frequency, 
            COALESCE(ai.calculated_cpm, 0) as avg_cpm, 
            COALESCE(ai.calculated_cpp, 0) as avg_cpp,
            COALESCE(ai.total_results, 0) as total_results,
            COALESCE(ai.calculated_cost_per_result, 0) as cost_per_result,
            COALESCE(ai.total_post_saves, 0) as total_post_saves,
            ai.first_date, 
            ai.last_date, 
            ai.account_id as advertiser_id,
            ai.insights_days_count as insights_records_count,
            a.created_time as ad_created_time,
            a.updated_time as ad_updated_time
        FROM facebook_ads a
        LEFT JOIN facebook_adsets adset ON a.adset_id = adset.adset_id
        LEFT JOIN facebook_campaigns c ON adset.campaign_id = c.campaign_id
        LEFT JOIN ad_insights_summary ai ON a.ad_id = ai.ad_id
        WHERE a.post_id = ANY(%s)
        ORDER BY a.ad_id, a.created_time DESC
        LIMIT 50
        """
        
        try:
            with self.conn.cursor() as cursor:
                # 🔍 DEBUG: Print query parameters
                print(f"    🔍 Searching for ads with post_ids: {search_post_ids}")
                
                # Pass post_ids ONCE - only for post_id column matching
                cursor.execute(direct_query, (search_post_ids,))
                ads_data = cursor.fetchall()
                
            if ads_data:
                print(f"    🎯 Found {len(ads_data)} ads")
            
            if not ads_data:
                print(f"    ℹ️  No ads found for post {post_id}")
                return {'ads_details': [], 'ads_total_media_cost': 0, 'ads_count': 0, 'campaigns_count': 0, 'adsets_count': 0, 'campaign_summary': {}}
            
            total_cost = 0
            ads_details = []
            campaign_summary = {}
            campaigns_count = 0
            
            for ad in ads_data:
                    # Extract data with proper indexing for aggregated query
                    try:
                        # ⭐ Check if ad is tuple (from SQL query)
                        if not isinstance(ad, (tuple, list)):
                            print(f"    ⚠️  Unexpected ad data type: {type(ad)}")
                            continue
                        
                        if len(ad) < 29:
                            print(f"    ⚠️  Incomplete ad data: expected 29 fields, got {len(ad)}")
                            continue
                        
                        ad_id, ad_name, ad_status, ad_creative = ad[0], ad[1], ad[2], ad[3]
                        adset_id, adset_name, adset_status, adset_daily_budget = ad[4], ad[5], ad[6], ad[7]
                        campaign_id, campaign_name, campaign_status, campaign_objective, campaign_daily_budget = ad[8], ad[9], ad[10], ad[11], ad[12]
                        
                        # Aggregated insights per ad_id (sum of daily insights)
                        total_spend = float(ad[13]) if ad[13] is not None else 0
                        total_impressions = int(ad[14]) if ad[14] is not None else 0
                        total_clicks = int(ad[15]) if ad[15] is not None else 0
                        avg_ctr = float(ad[16]) if ad[16] is not None else 0
                        max_reach = int(ad[17]) if ad[17] is not None else 0
                        avg_frequency = float(ad[18]) if ad[18] is not None else 0
                        avg_cpm = float(ad[19]) if ad[19] is not None else 0
                        avg_cpp = float(ad[20]) if ad[20] is not None else 0
                        total_results = float(ad[21]) if ad[21] is not None else 0
                        calculated_cost_per_result = float(ad[22]) if ad[22] is not None else 0
                        total_post_saves = int(ad[23]) if ad[23] is not None else 0
                        first_date, last_date, advertiser_id = ad[24], ad[25], ad[26]
                        insights_records_count = int(ad[27]) if ad[27] is not None else 0
                        ad_created_time, ad_updated_time = ad[28], ad[29]
                        
                        print(f"    💰 Ad {ad_id}: ${total_spend:.2f} spend, {int(total_results)} results, ${calculated_cost_per_result:.2f}/result ({insights_records_count} days)")
                            
                    except (IndexError, TypeError, ValueError) as e:
                        print(f"    ⚠️  Error accessing ad data: {e}, ad length: {len(ad)}")
                        continue
                    
                    # Build comprehensive ad detail structure in the exact requested format
                    # ✅ Safe date formatting - check if datetime object before strftime
                    ad_detail = {
                        'cpm': avg_cpm,
                        'cpp': avg_cpp,
                        'ctr': avg_ctr,
                        'ad_id': ad_id,
                        'reach': max_reach,
                        'spend': total_spend,
                        'clicks': total_clicks,
                        'ad_name': ad_name,
                        'ad_text': ad_name,  # Using name as text for compatibility
                        'app_name': '',  # Not applicable for Facebook
                        'date_stop': last_date.strftime('%Y-%m-%d') if last_date and hasattr(last_date, 'strftime') else None,
                        'frequency': avg_frequency,
                        'objective': campaign_objective or 'UNKNOWN',  # ⚠️ แก้: ไม่ใช้ default ENGAGEMENT
                        'cost_per_result': calculated_cost_per_result,  # ✅ ใช้ค่าที่คำนวณจาก total_spend/total_results
                        'total_results': int(total_results),  # ✅ เพิ่มฟิลด์ total_results
                        'adgroup_id': adset_id,
                        'date_start': first_date.strftime('%Y-%m-%d') if first_date and hasattr(first_date, 'strftime') else None,
                        'campaign_id': campaign_id,
                        'create_time': ad_created_time.strftime('%Y-%m-%d') if ad_created_time and hasattr(ad_created_time, 'strftime') else None,
                        'impressions': total_impressions,
                        'modify_time': ad_updated_time.strftime('%Y-%m-%d') if ad_updated_time and hasattr(ad_updated_time, 'strftime') else None,
                        'adgroup_name': adset_name or '',
                        'display_name': ad_name,
                        'ad_total_cost': total_spend,
                        'advertiser_id': advertiser_id or '',
                        'campaign_name': campaign_name or '',
                        'insights_days': insights_records_count,
                        'adgroup_budget': float(adset_daily_budget) if adset_daily_budget else 0.0,
                        'adgroup_status': adset_status or 'ACTIVE',
                        'campaign_budget': float(campaign_daily_budget) if campaign_daily_budget else 0,
                        'campaign_status': campaign_status or 'ACTIVE',
                        'operation_status': ad_status or 'ACTIVE',
                        'secondary_status': ad_status or 'ACTIVE',
                        'adgroup_budget_mode': 'BUDGET_MODE_DAY'
                    }
                    
                    # ⚠️ Log warning ถ้าไม่มี campaign objective
                    if not campaign_objective:
                        print(f"    ⚠️  Ad {ad_id} has no campaign objective (adset={adset_id}, campaign={campaign_id})")
                    
                    ads_details.append(ad_detail)
                    # ✅ Each ad has its own spend (aggregated from daily insights)
                    # If multiple ads promote same post → their spends will be summed
                    total_cost += total_spend
                    print(f"    ✅ Added ad ${total_spend:.2f}, cumulative: ${total_cost:.2f}")
                    
                    # Track campaign summary with aggregated data
                    if campaign_id not in campaign_summary:
                        campaign_summary[campaign_id] = {
                            'campaign_name': campaign_name,
                            'campaign_objective': campaign_objective,
                            'total_spend': 0,
                            'ad_count': 0,
                            'adsets': set(),
                            'total_impressions': 0,
                            'total_clicks': 0
                        }
                    campaign_summary[campaign_id]['total_spend'] += total_spend
                    campaign_summary[campaign_id]['total_impressions'] += total_impressions
                    campaign_summary[campaign_id]['total_clicks'] += total_clicks
                    campaign_summary[campaign_id]['ad_count'] += 1
                    campaign_summary[campaign_id]['adsets'].add(adset_id)
            
            # Convert sets to counts for JSON serialization
            for campaign_id in campaign_summary:
                campaign_summary[campaign_id]['adsets_count'] = len(campaign_summary[campaign_id]['adsets'])
                campaign_summary[campaign_id]['adsets'] = list(campaign_summary[campaign_id]['adsets'])
            
            campaigns_count = len(campaign_summary)
            
            total_post_saves_value = sum([int(ad[23]) if ad[23] else 0 for ad in ads_data])  # ✅ แก้ index จาก 22 → 23
            
            result = {
                'ads_details': ads_details,
                'ads_total_media_cost': total_cost,  # This is correctly calculated from aggregated spend
                'ads_count': len(ads_details),
                'campaigns_count': campaigns_count,
                'adsets_count': len(set([ad[4] for ad in ads_data if ad[4]])),
                'campaign_summary': campaign_summary,
                'total_post_saves': total_post_saves_value
            }
            
            print(f"    🔍 DEBUG - Returning: total_cost=${total_cost:.2f}, ads_count={len(ads_details)}, total_post_saves={total_post_saves_value}")
            
            return result
                
        except Exception as e:
            print(f"❌ Error fetching ads data for {post_id}: {e}")
            return {'ads_details': [], 'ads_total_media_cost': 0, 'ads_count': 0, 'campaigns_count': 0, 'adsets_count': 0, 'campaign_summary': {}, 'total_post_saves': 0}
    
    def calculate_performance_score(self, data):
        """
        Calculate Performance Score (PFM Score v4.0 - TikTok-style Threshold)
        
        🎯 Score Range: 0.00 - ไม่จำกัด (เหมือน TikTok - ยิ่งดียิ่งสูง)
        
        📊 Interpretation Guide:
        - 1.50+ = 🔥 ดีมาก (Excellent) - ยิง ads เต็มงบ, scale up!
        - 1.00-1.49 = ✅ ดี (Good) - ไปต่อได้, ยิง ads ได้
        - 0.70-0.99 = ⚡ ปานกลาง (Average) - ใช้ได้, อาจปรับปรุง
        - 0.50-0.69 = ⚠️ ต่ำกว่าเกณฑ์ (Below Average) - ควรปรับปรุง
        - < 0.50 = ❌ ไม่ดี (Poor) - หยุดยิง ads, ทำใหม่
        
        🔧 Algorithm: Dynamic Benchmark (TikTok-inspired) - NO CAP!
        
        Key Features:
        - ✅ Fair กับทุก reach range (Dynamic targets)
        - ✅ Quality Score: Shares 40%, Saves 30%, Comments 20%, Likes 10%
        - ✅ Cost Efficiency Factor (0.5-1.5x multiplier)
        - ✅ Content Performance Bonus (0.0-0.5 bonus)
        - ✅ ไม่มี cap - content ที่เทพสุดๆ ได้คะแนนสูงไม่จำกัด
        """
        try:
            # Base metrics - convert to float to ensure compatibility
            impressions = float(data.get('impressions', 0) or 0)
            video_views = float(data.get('video_views', 0) or 0)
            likes = float(data.get('likes', 0) or 0)
            comments = float(data.get('comments', 0) or 0)
            shares = float(data.get('shares', 0) or 0)
            post_saves = float(data.get('post_saves', 0) or 0)
            clicks = float(data.get('clicks', 0) or 0)
            ads_cost = float(data.get('ads_total_media_cost', 0) or 0)
            ads_count = float(data.get('ads_count', 0) or 0)
            reach = float(data.get('impressions_unique', impressions) or impressions)
            video_duration = float(data.get('video_duration', 0) or 0)
            avg_watch_time = float(data.get('average_time_watched', 0) or 0)

            # 🎯 STEP 1: Dynamic Benchmark Targets (TikTok method)
            def get_engagement_targets(reach):
                """Dynamic engagement rate targets based on reach ranges"""
                if reach < 10000:
                    return {'comment_rate': 0.3, 'share_rate': 0.15, 'save_rate': 0.1, 'like_rate': 2.0}
                elif reach < 50000:
                    return {'comment_rate': 0.2, 'share_rate': 0.1, 'save_rate': 0.08, 'like_rate': 1.5}
                elif reach < 100000:
                    return {'comment_rate': 0.15, 'share_rate': 0.08, 'save_rate': 0.06, 'like_rate': 1.0}
                elif reach < 500000:
                    return {'comment_rate': 0.1, 'share_rate': 0.05, 'save_rate': 0.04, 'like_rate': 0.7}
                else:  # Mega viral posts
                    return {'comment_rate': 0.05, 'share_rate': 0.03, 'save_rate': 0.02, 'like_rate': 0.5}
            
            targets = get_engagement_targets(reach)
            
            # 🎯 STEP 2: Calculate Target Values
            target_comments = (reach * targets['comment_rate']) / 100
            target_shares = (reach * targets['share_rate']) / 100
            target_saves = (reach * targets['save_rate']) / 100
            target_likes = (reach * targets['like_rate']) / 100
            
            # 🎯 STEP 3: Normalize (ไม่มี cap - ยิ่งทำได้ดียิ่งได้คะแนนสูง)
            norm_comments = comments / max(target_comments, 1)
            norm_shares = shares / max(target_shares, 1)
            norm_saves = post_saves / max(target_saves, 1)
            norm_likes = likes / max(target_likes, 1)
            
            # 🎯 STEP 4: Quality Score (Facebook-optimized weights)
            # Range: 0.0 - ไม่จำกัด (ยิ่งทำได้ดียิ่งสูง เหมือน TikTok)
            quality_score = (
                norm_shares * 40 +      # Shares = viral indicator (highest weight)
                norm_saves * 30 +       # Saves = high intent (like TikTok bookmarks)
                norm_comments * 20 +    # Comments = engagement
                norm_likes * 10         # Likes = baseline
            ) / 100

            # 🎯 STEP 5: Cost Efficiency Factor (0.5 - 1.5)
            cost_factor = 1.0  # Default for organic
            
            if ads_cost > 0:
                weighted_eng = (shares * 10 + post_saves * 5 + comments * 1.5 + likes * 0.1)
                
                if weighted_eng > 0:
                    cost_per_engagement = ads_cost / weighted_eng
                    
                    # Cost efficiency mapping:
                    # CPE <= $0.10 → factor 1.5 (boost 50%)
                    # CPE $0.10-$0.30 → factor 1.3
                    # CPE $0.30-$0.50 → factor 1.0
                    # CPE > $0.50 → factor 0.5-1.0 (penalty)
                    if cost_per_engagement <= 0.10:
                        cost_factor = 1.5
                    elif cost_per_engagement <= 0.30:
                        cost_factor = 1.3
                    elif cost_per_engagement <= 0.50:
                        cost_factor = 1.0
                    else:
                        cost_factor = max(0.5, 1.0 - ((cost_per_engagement - 0.50) / 1.0))
                    
                    # 🚨 Diminishing Returns Penalty
                    if ads_cost > 500:
                        engagement_per_dollar = weighted_eng / ads_cost
                        if engagement_per_dollar < 1.0:
                            cost_factor *= (0.7 + (engagement_per_dollar * 0.3))
                    
                    if ads_cost > 1000:
                        engagement_per_dollar = weighted_eng / ads_cost
                        if engagement_per_dollar < 0.5:
                            cost_factor *= 0.7  # Additional 30% penalty
                else:
                    cost_factor = 0.5  # Penalty for spending but no engagement

            # 🎯 STEP 6: Content Performance Bonus (0.0 - 0.5)
            content_bonus = 0.0
            
            if video_duration > 0 and avg_watch_time > 0:
                completion_rate = min((avg_watch_time / 1000) / video_duration, 1.0)
                if completion_rate > 0.7:
                    content_bonus = 0.3
                elif completion_rate > 0.5:
                    content_bonus = 0.2
                elif completion_rate > 0.3:
                    content_bonus = 0.1
            else:
                if impressions > 0:
                    ctr = (clicks / impressions)
                    if ctr > 0.05:  # CTR > 5%
                        content_bonus = 0.3
                    elif ctr > 0.03:
                        content_bonus = 0.2
                    elif ctr > 0.02:
                        content_bonus = 0.1

            # 📊 Final PFM Score Calculation
            # Base: quality_score (ไม่จำกัด) × cost_factor (0.5-1.5) + content_bonus (0-0.5)
            pfm_score = (quality_score * cost_factor) + content_bonus
            
            # Organic viral bonus (ถ้า organic และ quality ดี)
            if ads_count == 0 and quality_score > 1.5:
                pfm_score *= 1.2
            
            # ไม่มี cap - ให้คะแนนสูงได้ตามความสามารถจริง (เหมือน TikTok)
            
            return round(pfm_score, 2)

        except Exception as e:
            print(f"❌ Error calculating performance score: {e}")
            import traceback
            traceback.print_exc()
            return 0.0
    
    def upsert_performance_record(self, post_data, insights, video_insights, ads_data):
        """Insert or update performance record - Handle both regular posts and orphaned videos"""
        
        # ⭐ Safety check: ensure all parameters are the correct type
        if not isinstance(insights, dict):
            print(f"    ⚠️  Warning: insights is {type(insights)}, converting to empty dict")
            insights = {}
        
        if not isinstance(video_insights, dict):
            print(f"    ⚠️  Warning: video_insights is {type(video_insights)}, converting to empty dict")
            video_insights = {}
        
        if not isinstance(ads_data, dict):
            print(f"    ⚠️  Warning: ads_data is {type(ads_data)}, converting to empty dict")
            ads_data = {}
        
        # Calculate derived metrics - รวม organic + ads
        organic_impressions = insights.get('impressions', 0)
        organic_reach = insights.get('impressions_unique', 0)  # ⭐ Organic reach
        organic_clicks = insights.get('clicks', 0)
        
        # Get ads data with proper reach handling
        # ⭐ Safely get ads_details - handle both dict and None/empty cases
        ads_details_list = ads_data.get('ads_details', []) if isinstance(ads_data, dict) else []
        if ads_details_list is None:
            ads_details_list = []
        
        # Ensure all items in ads_details are dicts
        ads_impressions = sum(ad.get('impressions', 0) for ad in ads_details_list if isinstance(ad, dict))
        ads_reach = max((ad.get('reach', 0) for ad in ads_details_list if isinstance(ad, dict)), default=0)  # ⭐ Ads reach
        ads_clicks = sum(ad.get('clicks', 0) for ad in ads_details_list if isinstance(ad, dict))
        
        # Combine organic + ads
        total_impressions = organic_impressions + ads_impressions
        total_clicks = organic_clicks + ads_clicks
        
        # ⭐ Reach calculation: Smart deduplication
        if ads_reach == 0:
            reach = organic_reach
        elif ads_reach <= organic_reach * 2:
            # Ads ไม่เยอะมาก → น่าจะซ้ำกันเยอะ ใช้ MAX
            reach = max(organic_reach, ads_reach)
        else:
            # Ads เยอะมาก → มีคนใหม่แน่ๆ Assume 30% overlap
            # ⭐ Convert to int/float to avoid Decimal + float error
            reach = int(float(organic_reach) + (float(ads_reach) * 0.7))
        
        # Debug reach calculation
        if ads_reach > 0:
            print(f"    📊 Reach Calculation:")
            print(f"       Organic reach: {organic_reach:,}")
            print(f"       Ads reach: {ads_reach:,}")
            print(f"       Combined reach: {reach:,}")
            print(f"       Method: {'organic only' if ads_reach == 0 else 'MAX (conservative)' if ads_reach <= organic_reach * 2 else 'deduplicated (70%)'}")
        
        # Calculate rates
        engagement_rate = 0
        ctr = 0
        
        if reach > 0:
            total_engagement = insights.get('likes', 0) + insights.get('comments', 0) + insights.get('shares', 0)
            engagement_rate = min(total_engagement / reach, 0.9999)  # Cap at 0.9999 to avoid DB overflow
        
        if total_impressions > 0:
            ctr = min(total_clicks / total_impressions, 0.9999)  # Cap at 0.9999 to avoid DB overflow
            
        # Debug CTR calculation
        if ads_clicks > 0 or organic_clicks > 0:
            print(f"    📊 CTR Calculation: {total_clicks:,} clicks / {total_impressions:,} impressions = {ctr:.4f} ({ctr*100:.2f}%)")
            print(f"       Organic: {organic_clicks:,} clicks, {organic_impressions:,} impressions")
            print(f"       Ads: {ads_clicks:,} clicks, {ads_impressions:,} impressions")
        
        # ⭐ Data Quality Validation
        warnings = []
        post_id = post_data[0] if isinstance(post_data, (tuple, list)) and len(post_data) > 0 else 'unknown'
        
        # Check 1: CTR สมเหตุสมผล
        if ctr > 0.20:  # CTR > 20% น่าสงสัย
            warnings.append(f"⚠️ High CTR: {ctr*100:.2f}% (อาจมีการนับซ้ำ)")
        
        # Check 2: Engagement rate สมเหตุสมผล
        if engagement_rate > 0.50:  # Engagement > 50% น่าสงสัย
            warnings.append(f"⚠️ High engagement: {engagement_rate*100:.2f}% (อาจมีการนับซ้ำ)")
        
        # Check 3: Reach vs Impressions
        if reach > total_impressions and total_impressions > 0:
            warnings.append(f"⚠️ Reach ({reach:,}) > Impressions ({total_impressions:,})")
        
        # Check 4: Frequency check
        if reach > 0:
            frequency = total_impressions / reach
            if frequency > 10:
                warnings.append(f"⚠️ Frequency {frequency:.2f} > 10 (คนเห็นมากเกินไป)")
        
        # Check 5: Ads metrics consistency
        if isinstance(ads_data, dict) and (ads_data.get('ads_count') or 0) > 0:
            ads_total_from_details = sum(ad.get('spend', 0) for ad in ads_details_list if isinstance(ad, dict))
            ads_total_reported = ads_data.get('ads_total_media_cost', 0)
            if abs(ads_total_from_details - ads_total_reported) > 0.01:
                warnings.append(f"⚠️ Ads spend mismatch: ${ads_total_from_details:.2f} vs ${ads_total_reported:.2f}")
            
            # Check CPM
            if ads_impressions > 1000:
                cpm = (ads_total_reported / ads_impressions) * 1000
                if cpm > 100:
                    warnings.append(f"⚠️ CPM ${cpm:.2f} > $100 (แพงผิดปกติ)")
                elif cpm < 0.10:
                    warnings.append(f"⚠️ CPM ${cpm:.2f} < $0.10 (ถูกผิดปกติ)")
        
        # Report warnings
        if warnings:
            print(f"    🚨 Data Quality Warnings for post {post_id}:")
            for warning in warnings:
                print(f"       {warning}")
        
        # Calculate total post saves (organic + ads) with enhanced tracking
        # 🎯 NOTE: Facebook organic post_saves metric is rarely available
        # - Video/Reels: Only ads post_saves (no organic metric)
        # - Photo posts: May have organic saves (depends on API permissions)
        organic_saves = insights.get('post_saves', 0) or 0
        ads_saves = ads_data.get('total_post_saves', 0) if isinstance(ads_data, dict) else 0
        
        # 🚨 CRITICAL: For video/reels, post_saves from insights might ALREADY include ads
        # Check if organic_saves suspiciously matches ads_saves (indicating duplicate counting)
        print(f"    🔍 DEBUG POST SAVES:")
        print(f"       - organic_saves (insights): {organic_saves}")
        print(f"       - ads_saves (from ads_data): {ads_saves}")
        print(f"       - ads_data type: {type(ads_data)}")
        print(f"       - ads_data keys: {list(ads_data.keys()) if isinstance(ads_data, dict) else 'N/A'}")
        print(f"       - Media type: {video_insights.get('media_type', 'unknown')}")
        
        # Smart deduplication: For videos, if organic_saves exists and matches ads pattern, don't double count
        if organic_saves > 0 and ads_saves > 0:
            # If organic and ads are close (within 20%), likely the same data
            ratio = min(organic_saves, ads_saves) / max(organic_saves, ads_saves) if max(organic_saves, ads_saves) > 0 else 0
            if ratio > 0.8:
                print(f"       ⚠️  DUPLICATE DETECTED: organic ({organic_saves}) ≈ ads ({ads_saves})")
                print(f"       ✅ Using ads_saves only: {ads_saves}")
                total_post_saves = ads_saves  # Use ads_saves as source of truth
            else:
                print(f"       ✅ Different sources, adding: {organic_saves} + {ads_saves} = {organic_saves + ads_saves}")
                total_post_saves = organic_saves + ads_saves
        else:
            total_post_saves = organic_saves + ads_saves
        
        print(f"       - FINAL total_post_saves: {total_post_saves}")
        
        # Enhanced post saves reporting with context
        if total_post_saves > 0:
            if organic_saves > 0:
                print(f"    💾 Post Saves: {organic_saves} organic + {ads_saves} ads = {total_post_saves} total")
            else:
                print(f"    💾 Post Saves: {ads_saves} ads (organic metric not available)")
        elif isinstance(ads_data, dict) and ads_data.get('ads_count', 0) > 0:
            print(f"    💾 Post Saves: None (no saves from organic or ads)")
        else:
            print(f"    💾 Post Saves: None (no ads data)")
        
        # Prepare data for performance score calculation
        # ⭐ Ensure all are dicts before unpacking
        safe_insights = insights if isinstance(insights, dict) else {}
        safe_video_insights = video_insights if isinstance(video_insights, dict) else {}
        safe_ads_data = ads_data if isinstance(ads_data, dict) else {}
        
        perf_data = {
            **safe_insights,
            **safe_video_insights,
            **safe_ads_data
        }
        performance_score = self.calculate_performance_score(perf_data)
        print(f"    📈 Performance Score: {performance_score:.1f}/100")
        
        # Determine post type and source with better validation
        post_type = 'post'
        source_type = post_data[12] if len(post_data) > 12 else 'regular_post'
        
        if source_type == 'orphaned_video':
            # Validate orphaned video data
            duration = post_data[8] if len(post_data) > 8 and post_data[8] else 0
            if duration and duration > 60:
                post_type = 'video'
            else:
                post_type = 'reel'
            print(f"    🎬 Processing orphaned video as {post_type} (duration: {duration}s)")
        elif len(post_data) > 7 and post_data[7]:  # video_id exists
            duration = post_data[8] if len(post_data) > 8 and post_data[8] else 0
            post_type = 'video' if duration and duration > 60 else 'reel'
        elif len(post_data) > 10 and post_data[10]:  # attachment_type exists
            post_type = post_data[10]  # photo, video, link, etc.
        
        # Build caption (message หรือ video title)
        caption = post_data[2] or (post_data[9] if len(post_data) > 9 else '') or ''
        
        # Build URL - แก้ไขให้เป็น full URL เสมอ
        permalink = post_data[3]
        if permalink:
            # ถ้า permalink เป็น relative URL (/reel/...) ให้เติม https://www.facebook.com
            if permalink.startswith('/'):
                final_url = f"https://www.facebook.com{permalink}"
            else:
                final_url = permalink
        else:
            # ถ้าไม่มี permalink ให้สร้างจาก page_id + post_id
            final_url = self.build_permalink_url(post_data[1], post_data[0])

        # Handle thumbnail URL - Enhanced media linking and API endpoint generation
        thumbnail_url = post_data[5] if len(post_data) > 5 else None
        local_thumbnail_id = post_data[6] if len(post_data) > 6 else None
        video_id = post_data[7] if len(post_data) > 7 else None

        # 🎯 ถ้าไม่มี video_id ให้ลองดึงจาก URL pattern /reel/(\d+)/ หรือ /videos/(\d+)/
        if not video_id and final_url:
            import re
            match = re.search(r'/(reel|videos)/(\d+)', final_url)
            if match:
                video_id = match.group(2)
                print(f"    🔍 Extracted video_id {video_id} from URL pattern")

        # 🎯 ถ้าไม่มี video_id ให้ลองหาจาก post_id ใน facebook_video_posts
        # (บาง post อาจมาจาก facebook_posts แต่จริงๆแล้วเป็น video post)
        if not video_id:
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT video_id, local_picture_id, picture
                        FROM facebook_video_posts 
                        WHERE post_id = %s 
                        LIMIT 1
                    """, (post_data[0],))
                    result = cursor.fetchone()
                    if result:
                        video_id = result[0]
                        # ถ้าไม่มี local_thumbnail_id ให้เอาจาก video_posts ด้วย
                        if not local_thumbnail_id and result[1]:
                            local_thumbnail_id = result[1]
                            print(f"    ✅ Found local_thumbnail_id from video_posts: {local_thumbnail_id}")
                        if not thumbnail_url and result[2]:
                            thumbnail_url = result[2]
                        print(f"    🔍 Found video_id {video_id} for post {post_data[0]} via post_id lookup")
            except Exception as e:
                print(f"    ⚠️  Error looking up video_id: {e}")

        # 🎯 ถ้าไม่มี thumbnail แต่มี video_id ให้ลองค้นหาจาก video_id
        if not local_thumbnail_id and video_id:
            print(f"    🔍 Searching for thumbnail using video_id: {video_id}")
            video_thumbnail = self.find_thumbnail_by_video_id(video_id)
            if video_thumbnail:
                local_thumbnail_id = video_thumbnail['local_thumbnail_id']
                if not thumbnail_url:
                    thumbnail_url = video_thumbnail['thumbnail_url']
                print(f"    ✅ Linked thumbnail from video_id {video_id} to post {post_data[0]}")
            else:
                print(f"    ⚠️  No thumbnail found for video_id {video_id}")
        elif not video_id and not local_thumbnail_id:
            print(f"    ℹ️  No video_id available to search for thumbnail")

        # 🔍 Enhanced media search and URL generation with local priority
        if thumbnail_url and not local_thumbnail_id:
            # ค้นหา media ที่มีอยู่แล้ว
            found_media_id = self.find_existing_media_for_post(post_data[0], thumbnail_url)
            if found_media_id:
                local_thumbnail_id = found_media_id
                print(f"    🔗 Linked existing media: {local_thumbnail_id}")
                
                # อัปเดต thumbnail_url เป็น API endpoint ถ้าเป็น database storage
                try:
                    with self.conn.cursor() as cursor:
                        cursor.execute("""
                            SELECT is_stored_in_db, public_url FROM media_storage 
                            WHERE id = %s
                        """, (local_thumbnail_id,))
                        media_result = cursor.fetchone()
                        
                        if media_result:
                            is_stored_in_db, public_url = media_result
                            if is_stored_in_db:
                                # ใช้ API endpoint สำหรับ database-stored media
                                thumbnail_url = f"http://localhost:8000/media/{local_thumbnail_id}"
                                print(f"    🌐 Updated to API endpoint: {thumbnail_url}")
                            elif public_url:
                                # ใช้ public_url ถ้ามี
                                thumbnail_url = public_url
                                print(f"    🔗 Using public URL: {thumbnail_url[:60]}...")
                            # else: keep original thumbnail_url
                        
                except Exception as e:
                    print(f"    ⚠️  Could not check media storage type: {e}")
            else:
                print(f"    ❓ No local media found for {post_data[0]} - keeping original URL")
                # สำหรับ URLs ที่ยังไม่ได้ดาวน์โหลด ให้แนะนำการรัน sync scripts
                if 'fbcdn.net' in (thumbnail_url or ''):
                    print(f"    💡 Suggestion: Run video sync script to download and store this thumbnail")
        elif local_thumbnail_id:
            # มี local_thumbnail_id แล้ว - สร้าง local API endpoint
            try:
                with self.conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT local_filename, download_status 
                        FROM media_storage 
                        WHERE id = %s AND download_status = 'success'
                    """, (local_thumbnail_id,))
                    media_result = cursor.fetchone()
                    
                    if media_result:
                        local_filename, status = media_result
                        # Force local thumbnail URL for consistency
                        thumbnail_url = f"http://localhost:8000/media/{local_filename}"
                        print(f"    📸 Using local thumbnail: {local_filename}")
                    cursor.execute("""
                        SELECT is_stored_in_db, public_url FROM media_storage 
                        WHERE id = %s
                    """, (local_thumbnail_id,))
                    media_result = cursor.fetchone()
                    
                    if media_result:
                        is_stored_in_db, public_url = media_result
                        if is_stored_in_db:
                            # อัปเดต URL เป็น API endpoint
                            thumbnail_url = f"http://localhost:8000/media/{local_thumbnail_id}"
                            print(f"    🌐 Generated API endpoint: {thumbnail_url}")
                        elif public_url and not thumbnail_url:
                            # ใช้ public_url ถ้าไม่มี thumbnail_url
                            thumbnail_url = public_url
                            print(f"    🔗 Using stored public URL")
                    
            except Exception as e:
                print(f"    ⚠️  Could not generate API endpoint: {e}")
        
        # 🛡️ Check if we should preserve existing ads data
        preserve_ads = ads_data.get('preserve_existing', False) if isinstance(ads_data, dict) else False
        
        # ✅ Modified query - Handle ads data preservation
        if preserve_ads:
            # Don't update ads columns if we're preserving existing data
            query = """
            INSERT INTO facebook_posts_performance (
                post_id, channel_acc_id, post_type, url, caption, thumbnail_url, local_thumbnail_id,
                video_duration, video_views, total_time_watched, average_time_watched,
                impressions, impressions_unique, reach, clicks, likes, comments, shares, reactions,
                performance_score, engagement_rate, ctr,
                ads_details, ads_total_media_cost, ads_count, total_post_saves,
                create_time, update_time, last_sync_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, CURRENT_TIMESTAMP
            ) ON CONFLICT (post_id) 
            DO UPDATE SET
                post_type = EXCLUDED.post_type,
                caption = EXCLUDED.caption,
                thumbnail_url = EXCLUDED.thumbnail_url,
                local_thumbnail_id = EXCLUDED.local_thumbnail_id,
                video_duration = EXCLUDED.video_duration,
                video_views = EXCLUDED.video_views,
                total_time_watched = EXCLUDED.total_time_watched,
                average_time_watched = EXCLUDED.average_time_watched,
                impressions = EXCLUDED.impressions,
                impressions_unique = EXCLUDED.impressions_unique,
                reach = EXCLUDED.reach,
                clicks = EXCLUDED.clicks,
                likes = EXCLUDED.likes,
                comments = EXCLUDED.comments,
                shares = EXCLUDED.shares,
                reactions = EXCLUDED.reactions,
                performance_score = EXCLUDED.performance_score,
                engagement_rate = EXCLUDED.engagement_rate,
                ctr = EXCLUDED.ctr,
                total_post_saves = EXCLUDED.total_post_saves,
                update_time = EXCLUDED.update_time,
                last_sync_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """
        else:
            # Normal update including ads data - ป้องกัน SKU หาย
            query = """
            INSERT INTO facebook_posts_performance (
                post_id, channel_acc_id, post_type, url, caption, thumbnail_url, local_thumbnail_id,
                video_duration, video_views, total_time_watched, average_time_watched,
                impressions, impressions_unique, reach, clicks, likes, comments, shares, reactions,
                performance_score, engagement_rate, ctr,
                ads_details, ads_total_media_cost, ads_count, total_post_saves,
                create_time, update_time, last_sync_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, CURRENT_TIMESTAMP
            ) ON CONFLICT (post_id) 
            DO UPDATE SET
                post_type = EXCLUDED.post_type,
                url = EXCLUDED.url,
                caption = EXCLUDED.caption,
                thumbnail_url = EXCLUDED.thumbnail_url,
                local_thumbnail_id = EXCLUDED.local_thumbnail_id,
                video_duration = EXCLUDED.video_duration,
                video_views = EXCLUDED.video_views,
                total_time_watched = EXCLUDED.total_time_watched,
                average_time_watched = EXCLUDED.average_time_watched,
                impressions = EXCLUDED.impressions,
                impressions_unique = EXCLUDED.impressions_unique,
                reach = EXCLUDED.reach,
                clicks = EXCLUDED.clicks,
                likes = EXCLUDED.likes,
                comments = EXCLUDED.comments,
                shares = EXCLUDED.shares,
                reactions = EXCLUDED.reactions,
                performance_score = EXCLUDED.performance_score,
                engagement_rate = EXCLUDED.engagement_rate,
                ctr = EXCLUDED.ctr,
                ads_details = EXCLUDED.ads_details,
                ads_total_media_cost = EXCLUDED.ads_total_media_cost,
                ads_count = EXCLUDED.ads_count,
                total_post_saves = EXCLUDED.total_post_saves,
                -- 🛡️ ป้องกัน SKU หาย: ใช้ค่าเดิมถ้ามี
                primary_product_sku = COALESCE(facebook_posts_performance.primary_product_sku, EXCLUDED.primary_product_sku),
                products = COALESCE(facebook_posts_performance.products, EXCLUDED.products),
                update_time = EXCLUDED.update_time,
                last_sync_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            """
        
        try:
            with self.conn.cursor() as cursor:
                # 🛡️ Prepare parameters based on preserve_ads flag
                base_params = [
                    post_data[0],  # post_id
                    post_data[1],  # page_id (channel_acc_id)
                    post_type,
                    final_url,     # ใช้ permalink_url
                    caption,
                    thumbnail_url, # ใช้ picture_url เป็น thumbnail (อาจเป็น local path แล้ว)
                    local_thumbnail_id,  # local_picture_id (อาจเป็น UUID ใหม่)
                    post_data[8],  # video_duration
                    video_insights.get('video_views', 0),
                    video_insights.get('total_time_watched', 0),
                    video_insights.get('average_time_watched', 0),
                    total_impressions,  # ใช้ total (organic + ads)
                    insights.get('impressions_unique', 0),
                    reach,
                    total_clicks,  # ใช้ total (organic + ads)
                    insights.get('likes', 0),
                    insights.get('comments', 0),
                    insights.get('shares', 0),
                    json.dumps(insights.get('reactions'), ensure_ascii=False) if insights.get('reactions') else None,
                    round(performance_score, 2),
                    round(engagement_rate, 4),
                    round(ctr, 4)
                ]
                
                # Add ads parameters only if not preserving
                if preserve_ads:
                    # For preserve mode, we still need to provide ads values for INSERT (in case it's a new record)
                    # but the ON CONFLICT update won't touch ads columns
                    ads_params = [None, 0, 0, total_post_saves]  # Default values for new records + total_post_saves
                    base_params.extend(ads_params)
                else:
                    # Convert ads_details to proper JSON format
                    ads_details_json = None
                    if isinstance(ads_data, dict) and ads_data.get('ads_details') and len(ads_data.get('ads_details')) > 0:
                        ads_details_json = json.dumps(ads_data.get('ads_details'), ensure_ascii=False, default=str)
                    
                    ads_params = [
                        ads_details_json,
                        ads_data.get('ads_total_media_cost', 0) if isinstance(ads_data, dict) else 0,
                        ads_data.get('ads_count', 0) if isinstance(ads_data, dict) else 0,
                        total_post_saves
                    ]
                    base_params.extend(ads_params)
                
                # Add timestamp parameters
                time_params = [
                    post_data[4],  # created_time
                    post_data[4]   # updated_time (same as created for now)
                ]
                base_params.extend(time_params)
                
                cursor.execute(query, base_params)
            return True
        except psycopg2.IntegrityError as e:
            if "foreign key constraint" in str(e) and "post_id" in str(e):
                print(f"⚠️  Warning: Post {post_data[0]} not found in facebook_posts table - skipping")
                return False
            else:
                print(f"❌ Database integrity error for {post_data[0]}: {e}")
                return False
        except Exception as e:
            print(f"❌ Error upserting performance record for {post_data[0]}: {e}")
            return False
    
    def update_ads_post_id(self):
        """Update ads with missing post_id by fetching from Facebook API - integrated version"""
        print("\n🔧 Updating ads with missing post_id...")
        
        try:
            # Get FB token
            fb_token = os.getenv("FB_USER_ACCESS_TOKEN")
            if fb_token:
                fb_token = fb_token.split(',')[0]  # Use first token
            else:
                print("⚠️  No Facebook token found, skipping ads update")
                return
            
            # Check current status first
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN post_id IS NOT NULL AND post_id != '' THEN 1 END) as with_post_id
                    FROM facebook_ads
                """)
                total, with_post_id = cur.fetchone()
                percentage = (with_post_id / total * 100) if total > 0 else 0
                
                # If already good, skip
                if percentage >= 95:
                    print(f"✅ Ads connection already good: {with_post_id:,}/{total:,} ({percentage:.1f}%)")
                    return
            
            # Find ads needing post_id updates (no limit - process all)
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT ad_id, creative
                    FROM facebook_ads 
                    WHERE creative IS NOT NULL 
                      AND (post_id IS NULL OR post_id = '')
                    ORDER BY created_time DESC
                """)
                
                ads_to_update = cur.fetchall()
                
            if not ads_to_update:
                print("✅ All ads already have post_id")
                return
                
            print(f"📊 Found {len(ads_to_update)} ads needing post_id updates")
            updated_count = 0
            
            for i, (ad_id, creative_json) in enumerate(ads_to_update, 1):
                try:
                    creative_data = json.loads(creative_json) if isinstance(creative_json, str) else creative_json
                    
                    if isinstance(creative_data, dict) and 'id' in creative_data:
                        creative_id = creative_data['id']
                        
                        # Fetch from Facebook API
                        url = f"https://graph.facebook.com/v22.0/{creative_id}"
                        params = {
                            'fields': 'object_story_id,effective_object_story_id',
                            'access_token': fb_token
                        }
                        
                        response = requests.get(url, params=params, timeout=10)
                        
                        if response.status_code == 200:
                            data = response.json()
                            post_id = data.get('effective_object_story_id') or data.get('object_story_id')
                            
                            if post_id:
                                # Update database
                                with self.conn.cursor() as cur:
                                    cur.execute("""
                                        UPDATE facebook_ads 
                                        SET post_id = %s, updated_at = NOW()
                                        WHERE ad_id = %s
                                    """, (post_id, ad_id))
                                    self.conn.commit()
                                
                                updated_count += 1
                                if i % 20 == 0:
                                    print(f"  📊 Progress: {i}/{len(ads_to_update)} processed, {updated_count} updated")
                        
                        # Rate limiting
                        time.sleep(0.05)
                        
                except Exception as e:
                    continue  # Skip problematic ads
                    
            print(f"✅ Updated {updated_count} ads with post_id")
            
            # Show improvement
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN post_id IS NOT NULL AND post_id != '' THEN 1 END) as with_post_id
                    FROM facebook_ads
                """)
                
                total, with_post_id = cur.fetchone()
                percentage = (with_post_id / total * 100) if total > 0 else 0
                print(f"📊 Ads linkage now: {with_post_id:,}/{total:,} ({percentage:.1f}%)")
            
        except Exception as e:
            print(f"⚠️  Ads update error: {e}")
    
    def cleanup_duplicate_and_video_posts(self):
        """ลบ video posts ที่มี post_id เป็นตัวเลขอย่างเดียว (video_id) ถ้ามี record ที่ถูกต้อง (post_id แบบมี _)"""
        print(f"\n🧹 Cleaning up duplicate video posts...")
        
        try:
            with self.conn.cursor() as cursor:
                # ลบ records ที่มี post_id เป็นตัวเลขอย่างเดียว (video_id) 
                # เก็บเฉพาะ records ที่มี post_id แบบ page_id_postid (มีขีด _)
                cleanup_query = """
                DELETE FROM facebook_posts_performance
                WHERE post_id ~ '^\\d+$'  -- post_id เป็นตัวเลขอย่างเดียว (video_id)
                  AND url ~ '/(reel|videos)/\\d+'  -- เป็น video post
                  AND EXISTS (
                      -- มี record อื่นที่เป็น video เดียวกัน (มี _ ใน post_id)
                      SELECT 1 
                      FROM facebook_posts_performance p2
                      WHERE p2.post_id LIKE '%' || CHR(95) || '%'  -- post_id แบบมีขีด _ (ใช้ CHR(95) แทน escape)
                        AND p2.url LIKE '%/' || facebook_posts_performance.post_id || '%'
                  )
                RETURNING post_id
                """
                
                cursor.execute(cleanup_query)
                deleted_posts = cursor.fetchall()
                deleted_count = len(deleted_posts)
                
                if deleted_count > 0:
                    print(f"  ✅ Deleted {deleted_count} duplicate video post records:")
                    for post in deleted_posts[:10]:  # แสดงเฉพาะ 10 ตัวแรก
                        print(f"     - {post[0]}")
                    if deleted_count > 10:
                        print(f"     ... and {deleted_count - 10} more")
                else:
                    print(f"  ✅ No duplicate video posts found")
                
                return True
                
        except Exception as e:
            print(f"❌ Error during cleanup: {e}")
            traceback.print_exc()
            return False

    def sync_posts(self, days_back=None, post_id=None, force_local_thumbnails=False, cleanup_first=False):
        """Main sync process with enhanced local thumbnail prioritization"""
        print(f"\n🔄 Starting Facebook Posts Performance Sync...")
        
        # 🔧 Step 0.5: Populate video-promoted mapping (for bulk sync only)
        if not post_id:  # Only run for bulk sync, not single post
            print("\n🔗 Building video-promoted post mapping...")
            self.populate_video_promoted_mapping()
        
        # 🔧 Step 1: Update ads post_id linkage first (for bulk sync only)
        if not post_id:  # Only run for bulk sync, not single post
            self.update_ads_post_id()
        
        # 🧹 Step 2: ลบ duplicate video posts อัตโนมัติ (bulk sync เท่านั้น)
        if not post_id:  # Only run cleanup for bulk sync
            self.cleanup_duplicate_and_video_posts()
        
        # ทำความสะอาดข้อมูลก่อนถ้าต้องการ (ถ้ามี --cleanup flag)
        if cleanup_first:
            if not self.cleanup_duplicate_and_video_posts():
                print("⚠️  Cleanup failed, continuing with sync...")
        
        if post_id:
            print(f"📝 Syncing single post: {post_id}")
        elif days_back:
            print(f"📅 Syncing posts from last {days_back} days")
        else:
            print(f"📊 Syncing all posts")
            
        if force_local_thumbnails:
            print(f"🖼️  Priority: Force local thumbnails over Facebook CDN")
        
        posts = self.get_posts_to_sync(days_back, post_id)
        print(f"📄 Found {len(posts)} posts to process")
        
        for post_data in posts:
            try:
                post_id = post_data[0]
                print(f"\n  📝 Processing post: {post_id}")
                
                # Get insights
                insights = self.get_post_insights(post_id)
                print(f"    📊 Insights: {insights.get('impressions', 0)} impressions, {insights.get('likes', 0)} likes")
                
                # Get video insights if it's a video post
                video_insights = {}
                video_id = post_data[7] if len(post_data) > 7 and post_data[7] else self.extract_video_id_from_url(post_data[3])
                if video_id and str(video_id).isdigit():
                    try:
                        video_insights = self.get_video_insights(video_id)
                        if video_insights.get('video_views', 0) > 0:
                            print(f"    🎬 Video ID {video_id}: {video_insights.get('video_views', 0)} views")
                        
                        # 🎯 NEW: Get video engagement from JSON fields if needed
                        # Only for video posts that don't have engagement data from post_insights
                        if insights.get('likes', 0) == 0 and insights.get('comments', 0) == 0:
                            video_engagement = self.get_video_post_engagement(video_id)
                            if video_engagement.get('likes', 0) > 0 or video_engagement.get('comments', 0) > 0:
                                print(f"    💙 Merging video engagement: {video_engagement['likes']} likes, {video_engagement['comments']} comments, {video_engagement['shares']} shares")
                                # Merge video engagement into insights dict
                                insights['likes'] = video_engagement.get('likes', 0)
                                insights['comments'] = video_engagement.get('comments', 0)
                                insights['shares'] = video_engagement.get('shares', 0)
                        
                    except Exception as e:
                        print(f"    ⚠️  Video insights error for {video_id}: {e}")
                        video_insights = {}
                
                # Get ads data
                ads_data = self.get_ads_data(post_id)
                
                # 🔧 แก้ไขตรงนี้ - Handle None values when preserving existing data
                ads_total_cost = (ads_data.get('ads_total_media_cost') or 0) if isinstance(ads_data, dict) else 0
                ads_count = (ads_data.get('ads_count') or 0) if isinstance(ads_data, dict) else 0
                campaigns_count = (ads_data.get('campaigns_count') or 0) if isinstance(ads_data, dict) else 0
                
                print(f"    🔍 DEBUG - ads_data returned: ads_count={ads_count}, total_cost=${ads_total_cost:.2f}")
                
                # Check if ads data is valid (not preserving)
                if ads_count > 0:
                    print(f"    💰 Ads: {ads_count} ads across {campaigns_count} campaigns, ${ads_total_cost:.2f} spent")
                    
                    if isinstance(ads_data, dict) and ads_data.get('campaign_summary'):
                        for campaign_id, summary in ads_data['campaign_summary'].items():
                            print(f"      📊 {summary['campaign_name']}: ${summary['total_spend']:.2f} ({summary['ad_count']} ads)")
                else:
                    print(f"    💰 Ads: No paid promotion")
                
                # 🔧 อัปเดต class statistics ก่อน upsert
                self.total_ads += ads_count
                self.total_campaigns += campaigns_count  
                self.total_spend += ads_total_cost
                
                print(f"    🔍 DEBUG - Updated totals: ads={self.total_ads}, campaigns={self.total_campaigns}, spend=${self.total_spend:.2f}")
                
                # Upsert performance record
                if self.upsert_performance_record(post_data, insights, video_insights, ads_data):
                    self.updated_posts += 1
                    print(f"    ✅ Updated performance record")
                else:
                    self.errors += 1
                
                self.processed_posts += 1
                
            except Exception as e:
                print(f"    ❌ Error processing post {post_data[0]}: {e}")
                import traceback
                print(f"    📍 Traceback:")
                traceback.print_exc()
                self.errors += 1
        
        # Enhanced Summary
        duration = (datetime.now() - self.start_time).total_seconds()
        print(f"\n📊 Sync Summary:")
        print(f"  📄 Posts processed: {self.processed_posts}")
        print(f"  ✅ Successfully updated: {self.updated_posts}")
        print(f"  ❌ Errors: {self.errors}")
        if self.errors > 0:
            error_rate = (self.errors / max(self.processed_posts, 1)) * 100
            print(f"  📉 Error rate: {error_rate:.1f}%")
        print(f"  💰 Total ads processed: {self.total_ads}")
        print(f"  🎯 Total campaigns involved: {self.total_campaigns}")
        print(f"  💵 Total ad spend tracked: ${self.total_spend:.2f}")
        print(f"  ⏱️  Duration: {duration:.1f}s ({duration/60:.1f} minutes)")
        print(f"  📈 Processing rate: {self.processed_posts/max(duration, 1):.1f} posts/second")
        
        # Recommendations
        if self.errors > self.updated_posts * 0.1:  # More than 10% error rate
            print(f"\n⚠️  High error rate detected. Consider:")
            print(f"     • Checking database connectivity")
            print(f"     • Running ads sync if ads data is missing")
            print(f"     • Reviewing error messages above")
        elif not self.ads_connection_verified and self.total_ads == 0:
            print(f"\n💡 Tip: Run 'python update_ads_post_id.py' to improve ads linkage")
            print(f"💡 Then: Run 'python sync_all_facebook_data.py' for complete ads integration")
        
        # Additional recommendations for data completeness
        if self.processed_posts > 0:
            success_rate = (self.updated_posts / self.processed_posts) * 100
            print(f"\n📈 Data Quality Summary:")
            print(f"  ✅ Success rate: {success_rate:.1f}%")
            
            if success_rate < 95:
                print(f"  🔧 Consider running:")
                print(f"     • python sync_fb_video_posts_to_db.py --days-back {days_back or 60}")
                print(f"     • python sync_facebook_complete.py --days-back {days_back or 60}")
                print(f"     • python update_ads_post_id.py")
    
    def __del__(self):
        """Clean up database connection"""
        if self.conn:
            self.conn.close()

def main():
    """Main function with enhanced command line options"""
    # Fix Windows Unicode encoding issue
    import sys
    if sys.platform.startswith('win'):
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    print("🎯 Facebook Posts Performance Sync")
    print("=" * 60)
    print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Parse command line arguments
    days_back = None
    post_id = None
    recalculate = False
    health_check = False
    media_report = False
    force_local_thumbnails = False
    cleanup_first = False
    
    for i, arg in enumerate(sys.argv):
        if arg == '--days-back' and i + 1 < len(sys.argv):
            days_back = int(sys.argv[i + 1])
        elif arg == '--post-id' and i + 1 < len(sys.argv):
            post_id = sys.argv[i + 1]
        elif arg == '--recalculate':
            recalculate = True
        elif arg == '--health-check':
            health_check = True
        elif arg == '--media-report':
            media_report = True
        elif arg == '--force-local-thumbnails':
            force_local_thumbnails = True
        elif arg == '--cleanup':
            cleanup_first = True
        elif arg == '--help' or arg == '-h':
            print_help()
            return
    
    # Initialize sync process
    sync = FacebookPostsPerformanceSync()
    
    if not sync.connect_db():
        return
    
    try:
        # Handle different modes
        if health_check:
            print(f"\n🏥 Running Health Check...")
            sync.print_media_status_report()
            
        elif media_report:
            print(f"\n📊 Generating Media Report...")
            sync.print_media_status_report()
            
            # แสดงข้อแนะนำสำหรับ posts ที่ขาด media
            posts_needing_media = sync.find_posts_with_missing_media(100)
            sync.suggest_media_sync_commands(posts_needing_media)
            
        else:
            # Normal sync process with enhanced options
            if force_local_thumbnails:
                sync.force_local_thumbnails = True
                print(f"🖼️  Enabled: Force local thumbnails mode")
            
            sync.sync_posts(days_back=days_back, post_id=post_id, force_local_thumbnails=force_local_thumbnails, cleanup_first=cleanup_first)
            
        print(f"\n🎉 Operation completed successfully!")
        
    except KeyboardInterrupt:
        print(f"\n⚠️  Operation interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"🏁 Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

def print_help():
    """แสดงคำแนะนำการใช้งาน"""
    help_text = """
🎯 Facebook Posts Performance Sync - Usage Guide

📋 Basic Sync Commands:
  python sync_facebook_posts_performance.py                    # Sync ทั้งหมด
  python sync_facebook_posts_performance.py --days-back 30     # Sync 30 วันล่าสุด
  python sync_facebook_posts_performance.py --post-id POST_ID  # Sync post เดียว
  python sync_facebook_posts_performance.py --recalculate      # คำนวณ performance ใหม่

📊 Status & Reports:
  python sync_facebook_posts_performance.py --health-check    # ตรวจสอบสุขภาพระบบ
  python sync_facebook_posts_performance.py --media-report    # รายงานสถานะ media storage

🖼️  Enhanced Options:
  python sync_facebook_posts_performance.py --force-local-thumbnails  # บังคับใช้ local thumbnails
  python sync_facebook_posts_performance.py --days-back 30 --force-local-thumbnails  # Sync + force local
  python sync_facebook_posts_performance.py --cleanup  # ทำความสะอาดข้อมูลซ้ำและ video posts ก่อน sync
  python sync_facebook_posts_performance.py --days-back 30 --cleanup  # Cleanup + sync 30 วัน

🆘 Help:
  python sync_facebook_posts_performance.py --help           # แสดงคำแนะนำนี้

📝 Important Notes:
  • This script aggregates data from other tables into facebook_posts_performance
  • For missing media, run the suggested sync commands first:
    - sync_fb_video_posts_to_db.py (for video thumbnails)
    - sync_facebook_complete.py (for photo attachments)
  • Then re-run this script to link the media properly

📝 Examples:
  # Check system health and get media sync recommendations
  python sync_facebook_posts_performance.py --health-check

  # Generate detailed media report with sync suggestions
  python sync_facebook_posts_performance.py --media-report
    """
    print(help_text)

if __name__ == "__main__":
    main()