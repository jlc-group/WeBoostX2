"""
Facebook Legacy Database Mapper

Maps data from existing Facebook tables (localhost:5433/postgres)
to WeBoostX 2.0 models for Dashboard display.

This is READ-ONLY - does not modify the legacy database.
"""
import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)


class FacebookLegacyDB:
    """
    Read-only connection to legacy Facebook database
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5433,
        user: str = "postgres",
        password: str = "Ais@9894",
        database: str = "postgres"
    ):
        self.params = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database
        }
        self._conn = None
    
    def connect(self):
        """Get connection"""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(**self.params)
            self._conn.autocommit = True  # Enable autocommit to avoid transaction issues
        return self._conn
    
    def close(self):
        """Close connection"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None
    
    def query(self, sql: str, params: tuple = None) -> List[Dict]:
        """Execute query and return results as list of dicts"""
        conn = self.connect()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            # Reconnect on error to clear any bad state
            self.close()
            raise e
    
    def query_one(self, sql: str, params: tuple = None) -> Optional[Dict]:
        """Execute query and return single result"""
        results = self.query(sql, params)
        return results[0] if results else None
    
    def safe_count(self, table_name: str) -> int:
        """Safely get count from a table, returns 0 if table doesn't exist"""
        try:
            result = self.query_one(f'SELECT COUNT(*) as c FROM "{table_name}"')
            return result['c'] if result else 0
        except Exception as e:
            logger.warning(f"Error counting {table_name}: {e}")
            return 0


