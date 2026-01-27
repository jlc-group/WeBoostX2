#!/usr/bin/env python3
"""
Script to sync Facebook Video Posts and their insights to PostgreSQL database
Compliant with Facebook Graph API v23.0 documentation
Handles: Video posts, Video insights, Video metrics, Reels insights

Features:
- Fetches videos from Facebook Pages (default: 6 months back)
- Downloads video thumbnails to local media storage via FacebookMediaManager
- Detects and handles both regular videos and Reels content
- Stores video metadata, insights, and media URLs in PostgreSQL
- Rate limiting and error handling for stable API performance

Usage:
  python sync_fb_video_posts_to_db.py                    # Default: 6 months back (180 days)
  python sync_fb_video_posts_to_db.py --days-back 30     # 1 month back
  python sync_fb_video_posts_to_db.py --days-back 90     # 3 months back
  python sync_fb_video_posts_to_db.py --all              # All available data (no limit)

Tables: facebook_video_posts, facebook_video_insights, facebook_reels_insights, media_storage
"""

import os
import json
import time
import requests
import psycopg2
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database_media_manager import DatabaseMediaManager

# Load environment variables
load_dotenv()

# Facebook API Configuration
FB_PAGE_ACCESS_TOKENS = os.getenv("FB_PAGE_ACCESS_TOKENS", "").split(',')
FB_PAGE_IDS = os.getenv("FB_PAGE_IDS", "").split(',')

# Database Configuration
PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

def get_db_connection():
    """Get database connection"""
    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD
    )

# Initialize Database-Only Media Manager
media_manager = DatabaseMediaManager()

