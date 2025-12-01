"""
TikTok Service - Sync content from TikTok Business API
"""
import re
import json
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Content, TaskLog, TaskStatus
from app.models.system import AppSetting
from app.models.enums import Platform, ContentStatus, ContentType, ContentSource


class TikTokService:
    """Service for syncing TikTok content"""
    
    # TikTok Business API base URL
    BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"
    
    # External API for getting item details (from old system)
    ITEM_DETAIL_API = "https://api-tiktok.julaherb.co/get_item"
    
    # Default official channels (fallback ถ้า DB ยังไม่มีค่า)
    DEFAULT_OFFICIAL_CHANNELS = [
        "julaherbthailand",
        "julaherbthailandshop",
        "jh.beauty.club",
        "acnelabjulaherb",
    ]
    
    def __init__(self):
        # ใช้ access token แบบ dynamic:
        # - ถ้ามี token ตรง ๆ ใน .env (TIKTOK_ACCESS_TOKEN / TIKTOK_MAIN_ACCESS_TOKEN / TIKTOK_AD_TOKEN) จะใช้ตัวนั้น
        # - ถ้าไม่มี จะลอง refresh token ผ่าน OAuth2 ตามแบบระบบเดิม
        self.access_token = self.get_access_token()
        self.business_id = self.get_business_id()
    
    @classmethod
    def get_access_token(cls) -> Optional[str]:
        """
        ดึง access token สำหรับ TikTok Business API
        ลำดับความสำคัญ (ใหม่):
        1) ถ้ามี token ตรง ๆ ใน DB (app_settings.key = 'tiktok_access_token') ให้ใช้เลย
        2) ถ้าใน DB มี client_id + client_secret + refresh_token → ใช้ refresh flow
        3) ถ้าใน DB ไม่มี ค่อย fallback ไปใช้ .env:
           3.1) token ตรง ๆ (TIKTOK_ACCESS_TOKEN / TIKTOK_MAIN_ACCESS_TOKEN / TIKTOK_AD_TOKEN)
           3.2) หรือ refresh token จาก .env (TIKTOK_CLIENT_ID/SECRET/REFRESH_TOKEN)
        """
        db_settings = cls._get_db_settings()

        # 1) token ตรง ๆ ใน DB
        direct_db_token = db_settings.get("tiktok_access_token")
        if direct_db_token:
            return direct_db_token

        # 2) refresh flow จาก DB
        client_id = db_settings.get("tiktok_client_id")
        client_secret = db_settings.get("tiktok_client_secret")
        refresh_token = db_settings.get("tiktok_refresh_token")

        # 3) ถ้า DB ไม่มี ค่อย fallback ไปใช้ .env
        if not (client_id and client_secret and refresh_token):
            # 3.1 direct token จาก .env
            direct_env_token = settings.tiktok_content_access_token
            if direct_env_token:
                return direct_env_token

            # 3.2 refresh จาก .env
            client_id = settings.TIKTOK_CLIENT_ID
            client_secret = settings.TIKTOK_CLIENT_SECRET
            refresh_token = settings.TIKTOK_REFRESH_TOKEN

        if not (client_id and client_secret and refresh_token):
            print("[TikTokService] No TikTok credentials configured (DB or .env).")
            return None

        url = f"{settings.TIKTOK_API_BASE_URL}/tt_user/oauth2/refresh_token/"
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code != 200:
                    print(
                        f"[TikTokService] Failed to refresh access token: {resp.status_code} {resp.text}"
                    )
                    return None

                data = resp.json()
                access_token = (
                    data.get("data", {}).get("access_token")
                    if isinstance(data, dict)
                    else None
                )
                if not access_token:
                    print(
                        f"[TikTokService] No access_token field in refresh response: {data}"
                    )
                    return None

                return access_token
        except Exception as e:
            print(f"[TikTokService] Error refreshing access token: {e}")
            return None

    @staticmethod
    def _get_db_settings() -> Dict[str, str]:
        """Load TikTok-related settings from DB (category='tiktok')."""
        db = SessionLocal()
        try:
            rows = (
                db.query(AppSetting)
                .filter(AppSetting.category == "tiktok")
                .all()
            )
            return {row.key: row.value for row in rows if row.value is not None}
        finally:
            db.close()

    @classmethod
    def get_business_id(cls) -> Optional[str]:
        """Get TikTok business_id (prefer DB, fall back to .env)."""
        db_settings = cls._get_db_settings()
        return db_settings.get("tiktok_business_id") or settings.tiktok_business_id

    @classmethod
    def get_official_channels(cls) -> List[str]:
        """
        Get list of official company channels.
        ลำดับความสำคัญ:
        1) จาก DB (app_settings.key='tiktok_official_channels')
        2) ถ้าไม่มี ใช้ DEFAULT_OFFICIAL_CHANNELS
        """
        db_settings = cls._get_db_settings()
        raw = db_settings.get("tiktok_official_channels")
        if raw:
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, list):
                    return [str(x).strip() for x in loaded if str(x).strip()]
            except Exception:
                pass
        return cls.DEFAULT_OFFICIAL_CHANNELS
    
    @staticmethod
    def get_videos_list(access_token: str, business_id: str, cursor: str = None) -> Optional[Dict]:
        """Fetch videos list from TikTok Business API"""
        if not access_token:
            return None
        
        url = f"{TikTokService.BASE_URL}/business/video/list/"
        
        params = {
            "business_id": business_id,
            "fields": json.dumps([
                "item_id", "create_time", "thumbnail_url", "share_url", "caption",
                "video_views", "likes", "comments", "shares", "reach", "video_duration",
                "full_video_watched_rate", "total_time_watched", "average_time_watched",
                "impression_sources"
            ]),
            "max_count": 20
        }
        
        if cursor:
            params["cursor"] = cursor
        
        headers = {
            "Access-Token": access_token
        }
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url, headers=headers, params=params)
                response.raise_for_status()
                return response.json()
        except Exception as e:
            print(f"Error fetching videos: {e}")
            return None
    
    @staticmethod
    def get_item_detail(item_id: str) -> Optional[Dict]:
        """Get detailed item info from external API"""
        url = f"{TikTokService.ITEM_DETAIL_API}/{item_id}"
        
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.get(url)
                if response.status_code != 200:
                    return None
                
                data = response.json()
                if 'error' in data:
                    return None
                return data
        except Exception as e:
            print(f"Error getting item detail for {item_id}: {e}")
            return None
    
    @staticmethod
    def get_item_details_concurrently(item_ids: List[str], max_workers: int = 10) -> Tuple[List[Dict], List[str]]:
        """Fetch item details concurrently"""
        item_details = []
        failed_ids = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_id = {
                executor.submit(TikTokService.get_item_detail, item_id): item_id 
                for item_id in item_ids
            }
            
            for future in as_completed(future_to_id):
                item_id = future_to_id[future]
                try:
                    detail = future.result()
                    if detail:
                        item_details.append(detail)
                    else:
                        failed_ids.append(item_id)
                except Exception as e:
                    print(f"Error for {item_id}: {e}")
                    failed_ids.append(item_id)
        
        return item_details, failed_ids
    
    @staticmethod
    def extract_channel_from_url(share_url: str) -> Optional[str]:
        """Extract channel username from share URL"""
        match = re.search(r"@([^/]+)/video", share_url)
        if match:
            return match.group(1)
        return None
    
    @staticmethod
    def determine_content_source(channel_acc_id: str) -> ContentSource:
        """Determine content source based on channel"""
        if not channel_acc_id:
            return ContentSource.INFLUENCER

        official_channels = TikTokService.get_official_channels()
        if channel_acc_id in official_channels:
            return ContentSource.PAGE
        return ContentSource.INFLUENCER
    
    @staticmethod
    def calculate_pfm_score(video_views: int, likes: int, comments: int, 
                           shares: int, bookmarks: int = 0) -> Decimal:
        """
        Calculate PFM (Performance Factor Multiplier) score
        Based on engagement metrics relative to view count
        """
        try:
            video_views = float(video_views or 0)
            likes = float(likes or 0)
            comments = float(comments or 0)
            shares = float(shares or 0)
            bookmarks = float(bookmarks or 0)
        except (ValueError, TypeError):
            return Decimal("0")
        
        if video_views <= 0:
            return Decimal("0")
        
        # Adjust likes with bookmarks (1 bookmark = 10 likes)
        adjusted_likes = likes + (bookmarks * 10)
        
        # Set targets based on view count tiers
        if video_views < 10000:
            target_comments = 0.018
            target_shares = 0.07
            target_likes = 12
        elif video_views < 50000:
            target_comments = 0.016
            target_shares = 0.05
            target_likes = 10
        elif video_views < 100000:
            target_comments = 0.013
            target_shares = 0.04
            target_likes = 7
        elif video_views < 500000:
            target_comments = 0.01
            target_shares = 0.035
            target_likes = 4
        elif video_views < 1000000:
            target_comments = 0.009
            target_shares = 0.025
            target_likes = 1.8
        elif video_views < 5000000:
            target_comments = 0.004
            target_shares = 0.02
            target_likes = 1.5
        elif video_views < 10000000:
            target_comments = 0.003
            target_shares = 0.015
            target_likes = 1.2
        else:
            target_comments = 0.002
            target_shares = 0.01
            target_likes = 1
        
        # Calculate normalized scores
        view_target_comments = (video_views * target_comments) / 100
        view_target_shares = (video_views * target_shares) / 100
        view_target_likes = (video_views * target_likes) / 100
        
        norm_comments = (comments / view_target_comments) if view_target_comments > 0 else 0
        norm_shares = (shares / view_target_shares) if view_target_shares > 0 else 0
        norm_likes = (adjusted_likes / view_target_likes) if view_target_likes > 0 else 0
        
        # Calculate final score (weighted average)
        # Comments: 45%, Shares: 35%, Likes: 25%
        score = (norm_comments * 45 + norm_shares * 35 + norm_likes * 25) / 100
        
        return Decimal(str(round(score, 2)))
    
    @staticmethod
    def sync_videos_to_db(videos: List[Dict], db: Session) -> int:
        """Sync videos to database"""
        synced_count = 0
        
        for video in videos:
            try:
                item_id = video.get('item_id')
                if not item_id:
                    continue
                
                # Check if content exists
                content = db.query(Content).filter(
                    Content.platform == Platform.TIKTOK,
                    Content.platform_post_id == item_id
                ).first()
                
                # Extract channel info
                share_url = video.get('share_url', '')
                channel_acc_id = TikTokService.extract_channel_from_url(share_url)
                content_source = TikTokService.determine_content_source(channel_acc_id) if channel_acc_id else None
                
                # Parse create time
                create_time = None
                if video.get('create_time'):
                    try:
                        create_time = datetime.fromtimestamp(int(video['create_time']))
                    except:
                        pass
                
                # Calculate PFM
                pfm_score = TikTokService.calculate_pfm_score(
                    video.get('video_views', 0),
                    video.get('likes', 0),
                    video.get('comments', 0),
                    video.get('shares', 0),
                    0  # bookmarks not in list API
                )
                
                if content:
                    # Update existing
                    content.url = share_url
                    content.caption = video.get('caption', '')
                    content.thumbnail_url = video.get('thumbnail_url', '')
                    content.video_duration = Decimal(str(video.get('video_duration', 0)))
                    content.views = video.get('video_views', 0)
                    content.likes = video.get('likes', 0)
                    content.comments = video.get('comments', 0)
                    content.shares = video.get('shares', 0)
                    content.reach = video.get('reach', 0)
                    content.total_watch_time = Decimal(str(video.get('total_time_watched', 0)))
                    content.avg_watch_time = Decimal(str(video.get('average_time_watched', 0)))
                    content.completion_rate = Decimal(str(video.get('full_video_watched_rate', 0) * 100))
                    content.pfm_score = pfm_score
                    content.platform_metrics = {
                        'impression_sources': video.get('impression_sources', [])
                    }
                    content.creator_name = channel_acc_id
                else:
                    # Create new
                    content = Content(
                        platform=Platform.TIKTOK,
                        platform_post_id=item_id,
                        url=share_url,
                        caption=video.get('caption', ''),
                        thumbnail_url=video.get('thumbnail_url', ''),
                        platform_created_at=create_time,
                        content_source=content_source,
                        status=ContentStatus.READY,
                        video_duration=Decimal(str(video.get('video_duration', 0))),
                        views=video.get('video_views', 0),
                        likes=video.get('likes', 0),
                        comments=video.get('comments', 0),
                        shares=video.get('shares', 0),
                        reach=video.get('reach', 0),
                        total_watch_time=Decimal(str(video.get('total_time_watched', 0))),
                        avg_watch_time=Decimal(str(video.get('average_time_watched', 0))),
                        completion_rate=Decimal(str(video.get('full_video_watched_rate', 0) * 100)),
                        pfm_score=pfm_score,
                        platform_metrics={
                            'impression_sources': video.get('impression_sources', [])
                        },
                        creator_name=channel_acc_id,
                        creator_id=channel_acc_id,
                    )
                    db.add(content)
                
                synced_count += 1
                
            except Exception as e:
                print(f"Error syncing video {video.get('item_id')}: {e}")
                continue
        
        db.commit()
        return synced_count
    
    @staticmethod
    def update_content_details(item_details: List[Dict], db: Session) -> int:
        """Update content with detailed info (including bookmarks)"""
        updated_count = 0
        
        for detail in item_details:
            try:
                item_id = detail.get('item_id')
                if not item_id:
                    continue
                
                content = db.query(Content).filter(
                    Content.platform == Platform.TIKTOK,
                    Content.platform_post_id == item_id
                ).first()
                
                if not content:
                    continue
                
                # Update with detailed info
                content.views = detail.get('video_views', content.views)
                content.likes = detail.get('likes', content.likes)
                content.comments = detail.get('comments', content.comments)
                content.shares = detail.get('shares', content.shares)
                content.saves = detail.get('bookmarks', 0)  # bookmarks = saves
                
                # Recalculate PFM with bookmarks
                content.pfm_score = TikTokService.calculate_pfm_score(
                    content.views,
                    content.likes,
                    content.comments,
                    content.shares,
                    content.saves
                )
                
                # Update creator info
                if detail.get('author'):
                    content.creator_name = detail['author']
                    content.creator_id = detail['author']
                    content.content_source = TikTokService.determine_content_source(detail['author'])
                
                updated_count += 1
                
            except Exception as e:
                print(f"Error updating content {detail.get('item_id')}: {e}")
                continue
        
        db.commit()
        return updated_count
    
    @classmethod
    def fetch_and_sync_all_videos(cls, access_token: str, business_id: str, 
                                   fetch_type: str = "latest") -> Dict:
        """
        Fetch all videos from TikTok and sync to database
        
        Args:
            access_token: TikTok access token
            business_id: TikTok business ID
            fetch_type: "latest" (first 3 pages) or "all" (all pages)
        
        Returns:
            Dict with sync results
        """
        db = SessionLocal()
        cursor = None
        total_fetched = 0
        total_synced = 0
        fetch_idx = 0
        max_pages = 3 if fetch_type == "latest" else None  # "all" จะรันจนกว่า has_more=False
        
        try:
            while True:
                # Fetch videos
                response = cls.get_videos_list(access_token, business_id, cursor)
                fetch_idx += 1
                
                if not response:
                    break
                
                videos = response.get('data', {}).get('videos', [])
                if not videos:
                    break
                
                total_fetched += len(videos)
                print(f"Fetched {total_fetched} videos (page {fetch_idx})...")
                
                # Sync to database
                synced = cls.sync_videos_to_db(videos, db)
                total_synced += synced
                
                # Check for more pages
                cursor = response.get('data', {}).get('cursor')
                has_more = response.get('data', {}).get('has_more', False)
                
                # หยุดถ้าไม่มีหน้าเพิ่ม หรือไม่มี cursor
                if not has_more or not cursor:
                    break

                # สำหรับโหมด "latest" ให้จำกัดจำนวนหน้า
                if max_pages is not None and fetch_idx >= max_pages:
                    break
            
            return {
                "success": True,
                "total_fetched": total_fetched,
                "total_synced": total_synced,
                "pages_processed": fetch_idx
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "total_fetched": total_fetched,
                "total_synced": total_synced
            }
        finally:
            db.close()
    
    @classmethod
    def update_all_pfm_scores(cls) -> int:
        """Update PFM scores for all TikTok content"""
        db = SessionLocal()
        updated = 0
        
        try:
            contents = db.query(Content).filter(
                Content.platform == Platform.TIKTOK,
                Content.deleted_at.is_(None)
            ).all()
            
            for content in contents:
                old_score = content.pfm_score
                new_score = cls.calculate_pfm_score(
                    content.views or 0,
                    content.likes or 0,
                    content.comments or 0,
                    content.shares or 0,
                    content.saves or 0
                )
                
                if old_score != new_score:
                    content.pfm_score = new_score
                    updated += 1
            
            db.commit()
            return updated
            
        finally:
            db.close()