class FacebookLegacyMapper:
    """
    Maps legacy Facebook data to WeBoostX 2.0 format
    """
    
    def __init__(self, db: FacebookLegacyDB = None):
        self.db = db or FacebookLegacyDB()
    
    # ========================================
    # Pages (-> AdAccount-like)
    # ========================================
    
    def get_pages(self) -> List[Dict]:
        """Get all Facebook pages"""
        sql = """
            SELECT 
                id,
                name,
                category,
                likes,
                followers_count,
                picture_url,
                cover_photo_url,
                access_token,
                created_at,
                updated_at
            FROM facebook_pages
            ORDER BY name
        """
        return self.db.query(sql)
    
    def get_page_by_id(self, page_id: str) -> Optional[Dict]:
        """Get single page by ID"""
        sql = "SELECT * FROM facebook_pages WHERE id = %s"
        return self.db.query_one(sql, (page_id,))
    
    # ========================================
    # Posts (-> Content)
    # ========================================
    
    def get_posts(
        self,
        page_id: str = None,
        limit: int = 100,
        offset: int = 0,
        post_type: str = None,
    ) -> List[Dict]:
        """
        Get Facebook posts with performance data
        Maps to WeBoostX Content model
        """
        sql = """
            SELECT 
                p.id,
                p.page_id,
                p.message,
                p.story,
                p.type,
                p.permalink_url,
                p.picture_url,
                p.full_picture_url,
                p.video_url,
                p.created_time,
                p.updated_time,
                p.is_published,
                p.is_hidden,
                p.created_at,
                p.updated_at,
                -- Performance data (use correct column names)
                pp.post_type as perf_post_type,
                pp.thumbnail_url,
                pp.video_views,
                pp.likes,
                pp.comments,
                pp.shares,
                pp.reach,
                pp.impressions,
                pp.engagement_rate,
                pp.pfm_score as performance_score,
                pp.ads_count,
                pp.ads_total_media_cost as ads_total_cost,
                pp.boost_factor,
                pp.boost_start_date,
                pp.boost_expire_date,
                pp.products,
                pp.content_type,
                pp.content_status
            FROM facebook_posts p
            LEFT JOIN facebook_posts_performance pp ON p.id = pp.post_id
            WHERE 1=1
        """
        params = []
        
        if page_id:
            sql += " AND p.page_id = %s"
            params.append(page_id)
        
        if post_type:
            sql += " AND p.type = %s"
            params.append(post_type)
        
        sql += " ORDER BY p.created_time DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        return self.db.query(sql, tuple(params))
    
    def get_post_by_id(self, post_id: str) -> Optional[Dict]:
        """Get single post with all details"""
        sql = """
            SELECT 
                p.*,
                pp.post_type as perf_post_type,
                pp.video_views,
                pp.likes,
                pp.comments,
                pp.shares,
                pp.reach,
                pp.impressions,
                pp.engagement_rate,
                pp.pfm_score as performance_score,
                pp.ads_count,
                pp.ads_total_media_cost as ads_total_cost,
                pg.name as page_name
            FROM facebook_posts p
            LEFT JOIN facebook_posts_performance pp ON p.id = pp.post_id
            LEFT JOIN facebook_pages pg ON p.page_id = pg.id
            WHERE p.id = %s
        """
        return self.db.query_one(sql, (post_id,))
    
    def get_posts_count(self, page_id: str = None) -> int:
        """Get total posts count"""
        sql = "SELECT COUNT(*) as count FROM facebook_posts"
        params = []
        if page_id:
            sql += " WHERE page_id = %s"
            params.append(page_id)
        result = self.db.query_one(sql, tuple(params) if params else None)
        return result['count'] if result else 0
    
    def get_post_insights(self, post_id: str) -> List[Dict]:
        """Get insights for a post"""
        sql = """
            SELECT 
                metric_name,
                value,
                value_numeric,
                value_json,
                date_recorded
            FROM facebook_post_insights
            WHERE post_id = %s
            ORDER BY date_recorded DESC
        """
        return self.db.query(sql, (post_id,))
    
    # ========================================
    # Videos (-> Content with video type)
    # ========================================
    
    def get_video_posts(
        self,
        page_id: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict]:
        """Get Facebook video posts"""
        sql = """
            SELECT 
                v.video_id,
                v.post_id,
                v.page_id,
                v.title,
                v.description,
                v.created_time,
                v.permalink_url,
                v.source,
                v.picture,
                v.length,
                v.video_type,
                v.created_at,
                v.updated_at,
                -- Video insights
                vi.total_video_views,
                vi.total_video_views_unique,
                vi.total_video_complete_views,
                vi.total_video_views_organic,
                vi.total_video_views_paid
            FROM facebook_video_posts v
            LEFT JOIN facebook_video_insights vi ON v.video_id = vi.video_id
            WHERE 1=1
        """
        params = []
        
        if page_id:
            sql += " AND v.page_id = %s"
            params.append(page_id)
        
        sql += " ORDER BY v.created_time DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        return self.db.query(sql, tuple(params))
    
    # ========================================
    # Campaigns (-> Campaign)
    # ========================================
    
    def get_campaigns(
        self,
        account_id: str = None,
        status: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Get Facebook campaigns"""
        sql = """
            SELECT 
                campaign_id,
                account_id,
                name,
                status,
                objective,
                daily_budget,
                lifetime_budget,
                start_time,
                stop_time,
                created_time,
                updated_time,
                created_at,
                updated_at
            FROM facebook_campaigns
            WHERE 1=1
        """
        params = []
        
        if account_id:
            sql += " AND account_id = %s"
            params.append(account_id)
        
        if status:
            sql += " AND status = %s"
            params.append(status)
        
        sql += " ORDER BY created_time DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        return self.db.query(sql, tuple(params))
    
    def get_campaigns_count(self, account_id: str = None) -> int:
        """Get total campaigns count"""
        sql = "SELECT COUNT(*) as count FROM facebook_campaigns"
        params = []
        if account_id:
            sql += " WHERE account_id = %s"
            params.append(account_id)
        result = self.db.query_one(sql, tuple(params) if params else None)
        return result['count'] if result else 0
    
    # ========================================
    # AdSets (-> AdGroup)
    # ========================================
    
    def get_adsets(
        self,
        campaign_id: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Get Facebook adsets"""
        sql = """
            SELECT 
                adset_id,
                campaign_id,
                name,
                status,
                daily_budget,
                lifetime_budget,
                targeting,
                start_time,
                end_time,
                created_time,
                updated_time,
                created_at,
                updated_at
            FROM facebook_adsets
            WHERE 1=1
        """
        params = []
        
        if campaign_id:
            sql += " AND campaign_id = %s"
            params.append(campaign_id)
        
        sql += " ORDER BY created_time DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        return self.db.query(sql, tuple(params))
    
    def get_adsets_count(self, campaign_id: str = None) -> int:
        """Get total adsets count"""
        sql = "SELECT COUNT(*) as count FROM facebook_adsets"
        params = []
        if campaign_id:
            sql += " WHERE campaign_id = %s"
            params.append(campaign_id)
        result = self.db.query_one(sql, tuple(params) if params else None)
        return result['count'] if result else 0
    
    # ========================================
    # Ads (-> Ad)
    # ========================================
    
    def get_ads(
        self,
        adset_id: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """Get Facebook ads"""
        sql = """
            SELECT 
                ad_id,
                adset_id,
                name,
                status,
                creative,
                post_id,
                preview_url,
                created_time,
                updated_time,
                created_at,
                updated_at
            FROM facebook_ads
            WHERE 1=1
        """
        params = []
        
        if adset_id:
            sql += " AND adset_id = %s"
            params.append(adset_id)
        
        sql += " ORDER BY created_time DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        return self.db.query(sql, tuple(params))
    
    def get_ads_count(self, adset_id: str = None) -> int:
        """Get total ads count"""
        sql = "SELECT COUNT(*) as count FROM facebook_ads"
        params = []
        if adset_id:
            sql += " WHERE adset_id = %s"
            params.append(adset_id)
        result = self.db.query_one(sql, tuple(params) if params else None)
        return result['count'] if result else 0
    
    # ========================================
    # Ads Insights (-> Ad Performance)
    # ========================================
    
    def get_ads_insights(
        self,
        ad_id: str = None,
        date_start: str = None,
        date_end: str = None,
        limit: int = 1000,
    ) -> List[Dict]:
        """Get ads insights/performance data"""
        sql = """
            SELECT *
            FROM facebook_ads_insights
            WHERE 1=1
        """
        params = []
        
        if ad_id:
            sql += " AND ad_id = %s"
            params.append(ad_id)
        
        if date_start:
            sql += " AND date_start >= %s"
            params.append(date_start)
        
        if date_end:
            sql += " AND date_stop <= %s"
            params.append(date_end)
        
        sql += " ORDER BY date_start DESC LIMIT %s"
        params.append(limit)
        
        return self.db.query(sql, tuple(params))
    
    # ========================================
    # Ad Accounts
    # ========================================
    
    def get_ad_accounts(self) -> List[Dict]:
        """Get all ad accounts"""
        sql = """
            SELECT 
                id,
                account_id,
                name,
                business_name,
                timezone_name,
                timezone_id,
                owner_id,
                currency,
                account_status,
                business_id,
                created_time,
                updated_time,
                created_at,
                updated_at
            FROM facebook_ad_accounts
            ORDER BY name
        """
        return self.db.query(sql)
    
    # ========================================
    # Dashboard Aggregations
    # ========================================
    
    def get_dashboard_summary(self) -> Dict:
        """Get summary data for dashboard"""
        summary = {}
        
        # Use safe_count for each table
        summary['pages_count'] = self.db.safe_count('facebook_pages')
        summary['posts_count'] = self.db.safe_count('facebook_posts')
        summary['videos_count'] = self.db.safe_count('facebook_video_posts')
        summary['campaigns_count'] = self.db.safe_count('facebook_campaigns')
        summary['adsets_count'] = self.db.safe_count('facebook_adsets')
        summary['ads_count'] = self.db.safe_count('facebook_ads')
        summary['products_count'] = self.db.safe_count('products')
        
        # Total spend from insights
        try:
            spend_result = self.db.query_one("""
                SELECT COALESCE(SUM(spend), 0) as total_spend
                FROM facebook_ads_insights
            """)
            summary['total_spend'] = float(spend_result['total_spend']) if spend_result else 0
        except Exception as e:
            logger.warning(f"Error getting total spend: {e}")
            summary['total_spend'] = 0
        
        return summary
    
    def get_top_posts_by_performance(self, limit: int = 10) -> List[Dict]:
        """Get top performing posts"""
        sql = """
            SELECT 
                p.id,
                p.page_id,
                p.message,
                p.permalink_url,
                p.created_time,
                pp.pfm_score as performance_score,
                pp.ads_total_media_cost as ads_total_cost,
                pp.ads_count,
                pp.likes,
                pp.comments,
                pp.shares,
                pp.video_views
            FROM facebook_posts p
            JOIN facebook_posts_performance pp ON p.id = pp.post_id
            WHERE pp.pfm_score > 0
            ORDER BY pp.pfm_score DESC
            LIMIT %s
        """
        return self.db.query(sql, (limit,))
    
    def get_recent_posts(self, limit: int = 20) -> List[Dict]:
        """Get recent posts"""
        sql = """
            SELECT 
                p.id,
                p.page_id,
                p.message,
                p.type,
                p.permalink_url,
                p.picture_url,
                p.created_time,
                pg.name as page_name
            FROM facebook_posts p
            LEFT JOIN facebook_pages pg ON p.page_id = pg.id
            ORDER BY p.created_time DESC
            LIMIT %s
        """
        return self.db.query(sql, (limit,))
    
    def get_campaigns_performance(self) -> List[Dict]:
        """Get campaigns with aggregated performance"""
        sql = """
            SELECT 
                c.campaign_id,
                c.name,
                c.status,
                c.objective,
                c.daily_budget,
                COUNT(DISTINCT a.adset_id) as adsets_count,
                COUNT(DISTINCT ad.ad_id) as ads_count,
                COALESCE(SUM(i.spend), 0) as total_spend,
                COALESCE(SUM(i.impressions), 0) as total_impressions,
                COALESCE(SUM(i.clicks), 0) as total_clicks
            FROM facebook_campaigns c
            LEFT JOIN facebook_adsets a ON c.campaign_id = a.campaign_id
            LEFT JOIN facebook_ads ad ON a.adset_id = ad.adset_id
            LEFT JOIN facebook_ads_insights i ON ad.ad_id = i.ad_id
            GROUP BY c.campaign_id, c.name, c.status, c.objective, c.daily_budget
            ORDER BY total_spend DESC
            LIMIT 50
        """
        return self.db.query(sql)


# Singleton instance
_legacy_db = None

def get_legacy_db() -> FacebookLegacyDB:
    """Get singleton legacy DB connection"""
    global _legacy_db
    if _legacy_db is None:
        _legacy_db = FacebookLegacyDB()
    return _legacy_db

def get_legacy_mapper() -> FacebookLegacyMapper:
    """Get legacy mapper with singleton DB"""
    return FacebookLegacyMapper(get_legacy_db())
