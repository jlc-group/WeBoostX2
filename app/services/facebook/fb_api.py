"""
Facebook Graph API Client
Compatible with Graph API v23.0
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime, timedelta

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Facebook Graph API Base URL
FB_GRAPH_API_BASE = "https://graph.facebook.com/v23.0"


class FacebookAPI:
    """
    Facebook Graph API Client for fetching posts, insights, and ads data.
    """

    def __init__(
        self,
        page_access_token: Optional[str] = None,
        user_access_token: Optional[str] = None,
        page_id: Optional[str] = None,
    ):
        # Use settings for tokens (loaded from .env)
        self.page_access_token = page_access_token or settings.fb_page_access_token
        self.user_access_token = user_access_token or settings.FB_USER_ACCESS_TOKEN
        self.page_id = page_id
        self._client: Optional[httpx.AsyncClient] = None

    @staticmethod
    def get_page_ids() -> List[str]:
        """Get all page IDs from settings"""
        return settings.fb_page_ids

    @staticmethod
    def get_ad_account_ids() -> List[str]:
        """Get all ad account IDs from settings"""
        return settings.fb_ad_account_ids

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ========================================
    # Posts API
    # ========================================

    async def fetch_posts(
        self,
        page_id: Optional[str] = None,
        days_back: int = 365,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Fetch posts from a Facebook page.

        Args:
            page_id: Facebook Page ID
            days_back: Number of days to look back
            limit: Number of posts per request

        Returns:
            List of post data
        """
        page_id = page_id or self.page_id
        if not page_id:
            raise ValueError("page_id is required")

        # Calculate since timestamp
        since_date = datetime.now() - timedelta(days=days_back)
        since_timestamp = int(since_date.timestamp())

        url = f"{FB_GRAPH_API_BASE}/{page_id}/feed"
        params = {
            "fields": "id,created_time,message,story,is_published,is_hidden,permalink_url,full_picture",
            "limit": limit,
            "since": since_timestamp,
            "access_token": self.page_access_token,
        }

        all_posts = []

        while url:
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    logger.error(f"Facebook API Error: {data['error']['message']}")
                    break

                posts = data.get("data", [])
                all_posts.extend(posts)

                logger.info(f"Fetched {len(posts)} posts (Total: {len(all_posts)})")

                # Get next page URL
                paging = data.get("paging", {})
                url = paging.get("next")
                params = None  # Next URL contains all params

            except httpx.HTTPError as e:
                logger.error(f"HTTP Error fetching posts: {e}")
                break
            except Exception as e:
                logger.error(f"Error fetching posts: {e}")
                break

        return all_posts

    async def fetch_post_attachments(
        self,
        post_id: str,
    ) -> List[Dict[str, Any]]:
        """Fetch attachments for a specific post"""
        url = f"{FB_GRAPH_API_BASE}/{post_id}/attachments"
        params = {
            "fields": "media,type,description,title",
            "access_token": self.page_access_token,
        }

        try:
            response = await self.client.get(url, params=params)
            if response.status_code != 200:
                return []

            data = response.json()
            if "error" in data:
                return []

            return data.get("data", [])

        except Exception as e:
            logger.warning(f"Error fetching attachments for {post_id}: {e}")
            return []

    async def fetch_post_insights(
        self,
        post_id: str,
    ) -> Dict[str, Any]:
        """
        Fetch insights for a specific post.
        Returns aggregated metrics.
        """
        # Safe metrics (not deprecated in v23.0)
        safe_metrics = [
            "post_impressions",
            "post_impressions_unique",
            "post_clicks",
            "post_reactions_by_type_total",
        ]

        insights = {}

        # Fetch API metrics
        for metric in safe_metrics:
            try:
                url = f"{FB_GRAPH_API_BASE}/{post_id}/insights"
                params = {
                    "metric": metric,
                    "access_token": self.page_access_token,
                }

                response = await self.client.get(url, params=params)
                if response.status_code != 200:
                    continue

                data = response.json()
                if "error" in data:
                    continue

                for insight in data.get("data", []):
                    values = insight.get("values", [{}])
                    if values:
                        value = values[0].get("value", 0)
                        insights[insight.get("name")] = value

            except Exception as e:
                logger.warning(f"Error fetching metric {metric}: {e}")
                continue

        # Fetch engagement data
        try:
            url = f"{FB_GRAPH_API_BASE}/{post_id}"
            params = {
                "fields": "shares,comments.summary(true),likes.summary(true)",
                "access_token": self.page_access_token,
            }

            response = await self.client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()

                insights["shares"] = data.get("shares", {}).get("count", 0)
                insights["comments"] = data.get("comments", {}).get("summary", {}).get("total_count", 0)
                insights["likes"] = data.get("likes", {}).get("summary", {}).get("total_count", 0)

        except Exception as e:
            logger.warning(f"Error fetching engagement: {e}")

        return insights

    # ========================================
    # Video Posts API
    # ========================================

    async def fetch_video_posts(
        self,
        page_id: Optional[str] = None,
        days_back: int = 365,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch video posts from a Facebook page"""
        page_id = page_id or self.page_id
        if not page_id:
            raise ValueError("page_id is required")

        url = f"{FB_GRAPH_API_BASE}/{page_id}/videos"
        params = {
            "fields": "id,title,description,created_time,length,source,picture,permalink_url,views",
            "limit": limit,
            "access_token": self.page_access_token,
        }

        all_videos = []

        while url:
            try:
                response = await self.client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    logger.error(f"Facebook API Error: {data['error']['message']}")
                    break

                videos = data.get("data", [])
                all_videos.extend(videos)

                # Filter by date
                since_date = datetime.now() - timedelta(days=days_back)
                all_videos = [
                    v for v in all_videos
                    if self._parse_datetime(v.get("created_time")) >= since_date
                ]

                # Get next page
                paging = data.get("paging", {})
                url = paging.get("next")
                params = None

            except Exception as e:
                logger.error(f"Error fetching videos: {e}")
                break

        return all_videos

    # ========================================
    # Ads API
    # ========================================

    async def fetch_ad_accounts(self) -> List[Dict[str, Any]]:
        """Fetch ad accounts for the user"""
        url = f"{FB_GRAPH_API_BASE}/me/adaccounts"
        params = {
            "fields": "id,name,account_status,currency,timezone_name",
            "access_token": self.user_access_token or self.page_access_token,
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Error fetching ad accounts: {e}")
            return []

    async def fetch_campaigns(
        self,
        ad_account_id: str,
    ) -> List[Dict[str, Any]]:
        """Fetch campaigns for an ad account"""
        # Ensure act_ prefix
        if not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"

        url = f"{FB_GRAPH_API_BASE}/{ad_account_id}/campaigns"
        params = {
            "fields": "id,name,status,objective,daily_budget,lifetime_budget,start_time,stop_time",
            "limit": 100,
            "access_token": self.user_access_token or self.page_access_token,
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Error fetching campaigns: {e}")
            return []

    async def fetch_adsets(
        self,
        campaign_id: str,
    ) -> List[Dict[str, Any]]:
        """Fetch adsets for a campaign"""
        url = f"{FB_GRAPH_API_BASE}/{campaign_id}/adsets"
        params = {
            "fields": "id,name,status,optimization_goal,billing_event,daily_budget,targeting",
            "limit": 100,
            "access_token": self.user_access_token or self.page_access_token,
        }

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Error fetching adsets: {e}")
            return []

    async def fetch_ads_insights(
        self,
        ad_account_id: str,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch ads insights for date range"""
        if not ad_account_id.startswith("act_"):
            ad_account_id = f"act_{ad_account_id}"

        url = f"{FB_GRAPH_API_BASE}/{ad_account_id}/insights"
        params = {
            "fields": "campaign_id,adset_id,ad_id,impressions,reach,clicks,spend,ctr,cpc,cpm,actions",
            "level": "ad",
            "access_token": self.user_access_token or self.page_access_token,
        }

        if date_start:
            params["time_range"] = f'{{"since":"{date_start}","until":"{date_end or date_start}"}}'

        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("data", [])
        except Exception as e:
            logger.error(f"Error fetching insights: {e}")
            return []

    # ========================================
    # Utilities
    # ========================================

    @staticmethod
    def _parse_datetime(datetime_str: Optional[str]) -> datetime:
        """Parse Facebook datetime string"""
        if not datetime_str:
            return datetime.min
        try:
            return datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
        except Exception:
            return datetime.min

    @staticmethod
    def is_video_post(permalink_url: Optional[str], message: Optional[str] = None) -> bool:
        """Check if a post is a video based on URL patterns"""
        if not permalink_url:
            return False

        video_patterns = [
            "/videos/",
            "facebook.com/watch",
            "facebook.com/video",
            "fb.watch",
            "/reel/",
        ]

        for pattern in video_patterns:
            if pattern in permalink_url:
                return True

        return False
