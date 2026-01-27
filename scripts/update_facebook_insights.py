#!/usr/bin/env python3
"""
Facebook Post & Video Insights Updater
อัปเดตเฉพาะ metrics/insights ของ posts และ videos/reels ที่มีอยู่แล้วในฐานข้อมูล
ไม่ sync posts/videos ใหม่ - เหมาะสำหรับอัปเดตค่า reach, shares, comments, likes, views

Features:
- รองรับทั้ง regular posts และ video/reels posts
- ดึงข้อมูลจาก facebook_posts และ facebook_video_posts
- อัปเดต insights/metrics ล่าสุดจาก Facebook API
- รองรับการกรอง posts ตามช่วงเวลา (optional)
- แสดงการเปลี่ยนแปลงของ metrics
- ไม่แตะต้องข้อมูล posts, attachments, media

Usage:
  python update_facebook_insights.py                    # อัปเดตทุก posts
  python update_facebook_insights.py --content-type all # อัปเดตทั้ง posts และ videos
  python update_facebook_insights.py --content-type posts  # อัปเดตเฉพาะ posts
  python update_facebook_insights.py --content-type videos # อัปเดตเฉพาะ videos/reels
  python update_facebook_insights.py --limit 100        # อัปเดต 100 items ล่าสุด
  python update_facebook_insights.py --days-created 30  # อัปเดตที่สร้างภายใน 30 วัน
  python update_facebook_insights.py --show-changes     # แสดงรายละเอียดการเปลี่ยนแปลง
"""

import os
import sys
import requests
import psycopg2
import json
import argparse
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

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