def safe_convert_datetime(value):
    """Safely convert datetime string to timestamp"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    except:
        return None

def safe_convert_float(value):
    """Safely convert value to float"""
    if not value:
        return None
    try:
        return float(value)
    except:
        return None

def safe_convert_int(value):
    """Safely convert value to integer"""
    if not value:
        return None
    try:
        return int(value)
    except:
        return None

def insert_video_post(conn, video_data):
    """Insert or update video post data in database with local media support"""
    query = """
    INSERT INTO facebook_video_posts (
        video_id, post_id, page_id, created_time, permalink_url,
        source, length, title, description, picture,
        local_picture_id,
        created_at, updated_at
    ) VALUES (
        %(video_id)s, %(post_id)s, %(page_id)s, %(created_time)s, %(permalink_url)s,
        %(source)s, %(length)s, %(title)s, %(description)s, %(picture)s,
        %(local_picture_id)s,
        NOW(), NOW()
    ) ON CONFLICT (video_id) 
    DO UPDATE SET
        post_id = EXCLUDED.post_id,
        permalink_url = EXCLUDED.permalink_url,
        source = EXCLUDED.source,
        length = EXCLUDED.length,
        title = EXCLUDED.title,
        description = EXCLUDED.description,
        picture = EXCLUDED.picture,
        local_picture_id = EXCLUDED.local_picture_id,
        updated_at = NOW()
    """
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, video_data)
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error inserting video {video_data.get('video_id')}: {e}")
        conn.rollback()
        return False

def insert_video_insights(conn, insights_data):
    """Insert or update regular video insights data in database"""
    query = """
    INSERT INTO facebook_video_insights (
        id, video_id, date_start, date_stop,
        total_video_views, total_video_views_unique, total_video_complete_views,
        total_video_complete_views_unique, total_video_impressions, total_video_impressions_unique,
        total_video_avg_time_watched, total_video_view_total_time,
        total_video_10s_views, total_video_10s_views_unique, total_video_15s_views, total_video_30s_views,
        total_video_views_autoplayed, total_video_views_clicked_to_play,
        total_video_views_organic, total_video_views_paid,
        total_video_reactions_by_type_total, total_video_stories_by_action_type
    ) VALUES (
        %(id)s, %(video_id)s, %(date_start)s, %(date_stop)s,
        %(total_video_views)s, %(total_video_views_unique)s, %(total_video_complete_views)s,
        %(total_video_complete_views_unique)s, %(total_video_impressions)s, %(total_video_impressions_unique)s,
        %(total_video_avg_time_watched)s, %(total_video_view_total_time)s,
        %(total_video_10s_views)s, %(total_video_10s_views_unique)s, %(total_video_15s_views)s, %(total_video_30s_views)s,
        %(total_video_views_autoplayed)s, %(total_video_views_clicked_to_play)s,
        %(total_video_views_organic)s, %(total_video_views_paid)s,
        %(total_video_reactions_by_type_total)s, %(total_video_stories_by_action_type)s
    ) ON CONFLICT (video_id, date_start, date_stop)
    DO UPDATE SET
        total_video_views = EXCLUDED.total_video_views,
        total_video_views_unique = EXCLUDED.total_video_views_unique,
        total_video_complete_views = EXCLUDED.total_video_complete_views,
        total_video_complete_views_unique = EXCLUDED.total_video_complete_views_unique,
        total_video_impressions = EXCLUDED.total_video_impressions,
        total_video_impressions_unique = EXCLUDED.total_video_impressions_unique,
        total_video_avg_time_watched = EXCLUDED.total_video_avg_time_watched,
        total_video_view_total_time = EXCLUDED.total_video_view_total_time,
        total_video_10s_views = EXCLUDED.total_video_10s_views,
        total_video_10s_views_unique = EXCLUDED.total_video_10s_views_unique,
        total_video_15s_views = EXCLUDED.total_video_15s_views,
        total_video_30s_views = EXCLUDED.total_video_30s_views,
        total_video_views_autoplayed = EXCLUDED.total_video_views_autoplayed,
        total_video_views_clicked_to_play = EXCLUDED.total_video_views_clicked_to_play,
        total_video_views_organic = EXCLUDED.total_video_views_organic,
        total_video_views_paid = EXCLUDED.total_video_views_paid,
        total_video_reactions_by_type_total = EXCLUDED.total_video_reactions_by_type_total,
        total_video_stories_by_action_type = EXCLUDED.total_video_stories_by_action_type,
        updated_at = CURRENT_TIMESTAMP
    """
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, insights_data)
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error inserting video insights {insights_data.get('id')}: {e}")
        conn.rollback()
        return False

def insert_reels_insights(conn, insights_data):
    """Insert or update Facebook Reels insights data in database"""
    query = """
    INSERT INTO facebook_reels_insights (
        id, video_id, date_start, date_stop,
        blue_reels_play_count, fb_reels_replay_count, fb_reels_total_plays,
        post_impressions_unique, post_video_avg_time_watched, post_video_followers,
        post_video_likes_by_reaction_type, post_video_social_actions, post_video_view_time,
        post_video_retention_graph, calculated_engagement_rate, calculated_replay_rate
    ) VALUES (
        %(id)s, %(video_id)s, %(date_start)s, %(date_stop)s,
        %(blue_reels_play_count)s, %(fb_reels_replay_count)s, %(fb_reels_total_plays)s,
        %(post_impressions_unique)s, %(post_video_avg_time_watched)s, %(post_video_followers)s,
        %(post_video_likes_by_reaction_type)s, %(post_video_social_actions)s, %(post_video_view_time)s,
        %(post_video_retention_graph)s, %(calculated_engagement_rate)s, %(calculated_replay_rate)s
    ) ON CONFLICT (video_id, date_start, date_stop)
    DO UPDATE SET
        blue_reels_play_count = EXCLUDED.blue_reels_play_count,
        fb_reels_replay_count = EXCLUDED.fb_reels_replay_count,
        fb_reels_total_plays = EXCLUDED.fb_reels_total_plays,
        post_impressions_unique = EXCLUDED.post_impressions_unique,
        post_video_avg_time_watched = EXCLUDED.post_video_avg_time_watched,
        post_video_followers = EXCLUDED.post_video_followers,
        post_video_likes_by_reaction_type = EXCLUDED.post_video_likes_by_reaction_type,
        post_video_social_actions = EXCLUDED.post_video_social_actions,
        post_video_view_time = EXCLUDED.post_video_view_time,
        post_video_retention_graph = EXCLUDED.post_video_retention_graph,
        calculated_engagement_rate = EXCLUDED.calculated_engagement_rate,
        calculated_replay_rate = EXCLUDED.calculated_replay_rate,
        updated_at = CURRENT_TIMESTAMP
    """
    
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, insights_data)
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ Error inserting reels insights {insights_data.get('id')}: {e}")
        conn.rollback()
        return False

def select_best_thumbnail_for_dashboard(thumbnails):
    """
    เลือก thumbnail ที่เหมาะสมที่สุดสำหรับ dashboard
    
    ลำดับความสำคัญ:
    1. Preferred thumbnail (ถ้ามี)
    2. ขนาดที่เหมาะสมกับ dashboard (1080x1920 หรือใกล้เคียง)
    3. ขนาดใหญ่ที่สุด (สำหรับคุณภาพ)
    4. Aspect ratio ที่เหมาะสม (9:16 หรือ 16:9)
    
    Args:
        thumbnails: List of thumbnail objects
        
    Returns:
        dict: Best thumbnail object, หรือ None ถ้าไม่มี
    """
    if not thumbnails:
        return None
    
    # คำนวณ score สำหรับแต่ละ thumbnail
    scored_thumbnails = []
    
    for thumb in thumbnails:
        width = thumb.get('width', 0)
        height = thumb.get('height', 0)
        is_preferred = thumb.get('is_preferred', False)
        
        score = 0
        
        # 1. Preferred thumbnail ได้คะแนนสูงสุด
        if is_preferred:
            score += 1000
        
        # 2. ขนาดที่เหมาะสมกับ dashboard
        if width and height:
            # คำนวณ aspect ratio
            aspect_ratio = width / height
            
            # เหมาะสำหรับ mobile (9:16) หรือ desktop (16:9)
            if 0.5 <= aspect_ratio <= 0.6:  # Portrait (9:16 ≈ 0.56)
                score += 500
            elif 1.7 <= aspect_ratio <= 1.9:  # Landscape (16:9 ≈ 1.78)
                score += 400
            
            # ขนาดที่เหมาะสม (1080p หรือ 4K)
            pixels = width * height
            if 1920*1080 <= pixels <= 2160*3840:  # 1080p ถึง 4K
                score += 300
            elif 1280*720 <= pixels < 1920*1080:  # 720p
                score += 200
            elif pixels >= 2160*3840:  # มากกว่า 4K
                score += 100  # คะแนนน้อยกว่าเพราะไฟล์ใหญ่
            
            # ความละเอียดที่เหมาะสำหรับเว็บ
            if width == 1080 and height == 1920:  # Perfect mobile
                score += 200
            elif width == 1920 and height == 1080:  # Perfect desktop
                score += 150
        
        # 3. Scale factor (ถ้ามี)
        scale = thumb.get('scale', 1.0)
        if scale == 1.0:
            score += 50
        
        scored_thumbnails.append({
            'thumbnail': thumb,
            'score': score,
            'width': width,
            'height': height,
            'aspect_ratio': width/height if width and height else 0,
            'pixels': width * height if width and height else 0
        })
    
    # เรียงลำดับตาม score (สูงสุดก่อน)
    scored_thumbnails.sort(key=lambda x: x['score'], reverse=True)
    
    best = scored_thumbnails[0]
    print(f"    🎯 Selected thumbnail: {best['width']}x{best['height']} "
          f"(score: {best['score']}, aspect: {best['aspect_ratio']:.2f}, "
          f"preferred: {best['thumbnail'].get('is_preferred', False)})")
    
    return best['thumbnail']

def fetch_video_thumbnails(video_id, access_token):
    """Fetch all available thumbnails for a video - enhanced quality options"""
    thumbnails = []
    
    url = f"https://graph.facebook.com/v23.0/{video_id}/thumbnails"
    params = {
        'access_token': access_token,
        'fields': 'id,uri,width,height,is_preferred,scale'
    }
    
    try:
        print(f"    🖼️  Fetching thumbnails for video: {video_id}")
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            thumbnails_data = data.get('data', [])
            
            if thumbnails_data:
                print(f"    ✅ Found {len(thumbnails_data)} thumbnails")
                
                # เรียงลำดับตาม is_preferred และขนาด
                thumbnails_data.sort(key=lambda x: (
                    not x.get('is_preferred', False),  # preferred first
                    -(x.get('width', 0) * x.get('height', 0))  # then by size (largest first)
                ))
                
                for thumb in thumbnails_data:
                    thumbnail_info = {
                        'id': thumb.get('id'),
                        'uri': thumb.get('uri'),
                        'width': thumb.get('width'),
                        'height': thumb.get('height'),
                        'is_preferred': thumb.get('is_preferred', False),
                        'scale': thumb.get('scale', 1.0)
                    }
                    thumbnails.append(thumbnail_info)
                    
                    quality = "PREFERRED" if thumbnail_info['is_preferred'] else "STANDARD"
                    size = f"{thumbnail_info['width']}x{thumbnail_info['height']}"
                    print(f"      📐 {quality}: {size} - {thumbnail_info['uri'][:50]}...")
                    
            else:
                print(f"    ❌ No thumbnails found for video: {video_id}")
                
        else:
            print(f"    ⚠️  Thumbnails API error {response.status_code}: {response.text}")
            
    except Exception as e:
        print(f"    ❌ Error fetching thumbnails: {e}")
    
    return thumbnails

def fetch_page_videos(page_id, access_token, limit=10, days_back=180):
    """Fetch videos from Facebook API using /videos endpoint - enhanced fields (default: 6 months back)"""
    videos = []
    
    # Track filtered videos for reporting
    filtered_stats = {
        'no_permalink': 0,
        'stories': 0,
        'instagram': 0,
        'too_short': 0,
        'valid': 0
    }
    
    # คำนวณวันที่ที่ต้องการ (6 เดือน = 180 วัน)
    if days_back:
        since_date = datetime.now() - timedelta(days=days_back)
        since_timestamp = int(since_date.timestamp())
        print(f"  📅 Fetching videos from last {days_back} days (since {since_date.strftime('%Y-%m-%d')})")
    else:
        since_timestamp = None
        print(f"  📅 Fetching ALL videos (no date limit)")
    
    # Enhanced video fields that work with updated token
    fields = [
        'id', 'created_time', 'description', 'title', 'length', 
        'picture', 'permalink_url', 'source'
    ]
    
    url = f"https://graph.facebook.com/v23.0/{page_id}/videos"
    params = {
        'access_token': access_token,
        'fields': ','.join(fields),
        'limit': limit
    }
    
    # เพิ่ม since parameter ถ้ามีการจำกัดวันที่
    if since_timestamp:
        params['since'] = since_timestamp
    
    try:
        while url:
            print(f"📡 Fetching videos from {page_id}...")
            response = requests.get(url, params=params if 'params' not in locals() or params else None)
            
            if response.status_code != 200:
                print(f"❌ API Error: {response.status_code} - {response.text}")
                break
                
            data = response.json()
            
            if 'error' in data:
                print(f"❌ Facebook API Error: {data['error']}")
                break
            
            if 'data' in data:
                for video in data['data']:
                    # 🚫 FILTER: ข้าม Instagram Stories และ Facebook Stories
                    # Stories ไม่มี permalink_url หรือมี URL ที่มี /stories/ 
                    permalink = video.get('permalink_url', '')
                    video_length = video.get('length', 0)
                    video_title = video.get('title', '')
                    
                    # Skip if no permalink (Stories often don't have permalinks)
                    if not permalink:
                        print(f"  ⏭️  Skipping video {video.get('id')} - No permalink (likely Story)")
                        filtered_stats['no_permalink'] += 1
                        continue
                    
                    # Skip if URL contains /stories/ (Facebook Stories)
                    if '/stories/' in permalink.lower():
                        print(f"  ⏭️  Skipping video {video.get('id')} - Facebook Story")
                        filtered_stats['stories'] += 1
                        continue
                    
                    # Skip if URL is Instagram (Instagram Reels/Stories)
                    if 'instagram.com' in permalink.lower():
                        print(f"  ⏭️  Skipping video {video.get('id')} - Instagram content")
                        filtered_stats['instagram'] += 1
                        continue
                    
                    # 🚫 CRITICAL FILTER: ข้าม Stories videos (< 10 seconds)
                    # Stories มักมีความยาว 2-10 วินาที และไม่มี title
                    if video_length and video_length < 10:
                        print(f"  ⏭️  Skipping video {video.get('id')} - Too short ({video_length}s, likely Story)")
                        filtered_stats['too_short'] += 1
                        continue
                    
                    # 🚫 CRITICAL: Skip videos shorter than 10 seconds (Stories)
                    # Based on actual data analysis:
                    # - Stories: < 10 seconds, no title, no ads
                    # 🚫 DUPLICATE CHECK: Already filtered above, remove this duplicate
                    # Valid video - add to list
                    filtered_stats['valid'] += 1
                    video['page_id'] = page_id
                    videos.append(video)
                
                print(f"📹 Found {len(data['data'])} videos, {filtered_stats['valid']} after filtering")
            
            # Handle pagination
            url = data.get('paging', {}).get('next')
            params = None  # Parameters are included in next URL
            
            # Rate limiting
            time.sleep(0.3)
            
    except Exception as e:
        print(f"❌ Exception in fetch_page_videos: {e}")
    
    # Print filtering summary
    total_filtered = filtered_stats['no_permalink'] + filtered_stats['stories'] + filtered_stats['instagram']
    if total_filtered > 0:
        print(f"\n🚫 Filtering Summary:")
        print(f"   ✅ Valid videos: {filtered_stats['valid']}")
        print(f"   ❌ Filtered out: {total_filtered}")
        if filtered_stats['no_permalink'] > 0:
            print(f"      - No permalink: {filtered_stats['no_permalink']}")
        if filtered_stats['stories'] > 0:
            print(f"      - Facebook Stories: {filtered_stats['stories']}")
        if filtered_stats['instagram'] > 0:
            print(f"      - Instagram: {filtered_stats['instagram']}")
    
    return videos

def fetch_video_posts_from_posts(page_id, access_token, limit=10, days_back=180):
    """Fetch video posts from Facebook API using /posts endpoint - minimal fields only (default: 6 months back)"""
    video_posts = []
    
    # คำนวณวันที่ที่ต้องการ (6 เดือน = 180 วัน)
    if days_back:
        since_date = datetime.now() - timedelta(days=days_back)
        since_timestamp = int(since_date.timestamp())
        print(f"  📅 Fetching posts (videos only) from last {days_back} days (since {since_date.strftime('%Y-%m-%d')})")
    else:
        since_timestamp = None
        print(f"  📅 Fetching ALL posts (no date limit)")
    
    # Minimal post fields - only supported fields in v23.0
    fields = [
        'id', 'created_time', 'message', 'story'
    ]
    
    url = f"https://graph.facebook.com/v23.0/{page_id}/posts"
    params = {
        'access_token': access_token,
        'fields': ','.join(fields),
        'limit': limit
    }
    
    # เพิ่ม since parameter ถ้ามีการจำกัดวันที่
    if since_timestamp:
        params['since'] = since_timestamp
    
    try:
        while url:
            print(f"📡 Fetching posts (videos only) from {page_id}...")
            response = requests.get(url, params=params if 'params' not in locals() or params else None)
            
            if response.status_code != 200:
                print(f"❌ API Error: {response.status_code} - {response.text}")
                break
                
            data = response.json()
            
            if 'error' in data:
                print(f"❌ Facebook API Error: {data['error']}")
                break
            
            if 'data' in data:
                # Filter only video posts by checking individual posts
                for post in data['data']:
                    # Try to get individual post details to check if it's a video
                    try:
                        post_detail_url = f"https://graph.facebook.com/v23.0/{post['id']}"
                        post_detail_params = {
                            'access_token': access_token,
                            'fields': 'type'
                        }
                        
                        detail_response = requests.get(post_detail_url, params=post_detail_params)
                        if detail_response.status_code == 200:
                            detail_data = detail_response.json()
                            post_type = detail_data.get('type', '')
                            
                            # Only process video posts
                            if post_type == 'video':
                                # 🚫 FILTER: ข้าม Instagram Stories และ Facebook Stories
                                # Check story field for Stories indicators
                                story = post.get('story', '')
                                if 'instagram' in story.lower() or 'stories' in story.lower():
                                    print(f"  ⏭️  Skipping post {post['id']} - Story content detected in story field")
                                    continue
                                
                                # Extract video information with minimal data
                                video_data = {
                                    'video_id': post['id'],
                                    'post_id': post['id'],
                                    'page_id': page_id,
                                    'created_time': safe_convert_datetime(post.get('created_time')),
                                    'permalink_url': None,  # Not available in minimal request
                                    'source': None,
                                    'title': post.get('message', '')[:255] if post.get('message') else None,
                                    'description': post.get('story'),
                                    'picture': None
                                }
                                
                                video_posts.append(video_data)
                                
                        time.sleep(0.1)  # Rate limiting for individual requests
                        
                    except Exception as e:
                        print(f"    ⚠️ Could not check post type for {post.get('id')}: {e}")
                        continue
                
                video_count = len([v for v in video_posts if v.get('video_id')])
                print(f"🎬 Found {video_count} video posts")
            
            # Handle pagination
            url = data.get('paging', {}).get('next')
            params = None
            
            # Rate limiting
            time.sleep(0.2)
            
    except Exception as e:
        print(f"❌ Exception in fetch_video_posts_from_posts: {e}")
    
    return video_posts

def fetch_video_insights(video_id, access_token):
    """Fetch video insights from Facebook API - enhanced for both Videos and Reels"""
    
    # First, try to detect if this is a Reel by testing Reels metrics
    print(f"    🔍 Detecting content type for {video_id}...")
    
    # Test for Reels metrics first
    reels_metrics = ['blue_reels_play_count', 'fb_reels_total_plays']
    is_reel = False
    reels_data = {}
    
    for metric in reels_metrics:
        url = f"https://graph.facebook.com/v23.0/{video_id}/video_insights"
        params = {
            'access_token': access_token,
            'metric': metric,
            'period': 'lifetime'
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                insights = data.get('data', [])
                
                if insights and insights[0].get('values'):
                    value = insights[0]['values'][0].get('value', 0)
                    if isinstance(value, (int, float)) and value > 0:
                        is_reel = True
                        reels_data[metric] = value
                        print(f"    🎭 {metric}: {value}")
                    else:
                        reels_data[metric] = 0
                else:
                    reels_data[metric] = 0
        except Exception as e:
            print(f"    ⚠️ Error testing {metric}: {e}")
            reels_data[metric] = 0
    
    if is_reel:
        print(f"    🎭 Detected as REEL - fetching full Reels insights...")
        return fetch_reels_insights(video_id, access_token, reels_data)
    else:
        print(f"    📹 Detected as regular VIDEO - fetching video insights...")
        return fetch_regular_video_insights(video_id, access_token)

def fetch_reels_insights(video_id, access_token, initial_data=None):
    """Fetch Facebook Reels insights - these actually work!"""
    
    if initial_data is None:
        initial_data = {}
    
    # All Reels metrics to try
    reels_metrics = [
        'blue_reels_play_count',
        'fb_reels_replay_count', 
        'fb_reels_total_plays',
        'post_impressions_unique',
        'post_video_avg_time_watched',
        'post_video_followers',
        'post_video_likes_by_reaction_type',
        'post_video_social_actions',
        'post_video_view_time',
        'post_video_retention_graph'
    ]
    
    insights_dict = {
        'id': f"{video_id}_reels_{datetime.now().strftime('%Y%m%d')}",
        'video_id': video_id,
        'date_start': datetime.now().date(),
        'date_stop': datetime.now().date(),
        'blue_reels_play_count': initial_data.get('blue_reels_play_count', 0),
        'fb_reels_replay_count': 0,
        'fb_reels_total_plays': initial_data.get('fb_reels_total_plays', 0),
        'post_impressions_unique': 0,
        'post_video_avg_time_watched': 0,
        'post_video_followers': 0,
        'post_video_likes_by_reaction_type': None,
        'post_video_social_actions': None,
        'post_video_view_time': 0,
        'post_video_retention_graph': None,
        'calculated_engagement_rate': 0,
        'calculated_replay_rate': 0
    }
    
    # Fetch all Reels metrics
    for metric in reels_metrics:
        if metric in initial_data:
            continue  # Already fetched
            
        url = f"https://graph.facebook.com/v23.0/{video_id}/video_insights"
        params = {
            'access_token': access_token,
            'metric': metric,
            'period': 'lifetime'
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                insights = data.get('data', [])
                
                if insights and insights[0].get('values'):
                    value = insights[0]['values'][0].get('value')
                    
                    if value is not None:
                        if isinstance(value, (int, float)):
                            insights_dict[metric] = value
                            if value > 0:
                                print(f"    ✅ {metric}: {value}")
                        elif isinstance(value, dict):
                            insights_dict[metric] = json.dumps(value)
                            print(f"    ✅ {metric}: {json.dumps(value)[:50]}...")
                        else:
                            insights_dict[metric] = str(value) if value else None
                            
        except Exception as e:
            print(f"    ⚠️ Error fetching {metric}: {e}")
    
    # Calculate derived metrics
    total_plays = insights_dict.get('fb_reels_total_plays', 0)
    replay_count = insights_dict.get('fb_reels_replay_count', 0)
    impressions = insights_dict.get('post_impressions_unique', 0)
    
    if total_plays > 0:
        if impressions > 0:
            insights_dict['calculated_engagement_rate'] = total_plays / impressions
        if total_plays > 0:
            insights_dict['calculated_replay_rate'] = replay_count / total_plays
    
    return insights_dict, 'reel'

def fetch_regular_video_insights(video_id, access_token):
    """Fetch regular video insights - most return 0 for organic content"""
    
    # Regular video metrics to try
    video_metrics = [
        'total_video_views',
        'total_video_views_unique',
        'total_video_complete_views',
        'total_video_complete_views_unique',
        'total_video_impressions',
        'total_video_impressions_unique',
        'total_video_avg_time_watched',
        'total_video_view_total_time',
        'total_video_10s_views',
        'total_video_10s_views_unique',
        'total_video_15s_views',
        'total_video_30s_views',
        'total_video_views_autoplayed',
        'total_video_views_clicked_to_play',
        'total_video_views_organic',
        'total_video_views_paid',
        'total_video_reactions_by_type_total',
        'total_video_stories_by_action_type'
    ]
    
    insights_dict = {
        'id': f"{video_id}_video_{datetime.now().strftime('%Y%m%d')}",
        'video_id': video_id,
        'date_start': datetime.now().date(),
        'date_stop': datetime.now().date(),
    }
    
    # Initialize all metrics to 0
    for metric in video_metrics:
        insights_dict[metric] = 0
    
    # Set JSON fields to None
    insights_dict['total_video_reactions_by_type_total'] = None
    insights_dict['total_video_stories_by_action_type'] = None
    
    # Fetch metrics (most will return 0 for organic content)
    for metric in video_metrics:
        url = f"https://graph.facebook.com/v23.0/{video_id}/video_insights"
        params = {
            'access_token': access_token,
            'metric': metric,
            'period': 'lifetime'
        }
        
        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                insights = data.get('data', [])
                
                if insights and insights[0].get('values'):
                    value = insights[0]['values'][0].get('value')
                    
                    if value is not None:
                        if isinstance(value, (int, float)):
                            insights_dict[metric] = value
                            if value > 0:
                                print(f"    ✅ {metric}: {value}")
                        elif isinstance(value, dict):
                            insights_dict[metric] = json.dumps(value)
                            print(f"    ✅ {metric}: {json.dumps(value)[:50]}...")
                        else:
                            insights_dict[metric] = str(value) if value else None
                            
        except Exception as e:
            print(f"    ⚠️ Error fetching {metric}: {e}")
    
    return insights_dict, 'video'

def main(days_back=180):
    """Main function to sync Facebook video posts and insights (default: 6 months back)"""
    print("🎬 Starting Facebook Video Posts & Insights Sync...")
    print(f"📅 Sync started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # แสดงข้อมูลช่วงเวลา
    if days_back:
        since_date = datetime.now() - timedelta(days=days_back)
        print(f"📅 Date Range: Last {days_back} days ({since_date.strftime('%Y-%m-%d')} to {datetime.now().strftime('%Y-%m-%d')})")
    else:
        print("📅 Date Range: ALL available data (no limit)")
    
    # Validate configuration
    if not FB_PAGE_IDS or not FB_PAGE_ACCESS_TOKENS:
        print("❌ Missing FB_PAGE_IDS or FB_PAGE_ACCESS_TOKENS in .env")
        return
    
    if len(FB_PAGE_IDS) != len(FB_PAGE_ACCESS_TOKENS):
        print("❌ Number of PAGE_IDS and ACCESS_TOKENS must match")
        return
    
    try:
        # Create database connection
        conn = get_db_connection()
        print("✅ Database connection established")
        
        total_videos = 0
        total_insights = 0
        start_time = datetime.now()
        
        # Process each page
        for i, page_id in enumerate(FB_PAGE_IDS):
            page_id = page_id.strip()
            access_token = FB_PAGE_ACCESS_TOKENS[i].strip()
            
            if not page_id or not access_token:
                continue
                
            print(f"\n🎬 Processing Page: {page_id}")
            
            # Method 1: Fetch from /videos endpoint
            print("📡 Fetching from /videos endpoint...")
            videos_from_videos = fetch_page_videos(page_id, access_token, limit=25, days_back=days_back)
            
            # Skip video posts sync for now due to API limitations
            print("📡 Skipping video posts from /posts endpoint due to API v23.0 limitations...")
            videos_from_posts = []  # Empty list since we're skipping
            
            # Combine and deduplicate videos
            all_videos = videos_from_videos + videos_from_posts
            seen_ids = set()
            unique_videos = []
            
            for video in all_videos:
                video_id = video.get('id') or video.get('video_id')
                if video_id and video_id not in seen_ids:
                    seen_ids.add(video_id)
                    # Ensure video_id field exists
                    if 'video_id' not in video:
                        video['video_id'] = video_id
                    unique_videos.append(video)
            
            print(f"📊 Total unique videos found: {len(unique_videos)}")
            
            # Process each video
            video_success_count = 0
            insights_success_count = 0
            
            for video in unique_videos:
                try:
                    video_id = video['video_id']
                    
                    # Download thumbnail image if available - Enhanced with multiple quality options
                    local_picture_id = None
                    picture_url = video.get('picture')
                    
                    # Try to get enhanced thumbnails first
                    thumbnails = fetch_video_thumbnails(video_id, access_token)
                    
                    if thumbnails:
                        # เลือก thumbnail ที่ดีที่สุดสำหรับ dashboard
                        best_thumbnail = select_best_thumbnail_for_dashboard(thumbnails)
                        
                        if best_thumbnail:
                            picture_url = best_thumbnail['uri']
                            
                            print(f"  📸 Using enhanced thumbnail ({best_thumbnail['width']}x{best_thumbnail['height']}) for: {video_id}")
                            
                            # เก็บข้อมูล metadata เพิ่มเติม
                            thumbnail_metadata = {
                                'width': best_thumbnail['width'],
                                'height': best_thumbnail['height'],
                                'is_preferred': best_thumbnail['is_preferred'],
                                'scale': best_thumbnail['scale'],
                                'aspect_ratio': best_thumbnail['width'] / best_thumbnail['height'] if best_thumbnail['width'] and best_thumbnail['height'] else None,
                                'total_thumbnails': len(thumbnails),
                                'selection_method': 'enhanced_api'
                            }
                        else:
                            print(f"  ❌ No suitable thumbnail found in API response for: {video_id}")
                            thumbnail_metadata = None
                            
                    elif picture_url:
                        print(f"  📸 Using basic picture field for: {video_id}")
                        thumbnail_metadata = {
                            'width': None,
                            'height': None, 
                            'is_preferred': True,  # Assume basic picture is preferred
                            'scale': 1.0,
                            'aspect_ratio': None,
                            'total_thumbnails': 1,
                            'selection_method': 'basic_field'
                        }
                    else:
                        print(f"  ❌ No thumbnail available for: {video_id}")
                        thumbnail_metadata = None
                    
                    if picture_url:
                        print(f"  📥 Downloading video thumbnail to database: {video_id}")
                        # สำหรับ videos จาก /videos endpoint: ใช้ video_id เป็น source_post_id
                        # สำหรับ videos จาก /posts endpoint: ใช้ post_id ที่มีอยู่แล้ว
                        source_post_id = video.get('post_id', video_id)  # ใช้ post_id ถ้ามี ไม่งั้นใช้ video_id
                        
                        # เพิ่ม metadata ใน category สำหรับ dashboard
                        category = "video_thumbnails"
                        if thumbnail_metadata and thumbnail_metadata.get('width'):
                            aspect_ratio = thumbnail_metadata.get('aspect_ratio', 0)
                            if 0.5 <= aspect_ratio <= 0.6:
                                category = "video_thumbnails_portrait"  # Mobile-friendly
                            elif 1.7 <= aspect_ratio <= 1.9:
                                category = "video_thumbnails_landscape"  # Desktop-friendly
                            else:
                                category = f"video_thumbnails_{thumbnail_metadata['width']}x{thumbnail_metadata['height']}"
                        
                        local_picture_id = media_manager.store_media_from_url(
                            picture_url, 
                            category=category,
                            source_post_id=source_post_id,  # ใช้ post_id หรือ video_id
                            source_type="facebook_video"
                        )
                        if local_picture_id:
                            print(f"  ✅ Thumbnail downloaded for video: {video_id}")
                            
                            # อัปเดต metadata ใน media_storage
                            if thumbnail_metadata:
                                try:
                                    with conn.cursor() as cursor:
                                        cursor.execute("""
                                            UPDATE media_storage 
                                            SET metadata = %s
                                            WHERE id = %s
                                        """, (json.dumps(thumbnail_metadata), local_picture_id))
                                        conn.commit()
                                        
                                        # แสดงข้อมูลที่เก็บ
                                        method = thumbnail_metadata.get('selection_method', 'unknown')
                                        if thumbnail_metadata.get('width'):
                                            print(f"    📊 Saved metadata: {thumbnail_metadata['width']}x{thumbnail_metadata['height']} "
                                                  f"(aspect: {thumbnail_metadata.get('aspect_ratio', 0):.2f}, method: {method})")
                                        else:
                                            print(f"    📊 Saved metadata: basic thumbnail (method: {method})")
                                            
                                except Exception as e:
                                    print(f"    ⚠️  Could not save metadata: {e}")
                        else:
                            print(f"  ⚠️ Failed to download thumbnail for: {video_id}")
                    
                    # Prepare video data for database with enhanced fields
                    video_data = {
                        'video_id': video_id,
                        'post_id': video.get('post_id', video_id),
                        'page_id': video['page_id'],
                        'created_time': safe_convert_datetime(video.get('created_time')),
                        'permalink_url': video.get('permalink_url'),
                        'source': video.get('source'),
                        'length': safe_convert_float(video.get('length')),
                        'title': video.get('title', '')[:255] if video.get('title') else video.get('description', '')[:255],
                        'description': video.get('description'),
                        'picture': picture_url,
                        'local_picture_id': local_picture_id
                    }
                    
                    # Insert video data
                    if insert_video_post(conn, video_data):
                        video_success_count += 1
                        print(f"  ✅ Video synced: {video_id}")
                        
                        # Always try to fetch and insert insights (video or reels)
                        insights_result = fetch_video_insights(video_id, access_token)
                        if insights_result:
                            insights_data, content_type = insights_result
                            
                            # Update video_type in video_data
                            try:
                                with conn.cursor() as cursor:
                                    cursor.execute(
                                        "UPDATE facebook_video_posts SET video_type = %s WHERE video_id = %s",
                                        (content_type, video_id)
                                    )
                                    conn.commit()
                            except Exception as e:
                                print(f"    ⚠️ Could not update video_type: {e}")
                            
                            # Insert appropriate insights
                            if content_type == 'reel':
                                if insert_reels_insights(conn, insights_data):
                                    insights_success_count += 1
                                    print(f"    🎭 Reels insights synced for: {video_id}")
                                else:
                                    print(f"    ❌ Failed to insert reels insights for: {video_id}")
                            else:
                                if insert_video_insights(conn, insights_data):
                                    insights_success_count += 1
                                    print(f"    � Video insights synced for: {video_id}")
                                else:
                                    print(f"    ❌ Failed to insert video insights for: {video_id}")
                        
                        # Rate limiting
                        time.sleep(0.2)
                    
                except Exception as e:
                    print(f"  ❌ Error processing video {video.get('video_id', 'unknown')}: {e}")
                    continue
            
            print(f"✅ Page {page_id}: {video_success_count}/{len(unique_videos)} videos synced")
            print(f"📈 Page {page_id}: {insights_success_count}/{len(unique_videos)} insights synced")
            
            total_videos += video_success_count
            total_insights += insights_success_count
        
        # Summary
        end_time = datetime.now()
        duration = end_time - start_time
        
        print(f"\n🎉 Sync Process Completed!")
        print(f"📹 Total videos synced: {total_videos}")
        print(f"📊 Total insights synced: {total_insights}")
        print(f"⏱️  Duration: {duration}")
        print(f"🏁 Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Show media storage statistics
        print(f"\n📊 Media Storage Statistics:")
        if 'media_manager' in globals():
            media_manager.get_storage_stats()
        
    except psycopg2.Error as e:
        print(f"❌ Database error: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            print("🔌 Database connection closed")

if __name__ == "__main__":
    # Setup command line argument parser
    parser = argparse.ArgumentParser(
        description='Facebook Video Posts & Insights Sync Script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sync_fb_video_posts_to_db.py                    # Sync last 180 days (default)
  python sync_fb_video_posts_to_db.py --days-back 30     # Sync last 30 days
  python sync_fb_video_posts_to_db.py --days-back 90     # Sync last 90 days
  python sync_fb_video_posts_to_db.py --all              # Sync all available data (no time limit)
  
Date Range Options:
  --days-back 180  → Sync last 6 months (recommended for first run)
  --days-back 90   → Sync last 3 months
  --days-back 30   → Sync last 1 month
  --days-back 7    → Sync last 7 days
  --all            → Sync all available data (no time limit)
        """
    )
    
    # Add mutually exclusive group for date options
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument(
        '--days-back',
        type=int,
        default=180,
        help='Number of days to sync back from today (default: 180)'
    )
    date_group.add_argument(
        '--all',
        action='store_true',
        help='Sync all available data with no time limit'
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    # Fix Windows Unicode encoding issue
    import sys
    if sys.platform.startswith('win'):
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    # Determine days_back value
    if args.all:
        days_back = None
        print("📅 Mode: Sync ALL available video data (no time limit)")
    else:
        days_back = args.days_back
        print(f"📅 Mode: Sync last {days_back} days of video data")
    
    try:
        main(days_back)
    except KeyboardInterrupt:
        print("\n⚠️  Video sync interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import sys
        sys.exit(1)
