"""
Content model - unified content across all platforms
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, Text, Date, DateTime, JSON, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, SoftDeleteMixin
from app.models.enums import Platform, ContentType, ContentSource, ContentStatus


class Content(BaseModel, SoftDeleteMixin):
    """
    Unified content model for all platforms (TikTok, Facebook, Instagram)
    Replaces the old TiktokPost model
    """
    
    __tablename__ = "contents"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Platform & Identity
    # ============================================
    platform = Column(Enum(Platform), nullable=False, index=True)
    platform_post_id = Column(String(100), nullable=False, index=True)  # TikTok item_id / FB post_id
    ad_account_id = Column(Integer, ForeignKey("ad_accounts.id"), nullable=True, index=True)
    
    # ============================================
    # Content Info
    # ============================================
    url = Column(String(500), nullable=True)
    caption = Column(Text, nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    
    # Timestamps from platform
    platform_created_at = Column(DateTime(timezone=True), nullable=True)
    platform_updated_at = Column(DateTime(timezone=True), nullable=True)
    
    # ============================================
    # Classification
    # ============================================
    content_type = Column(Enum(ContentType), default=ContentType.OTHER, index=True)
    content_source = Column(Enum(ContentSource), nullable=True)
    status = Column(Enum(ContentStatus), default=ContentStatus.READY, index=True)
    
    # ============================================
    # Product Association
    # ============================================
    product_codes = Column(JSON, nullable=True)  # ["S1", "S2"]
    product_group_id = Column(Integer, ForeignKey("product_groups.id"), nullable=True, index=True)
    
    # ============================================
    # Creator/Owner Info
    # ============================================
    creator_id = Column(String(100), nullable=True)  # Platform user ID
    creator_name = Column(String(255), nullable=True)  # Platform username
    creator_details = Column(JSON, nullable=True)  # Additional creator info
    
    # Employee/Influencer relationship
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True, index=True)
    influencer_id = Column(Integer, ForeignKey("influencers.id"), nullable=True, index=True)
    influencer_cost = Column(Numeric(12, 2), nullable=True)  # Cost paid to influencer
    
    # ============================================
    # Organic Metrics (from platform)
    # ============================================
    # Video metrics
    video_duration = Column(Numeric(10, 2), nullable=True)  # seconds
    
    # Engagement metrics (unified naming)
    views = Column(Integer, default=0)
    impressions = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    saves = Column(Integer, default=0)  # bookmarks
    
    # Watch time metrics
    total_watch_time = Column(Numeric(15, 2), nullable=True)  # seconds
    avg_watch_time = Column(Numeric(10, 2), nullable=True)  # seconds
    completion_rate = Column(Numeric(5, 2), nullable=True)  # percentage
    
    # Platform-specific metrics (JSON for flexibility)
    platform_metrics = Column(JSON, nullable=True)
    # TikTok: {"full_video_watched_rate": 0.15, ...}
    # Facebook: {"thruplay": 1000, "3s_views": 5000, ...}
    
    # ============================================
    # Ad Performance (aggregated from ads)
    # ============================================
    ads_total_cost = Column(Numeric(15, 2), default=0)  # Total spent across all platforms
    ads_count = Column(Integer, default=0)  # Number of ads using this content
    
    # ACE/ABX specific (TikTok only)
    # ACE = 1 adgroup per 1 content (standard)
    # ABX = 1 adgroup per N contents (testing multiple contents)
    ace_ad_count = Column(Integer, default=0)
    ace_details = Column(JSON, nullable=True)  # List of ACE ads info
    abx_ad_count = Column(Integer, default=0)
    abx_details = Column(JSON, nullable=True)  # List of ABX ads info
    
    # Detailed ads info (JSON) - all platforms
    ads_details = Column(JSON, nullable=True)
    # {"tiktok": [...], "facebook": [...]}
    
    # ============================================
    # Performance Scores
    # ============================================
    pfm_score = Column(Numeric(5, 2), nullable=True)  # TikTok PFM score
    fb_score = Column(Numeric(5, 2), nullable=True)   # Facebook performance score
    unified_score = Column(Numeric(5, 2), nullable=True)  # Unified Content Impact Score
    score_details = Column(JSON, nullable=True)  # Score breakdown
    
    # ============================================
    # Boost Feature
    # ============================================
    boost_factor = Column(Numeric(3, 2), default=1.0)  # Multiplier for priority
    boost_start_date = Column(Date, nullable=True)
    boost_end_date = Column(Date, nullable=True)
    boost_reason = Column(Text, nullable=True)
    boost_created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # ============================================
    # Expiration
    # ============================================
    expire_date = Column(Date, nullable=True)
    
    # ============================================
    # Targeting (for ad creation)
    # ============================================
    targeting_template_id = Column(Integer, ForeignKey("targeting_templates.id"), nullable=True)
    targeting_override = Column(JSON, nullable=True)  # Override targeting settings
    
    # ============================================
    # Relationships
    # ============================================
    ad_account = relationship("AdAccount", back_populates="contents")
    ads = relationship("Ad", back_populates="content")
    employee = relationship("Employee", backref="contents", foreign_keys=[employee_id])
    influencer = relationship("Influencer", backref="contents", foreign_keys=[influencer_id])


class ContentScoreHistory(BaseModel):
    """Track content score changes over time"""
    
    __tablename__ = "content_score_history"
    
    id = Column(Integer, primary_key=True, index=True)
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=False, index=True)
    
    # Scores at this point
    pfm_score = Column(Numeric(5, 2), nullable=True)
    fb_score = Column(Numeric(5, 2), nullable=True)
    unified_score = Column(Numeric(5, 2), nullable=True)
    
    # Score components (JSON)
    score_breakdown = Column(JSON, nullable=True)
    
    # Snapshot of key metrics
    metrics_snapshot = Column(JSON, nullable=True)

