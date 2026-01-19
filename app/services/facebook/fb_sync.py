"""
Facebook Sync Service
Syncs Facebook posts and ads data to WeBoostX database
"""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.models.content import Content
from app.models.campaign import Campaign, AdGroup, Ad
from app.models.platform import AdAccount
from app.models.enums import Platform, ContentStatus
from app.services.facebook.fb_api import FacebookAPI

logger = logging.getLogger(__name__)


class FacebookSyncService:
    """
    Service for syncing Facebook data to WeBoostX database.
    Uses unified Content/Campaign models (same as TikTok).
    """

    def __init__(self, db: Session, page_access_token: Optional[str] = None):
        self.db = db
        self.api = FacebookAPI(page_access_token=page_access_token)

    async def close(self):
        """Close API client"""
        await self.api.close()

    # ========================================
    # Content Sync (Posts)
    # ========================================

    async def sync_posts(
        self,
        page_id: str,
        ad_account_id: Optional[int] = None,
        days_back: int = 365,
        batch_size: int = 10,
        skip_insights: bool = False,
    ) -> Dict[str, int]:
        """
        Sync Facebook posts to Content table.

        Args:
            page_id: Facebook Page ID
            ad_account_id: WeBoostX AdAccount ID (FK)
            days_back: Days to look back
            batch_size: Commit every N posts for faster response
            skip_insights: Skip fetching insights (faster but no metrics)

        Returns:
            Stats dict with created/updated/skipped counts
        """
        stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}

        logger.info(f"Starting Facebook posts sync for page {page_id}")

        try:
            posts = await self.api.fetch_posts(page_id=page_id, days_back=days_back)
            logger.info(f"Fetched {len(posts)} posts from Facebook")

            for i, post in enumerate(posts):
                try:
                    result = await self._upsert_post(
                        post, page_id, ad_account_id, skip_insights=skip_insights
                    )
                    stats[result] += 1

                    # Commit every batch_size records
                    if (i + 1) % batch_size == 0:
                        self.db.commit()
                        logger.info(f"Committed batch {(i + 1) // batch_size}: {stats}")

                except Exception as e:
                    logger.error(f"Error upserting post {post.get('id')}: {e}")
                    stats["errors"] += 1

            # Final commit
            self.db.commit()
            logger.info(f"Sync complete: {stats}")

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            self.db.rollback()
            raise

        return stats

    async def _upsert_post(
        self,
        post_data: Dict[str, Any],
        page_id: str,
        ad_account_id: Optional[int],
        skip_videos: bool = False,
        skip_insights: bool = False,
    ) -> str:
        """Insert or update a single post"""
        post_id = post_data.get("id")
        permalink = post_data.get("permalink_url", "")

        # Optionally skip video posts (if syncing videos separately)
        if skip_videos and self.api.is_video_post(permalink, post_data.get("message")):
            logger.debug(f"Skipping video post: {post_id}")
            return "skipped"

        # Check if exists
        existing = self.db.query(Content).filter(
            Content.platform == Platform.FACEBOOK,
            Content.platform_post_id == post_id,
        ).first()

        # Parse created_time
        created_time = None
        if post_data.get("created_time"):
            try:
                created_time = datetime.fromisoformat(
                    post_data["created_time"].replace("Z", "+00:00")
                )
            except Exception:
                pass

        # Fetch insights (skip if flag set for faster sync)
        insights = {}
        if not skip_insights:
            insights = await self.api.fetch_post_insights(post_id)

        # Get thumbnail URL (column is now TEXT, no truncation needed)
        thumbnail = post_data.get("full_picture") or None

        content_data = {
            "platform": Platform.FACEBOOK,
            "platform_post_id": post_id,
            "ad_account_id": ad_account_id,
            "url": permalink or None,
            "caption": post_data.get("message") or post_data.get("story"),
            "thumbnail_url": thumbnail,
            "platform_created_at": created_time,
            "status": ContentStatus.READY,
            # Metrics from insights
            "impressions": insights.get("post_impressions", 0),
            "reach": insights.get("post_impressions_unique", 0),
            "likes": insights.get("likes", 0),
            "comments": insights.get("comments", 0),
            "shares": insights.get("shares", 0),
            # Platform-specific data
            "platform_metrics": {
                "page_id": page_id,
                "is_published": post_data.get("is_published", True),
                "is_hidden": post_data.get("is_hidden", False),
                "reactions_by_type": insights.get("post_reactions_by_type_total"),
                "clicks": insights.get("post_clicks", 0),
            },
        }

        if existing:
            # Update existing
            for key, value in content_data.items():
                if value is not None:
                    setattr(existing, key, value)
            return "updated"
        else:
            # Create new
            content = Content(**content_data)
            self.db.add(content)
            return "created"

    # ========================================
    # Video Posts Sync
    # ========================================

    async def sync_video_posts(
        self,
        page_id: str,
        ad_account_id: Optional[int] = None,
        days_back: int = 365,
    ) -> Dict[str, int]:
        """Sync Facebook video posts to Content table"""
        stats = {"created": 0, "updated": 0, "errors": 0}

        logger.info(f"Starting Facebook video sync for page {page_id}")

        try:
            videos = await self.api.fetch_video_posts(page_id=page_id, days_back=days_back)
            logger.info(f"Fetched {len(videos)} videos from Facebook")

            for video in videos:
                try:
                    result = await self._upsert_video(video, page_id, ad_account_id)
                    stats[result] += 1
                except Exception as e:
                    logger.error(f"Error upserting video {video.get('id')}: {e}")
                    stats["errors"] += 1

            self.db.commit()
            logger.info(f"Video sync complete: {stats}")

        except Exception as e:
            logger.error(f"Video sync failed: {e}")
            self.db.rollback()
            raise

        return stats

    async def _upsert_video(
        self,
        video_data: Dict[str, Any],
        page_id: str,
        ad_account_id: Optional[int],
    ) -> str:
        """Insert or update a video post"""
        video_id = video_data.get("id")

        existing = self.db.query(Content).filter(
            Content.platform == Platform.FACEBOOK,
            Content.platform_post_id == video_id,
        ).first()

        # Parse created_time
        created_time = None
        if video_data.get("created_time"):
            try:
                created_time = datetime.fromisoformat(
                    video_data["created_time"].replace("Z", "+00:00")
                )
            except Exception:
                pass

        content_data = {
            "platform": Platform.FACEBOOK,
            "platform_post_id": video_id,
            "ad_account_id": ad_account_id,
            "url": video_data.get("permalink_url"),
            "caption": video_data.get("title") or video_data.get("description"),
            "thumbnail_url": video_data.get("picture"),
            "platform_created_at": created_time,
            "status": ContentStatus.READY,
            "video_duration": video_data.get("length"),
            "views": video_data.get("views", 0),
            "platform_metrics": {
                "page_id": page_id,
                "source": video_data.get("source"),
            },
        }

        if existing:
            for key, value in content_data.items():
                if value is not None:
                    setattr(existing, key, value)
            return "updated"
        else:
            content = Content(**content_data)
            self.db.add(content)
            return "created"

    # ========================================
    # Campaigns & Ads Sync
    # ========================================

    async def sync_campaigns(
        self,
        ad_account_external_id: str,
        ad_account_id: int,
    ) -> Dict[str, int]:
        """Sync Facebook campaigns to Campaign table"""
        stats = {"created": 0, "updated": 0, "errors": 0}

        logger.info(f"Syncing campaigns for ad account {ad_account_external_id}")

        try:
            campaigns = await self.api.fetch_campaigns(ad_account_external_id)
            logger.info(f"Fetched {len(campaigns)} campaigns")

            for campaign_data in campaigns:
                try:
                    result = self._upsert_campaign(campaign_data, ad_account_id)
                    stats[result] += 1
                except Exception as e:
                    logger.error(f"Error upserting campaign: {e}")
                    stats["errors"] += 1

            self.db.commit()

        except Exception as e:
            logger.error(f"Campaign sync failed: {e}")
            self.db.rollback()
            raise

        return stats

    def _upsert_campaign(self, campaign_data: Dict[str, Any], ad_account_id: int) -> str:
        """Insert or update a campaign"""
        external_id = campaign_data.get("id")

        existing = self.db.query(Campaign).filter(
            Campaign.platform == Platform.FACEBOOK,
            Campaign.external_campaign_id == external_id,
        ).first()

        data = {
            "platform": Platform.FACEBOOK,
            "ad_account_id": ad_account_id,
            "external_campaign_id": external_id,
            "name": campaign_data.get("name", ""),
            "objective_raw": campaign_data.get("objective"),
            "daily_budget": campaign_data.get("daily_budget"),
            "lifetime_budget": campaign_data.get("lifetime_budget"),
            "platform_data": campaign_data,
            "last_synced_at": datetime.utcnow(),
        }

        if existing:
            for key, value in data.items():
                if value is not None:
                    setattr(existing, key, value)
            return "updated"
        else:
            campaign = Campaign(**data)
            self.db.add(campaign)
            return "created"

    # ========================================
    # Ad Accounts Sync
    # ========================================

    async def sync_ad_accounts(self) -> List[AdAccount]:
        """Sync Facebook ad accounts"""
        accounts_data = await self.api.fetch_ad_accounts()
        synced = []

        for acc in accounts_data:
            external_id = acc.get("id", "").replace("act_", "")

            existing = self.db.query(AdAccount).filter(
                AdAccount.platform == Platform.FACEBOOK,
                AdAccount.external_account_id == external_id,
            ).first()

            if existing:
                existing.name = acc.get("name", existing.name)
                existing.currency = acc.get("currency", "THB")
                existing.timezone = acc.get("timezone_name")
                synced.append(existing)
            else:
                new_account = AdAccount(
                    platform=Platform.FACEBOOK,
                    external_account_id=external_id,
                    name=acc.get("name", f"FB Account {external_id}"),
                    currency=acc.get("currency", "THB"),
                    timezone=acc.get("timezone_name"),
                )
                self.db.add(new_account)
                synced.append(new_account)

        self.db.commit()
        return synced