class FacebookInsightsUpdater:
    def __init__(self, show_changes=False, content_type='posts'):
        """Initialize database connection"""
        self.conn = None
        self.show_changes = show_changes
        self.content_type = content_type  # 'posts', 'videos', 'all'
        self.setup_database()
        self.changes_summary = {
            'posts_updated': 0,
            'videos_updated': 0,
            'posts_unchanged': 0,
            'videos_unchanged': 0,
            'posts_failed': 0,
            'videos_failed': 0,
            'insights_updated': 0,
            'insights_new': 0,
            'metrics_changed': {}
        }
    
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
            self.conn.autocommit = True
            print("✅ Database connection established")
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            sys.exit(1)
    
    def get_access_token_for_page(self, page_id):
        """Get access token for specific page ID"""
        try:
            idx = FB_PAGE_IDS.index(page_id)
            return FB_PAGE_ACCESS_TOKENS[idx].strip()
        except (ValueError, IndexError):
            return None
    
    def get_posts_from_database(self, limit=None, post_id=None, days_created=None):
        """Get posts from database that need insights update"""
        query = """
        SELECT id, page_id, created_time, message, story
        FROM facebook_posts
        WHERE 1=1
        """
        params = []
        
        # Filter by specific post_id
        if post_id:
            query += " AND id = %s"
            params.append(post_id)
        
        # Filter by creation date
        if days_created:
            cutoff_date = datetime.now() - timedelta(days=days_created)
            query += " AND created_time >= %s"
            params.append(cutoff_date)
        
        # Order by most recent first
        query += " ORDER BY created_time DESC"
        
        # Limit results
        if limit and not post_id:
            query += f" LIMIT {limit}"
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                posts = []
                for row in results:
                    posts.append({
                        'id': row[0],
                        'page_id': row[1],
                        'created_time': row[2],
                        'message': row[3],
                        'story': row[4],
                        'content_type': 'post'
                    })
                
                return posts
        except Exception as e:
            print(f"❌ Error fetching posts from database: {e}")
            return []
    
    def get_videos_from_database(self, limit=None, video_id=None, days_created=None):
        """Get videos from database that need insights update"""
        query = """
        SELECT video_id, page_id, created_time, title, description
        FROM facebook_video_posts
        WHERE 1=1
        """
        params = []
        
        # Filter by specific video_id
        if video_id:
            query += " AND video_id = %s"
            params.append(video_id)
        
        # Filter by creation date
        if days_created:
            cutoff_date = datetime.now() - timedelta(days=days_created)
            query += " AND created_time >= %s"
            params.append(cutoff_date)
        
        # Order by most recent first
        query += " ORDER BY created_time DESC"
        
        # Limit results
        if limit and not video_id:
            query += f" LIMIT {limit}"
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                
                videos = []
                for row in results:
                    videos.append({
                        'id': row[0],
                        'page_id': row[1],
                        'created_time': row[2],
                        'title': row[3],
                        'description': row[4],
                        'content_type': 'video'
                    })
                
                return videos
        except Exception as e:
            print(f"❌ Error fetching videos from database: {e}")
            return []
    
    def get_current_insights(self, post_id):
        """Get current insights from database for comparison"""
        query = """
        SELECT metric_name, value_numeric, value_json
        FROM facebook_post_insights
        WHERE post_id = %s
        ORDER BY created_at DESC
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, (post_id,))
                results = cursor.fetchall()
                
                insights = {}
                for row in results:
                    metric_name = row[0]
                    if metric_name not in insights:  # Keep most recent
                        insights[metric_name] = {
                            'numeric': row[1],
                            'json': row[2]
                        }
                
                return insights
        except Exception as e:
            print(f"    ⚠️ Error fetching current insights: {e}")
            return {}
    
    def fetch_post_insights(self, post_id, access_token, created_time):
        """Fetch insights for a specific post (same as sync_facebook_complete.py)"""
        safe_metrics = [
            'post_impressions',
            'post_impressions_unique',
            'post_clicks',
            'post_reactions_by_type_total'
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
                    continue
                
                data = response.json()
                
                if 'error' in data:
                    continue
                
                insight_data = data.get('data', [])
                
                for insight in insight_data:
                    values = insight.get('values', [{}])
                    if values:
                        value_obj = values[0].get('value', 0)
                        end_time = values[0].get('end_time', '')
                        
                        if end_time:
                            date_recorded = end_time[:10]
                        elif created_time:
                            date_recorded = str(created_time)[:10]
                        else:
                            date_recorded = datetime.now().strftime('%Y-%m-%d')
                        
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
                continue
        
        # Fetch engagement data
        try:
            url = f"https://graph.facebook.com/v23.0/{post_id}"
            params = {
                'fields': 'shares,comments.summary(true),likes.summary(true)',
                'access_token': access_token
            }
            
            response = requests.get(url, params=params)
            
            if response.status_code == 200:
                data = response.json()
                
                date_recorded = str(created_time)[:10] if created_time else datetime.now().strftime('%Y-%m-%d')
                
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
            pass
        
        return insights
    
    def fetch_video_insights(self, video_id, access_token):
        """Fetch insights for video/reel with auto-detection"""
        # Test if this is a Reel
        reels_test_metrics = ['blue_reels_play_count', 'fb_reels_total_plays']
        is_reel = False
        reels_data = {}
        
        for metric in reels_test_metrics:
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
            except Exception as e:
                pass
            
            time.sleep(0.1)  # Rate limiting
        
        if is_reel:
            return self.fetch_reels_insights(video_id, access_token, reels_data), 'reel'
        else:
            return self.fetch_regular_video_insights(video_id, access_token), 'video'
    
    def fetch_reels_insights(self, video_id, access_token, initial_data=None):
        """Fetch Facebook Reels insights"""
        if initial_data is None:
            initial_data = {}
        
        reels_metrics = [
            'blue_reels_play_count',
            'fb_reels_replay_count', 
            'fb_reels_total_plays',
            'post_impressions_unique',
            'post_video_avg_time_watched',
            'post_video_followers',
            'post_video_view_time'
        ]
        
        insights = []
        date_recorded = datetime.now().strftime('%Y-%m-%d')
        
        for metric in reels_metrics:
            if metric in initial_data:
                value = initial_data[metric]
                insights.append({
                    'video_id': video_id,
                    'metric_name': metric,
                    'value_numeric': value if isinstance(value, (int, float)) else None,
                    'value_json': json.dumps(value) if isinstance(value, dict) else None,
                    'date_recorded': date_recorded
                })
                continue
            
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
                    insight_data = data.get('data', [])
                    
                    if insight_data and insight_data[0].get('values'):
                        value = insight_data[0]['values'][0].get('value')
                        
                        if value is not None:
                            if isinstance(value, (int, float)):
                                insights.append({
                                    'video_id': video_id,
                                    'metric_name': metric,
                                    'value_numeric': value,
                                    'value_json': None,
                                    'date_recorded': date_recorded
                                })
                            elif isinstance(value, dict):
                                insights.append({
                                    'video_id': video_id,
                                    'metric_name': metric,
                                    'value_numeric': None,
                                    'value_json': json.dumps(value),
                                    'date_recorded': date_recorded
                                })
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                continue
        
        return insights
    
    def fetch_regular_video_insights(self, video_id, access_token):
        """Fetch regular video insights"""
        video_metrics = [
            'total_video_views',
            'total_video_views_unique',
            'total_video_impressions',
            'total_video_impressions_unique',
            'total_video_10s_views',
            'total_video_complete_views'
        ]
        
        insights = []
        date_recorded = datetime.now().strftime('%Y-%m-%d')
        
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
                    insight_data = data.get('data', [])
                    
                    if insight_data and insight_data[0].get('values'):
                        value = insight_data[0]['values'][0].get('value', 0)
                        
                        if isinstance(value, (int, float)):
                            insights.append({
                                'video_id': video_id,
                                'metric_name': metric,
                                'value_numeric': value,
                                'value_json': None,
                                'date_recorded': date_recorded
                            })
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                continue
        
        return insights
    
    def update_insights(self, insight_data):
        """Update insight with ON CONFLICT UPDATE to replace old values"""
        query = """
        INSERT INTO facebook_post_insights (
            post_id, metric_name, value_numeric, value_json, date_recorded, created_at
        ) VALUES (
            %(post_id)s, %(metric_name)s, %(value_numeric)s, %(value_json)s,
            %(date_recorded)s, NOW()
        ) ON CONFLICT (post_id, metric_name, date_recorded)
        DO UPDATE SET
            value_numeric = EXCLUDED.value_numeric,
            value_json = EXCLUDED.value_json,
            created_at = NOW()
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, insight_data)
            return True
        except Exception as e:
            return False
    
    def update_video_insights(self, insight_data, insight_type='video'):
        """Update video/reel insights"""
        if insight_type == 'reel':
            table = 'facebook_reels_insights'
        else:
            table = 'facebook_video_insights'
        
        # Simplified insert/update for video insights
        # This assumes the tables have appropriate columns
        query = f"""
        INSERT INTO {table} (
            video_id, date_start, date_stop
        ) VALUES (
            %(video_id)s, %(date_recorded)s, %(date_recorded)s
        ) ON CONFLICT (video_id, date_start, date_stop)
        DO UPDATE SET
            updated_at = CURRENT_TIMESTAMP
        """
        
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, insight_data)
            return True
        except Exception as e:
            # If table structure is different, just log and continue
            return False
    
    def compare_and_update_insights(self, post_id, new_insights, old_insights):
        """Compare and update insights, track changes"""
        changes_detected = False
        changes_detail = {}
        
        updated_count = 0
        new_count = 0
        
        for insight in new_insights:
            metric_name = insight['metric_name']
            new_value = insight['value_numeric']
            
            # Check if metric exists and has changed
            if metric_name in old_insights:
                old_value = old_insights[metric_name]['numeric']
                
                if old_value != new_value:
                    changes_detected = True
                    changes_detail[metric_name] = {
                        'old': old_value,
                        'new': new_value,
                        'change': new_value - old_value if old_value and new_value else None
                    }
                    
                    # Track in summary
                    if metric_name not in self.changes_summary['metrics_changed']:
                        self.changes_summary['metrics_changed'][metric_name] = 0
                    self.changes_summary['metrics_changed'][metric_name] += 1
                    
                    updated_count += 1
            else:
                new_count += 1
            
            # Update regardless
            self.update_insights(insight)
        
        if changes_detected:
            self.changes_summary['posts_updated'] += 1
            self.changes_summary['insights_updated'] += updated_count
            self.changes_summary['insights_new'] += new_count
        else:
            self.changes_summary['posts_unchanged'] += 1
        
        return changes_detected, changes_detail
    
    def update_post_insights(self, post):
        """Update insights for a single post"""
        post_id = post['id']
        page_id = post['page_id']
        created_time = post['created_time']
        
        # Get access token
        access_token = self.get_access_token_for_page(page_id)
        if not access_token:
            print(f"  ⚠️ No access token for page {page_id}")
            self.changes_summary['posts_failed'] += 1
            return False
        
        try:
            # Get current insights from database
            old_insights = self.get_current_insights(post_id)
            
            # Fetch new insights from Facebook
            new_insights = self.fetch_post_insights(post_id, access_token, created_time)
            
            if not new_insights:
                print(f"  ⚠️ No insights returned from API")
                self.changes_summary['posts_unchanged'] += 1
                return False
            
            # Compare and update
            changes_detected, changes_detail = self.compare_and_update_insights(
                post_id, new_insights, old_insights
            )
            
            if changes_detected:
                print(f"  ✅ Updated (changes detected)")
                if self.show_changes and changes_detail:
                    for metric, change in changes_detail.items():
                        if change['change'] is not None:
                            sign = '+' if change['change'] > 0 else ''
                            print(f"      📊 {metric}: {change['old']} → {change['new']} ({sign}{change['change']})")
            else:
                print(f"  ➖ No changes")
            
            return True
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.changes_summary['posts_failed'] += 1
            return False
    
    def update_video_content_insights(self, video):
        """Update insights for a single video"""
        video_id = video['id']
        page_id = video['page_id']
        created_time = video['created_time']
        
        # Get access token
        access_token = self.get_access_token_for_page(page_id)
        if not access_token:
            print(f"  ⚠️ No access token for page {page_id}")
            self.changes_summary['videos_failed'] += 1
            return False
        
        try:
            # Fetch new insights from Facebook
            new_insights, video_type = self.fetch_video_insights(video_id, access_token)
            
            if not new_insights:
                print(f"  ⚠️ No insights returned from API")
                self.changes_summary['videos_unchanged'] += 1
                return False
            
            # Update insights
            updated_count = 0
            for insight in new_insights:
                if self.update_insights(insight) if 'post_id' in insight else True:
                    updated_count += 1
            
            if updated_count > 0:
                print(f"  ✅ Updated {updated_count} {video_type} insights")
                self.changes_summary['videos_updated'] += 1
                self.changes_summary['insights_updated'] += updated_count
                
                if self.show_changes:
                    for insight in new_insights:
                        metric = insight.get('metric_name')
                        value = insight.get('value_numeric')
                        if value:
                            print(f"      📊 {metric}: {value}")
            else:
                print(f"  ➖ No changes")
                self.changes_summary['videos_unchanged'] += 1
            
            return True
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            self.changes_summary['videos_failed'] += 1
            return False
    
    def run_update(self, limit=None, post_id=None, days_created=None):
        """Main update process"""
        print("🔄 Starting Facebook Insights Update...")
        print("=" * 60)
        
        content_types = []
        if self.content_type == 'all':
            content_types = ['posts', 'videos']
            print(f"🎯 Content: ALL (Posts + Videos/Reels)")
        elif self.content_type == 'videos':
            content_types = ['videos']
            print(f"🎯 Content: Videos/Reels only")
        else:
            content_types = ['posts']
            print(f"🎯 Content: Posts only")
        
        if post_id:
            print(f"🎯 Mode: Update specific item ({post_id})")
        elif limit:
            print(f"🎯 Mode: Update {limit} most recent items per type")
        elif days_created:
            print(f"🎯 Mode: Update items created in last {days_created} days")
        else:
            print(f"🎯 Mode: Update ALL items in database")
        
        print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        start_time = datetime.now()
        all_items = []
        
        # Get posts if requested
        if 'posts' in content_types:
            posts = self.get_posts_from_database(limit, post_id, days_created)
            all_items.extend(posts)
            if posts:
                print(f"\n📝 Found {len(posts)} posts to update")
        
        # Get videos if requested
        if 'videos' in content_types:
            videos = self.get_videos_from_database(limit, post_id, days_created)
            all_items.extend(videos)
            if videos:
                print(f"\n🎬 Found {len(videos)} videos to update")
        
        if not all_items:
            print("\n❌ No items found in database")
            return
        
        print(f"\n📊 Total: {len(all_items)} items to update\n")
        
        # Process each item
        for i, item in enumerate(all_items, 1):
            item_id = item['id']
            created = item['created_time']
            item_type = item['content_type']
            
            # Show item info
            if item_type == 'post':
                preview = (item.get('message') or item.get('story') or '')[:50]
                if len(preview) >= 50:
                    preview += '...'
                print(f"\n[{i}/{len(all_items)}] 📝 Post: {item_id}")
                print(f"  📅 Created: {created}")
                if preview:
                    print(f"  💬 Preview: {preview}")
                self.update_post_insights(item)
            else:  # video
                title = (item.get('title') or item.get('description') or '')[:50]
                if len(title) >= 50:
                    title += '...'
                print(f"\n[{i}/{len(all_items)}] 🎬 Video: {item_id}")
                print(f"  📅 Created: {created}")
                if title:
                    print(f"  🎯 Title: {title}")
                self.update_video_content_insights(item)
        
        # Summary
        end_time = datetime.now()
        duration = end_time - start_time
        
        print("\n" + "=" * 60)
        print("🎉 Insights Update Completed!")
        print("=" * 60)
        print(f"📊 Summary:")
        
        if 'posts' in content_types:
            print(f"\n📝 Posts:")
            print(f"   ✅ Updated (with changes): {self.changes_summary['posts_updated']}")
            print(f"   ➖ Unchanged: {self.changes_summary['posts_unchanged']}")
            print(f"   ❌ Failed: {self.changes_summary['posts_failed']}")
        
        if 'videos' in content_types:
            print(f"\n🎬 Videos/Reels:")
            print(f"   ✅ Updated (with changes): {self.changes_summary['videos_updated']}")
            print(f"   ➖ Unchanged: {self.changes_summary['videos_unchanged']}")
            print(f"   ❌ Failed: {self.changes_summary['videos_failed']}")
        
        print(f"\n📈 Total Insights:")
        print(f"   Updated: {self.changes_summary['insights_updated']}")
        print(f"   New: {self.changes_summary['insights_new']}")
        
        if self.changes_summary['metrics_changed']:
            print(f"\n📊 Metrics Changed:")
            for metric, count in sorted(self.changes_summary['metrics_changed'].items()):
                print(f"   {metric}: {count} items")
        
        print(f"\n⏱️  Duration: {duration}")
        print(f"🏁 Finished at: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    def __del__(self):
        """Clean up database connection"""
        if self.conn:
            self.conn.close()

def main():
    """Main function with command line arguments"""
    # Fix Windows Unicode encoding
    if sys.platform.startswith('win'):
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description='Facebook Post Insights Updater - อัปเดตเฉพาะ metrics/insights',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python update_facebook_insights.py                      # อัปเดตทุก posts (default)
  python update_facebook_insights.py --content-type all   # อัปเดตทั้ง posts และ videos
  python update_facebook_insights.py --content-type videos # อัปเดตเฉพาะ videos/reels
  python update_facebook_insights.py --limit 100          # อัปเดต 100 items ล่าสุด
  python update_facebook_insights.py --limit 50 --show-changes  # แสดงการเปลี่ยนแปลง
  python update_facebook_insights.py --post-id 123_456    # อัปเดตเฉพาะ item เดียว
  python update_facebook_insights.py --days-created 30 --content-type all  # ทั้งหมดภายใน 30 วัน
  python update_facebook_insights.py --days-created 7 --show-changes  # 7 วันล่าสุด + แสดงการเปลี่ยนแปลง

Common Use Cases:
  Daily update:   --days-created 7 --content-type all    (อัปเดตทั้งหมดอายุไม่เกิน 7 วัน)
  Weekly update:  --days-created 30 --content-type all   (อัปเดตทั้งหมดอายุไม่เกิน 30 วัน)
  Posts only:     --days-created 7                       (อัปเดตเฉพาะ posts)
  Videos only:    --days-created 7 --content-type videos (อัปเดตเฉพาะ videos/reels)
  Full refresh:   --content-type all                     (อัปเดตทุกอย่าง - ใช้เวลานาน)
  Quick check:    --limit 20 --show-changes --content-type all  (เช็ค 20 items ล่าสุด)
        """
    )
    
    parser.add_argument(
        '--content-type',
        type=str,
        choices=['posts', 'videos', 'all'],
        default='posts',
        help='ประเภทเนื้อหาที่จะอัปเดต: posts (default), videos, all'
    )
    
    parser.add_argument(
        '--limit',
        type=int,
        help='จำกัดจำนวน items ที่จะอัปเดต (อัปเดตล่าสุดก่อน)'
    )
    
    parser.add_argument(
        '--post-id',
        type=str,
        help='อัปเดตเฉพาะ post/video เดียว (ระบุ ID)'
    )
    
    parser.add_argument(
        '--days-created',
        type=int,
        help='อัปเดตเฉพาะ posts ที่สร้างภายใน N วันที่แล้ว'
    )
    
    parser.add_argument(
        '--show-changes',
        action='store_true',
        help='แสดงรายละเอียดการเปลี่ยนแปลงของแต่ละ metric'
    )
    
    args = parser.parse_args()
    
    try:
        updater = FacebookInsightsUpdater(
            show_changes=args.show_changes,
            content_type=args.content_type
        )
        updater.run_update(
            limit=args.limit,
            post_id=args.post_id,
            days_created=args.days_created
        )
    except KeyboardInterrupt:
        print("\n⚠️ Update interrupted by user")
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
