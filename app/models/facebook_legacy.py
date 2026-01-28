"""
Facebook Legacy models - สำหรับเชื่อมต่อกับ Local PostgreSQL database
ใช้สำหรับ backward compatibility กับ Facebook data
"""
from sqlalchemy import Column, Integer, BigInteger, String, Float, Boolean, Date, DateTime, Text, Numeric
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from sqlalchemy.ext.declarative import declarative_base

from app.models.base import Base


class FacebookPostPerformance(Base):
    """
    Facebook Post Performance model - consolidated post data with performance metrics
    Contains: posts, reels, performance data, ads details, PFM score
    """
    
    __tablename__ = "facebook_posts_performance"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(String, nullable=True, index=True)
    channel_acc_id = Column(String, nullable=True)
    post_type = Column(String, nullable=True)  # photo, status, reel, link, video
    
    # Content Info
    url = Column(Text, nullable=True)
    caption = Column(Text, nullable=True)
    thumbnail_url = Column(Text, nullable=True)
    local_thumbnail_id = Column(String, nullable=True)  # UUID
    
    # Video Metrics
    video_duration = Column(Integer, nullable=True)
    video_views = Column(BigInteger, default=0)
    total_time_watched = Column(BigInteger, default=0)
    average_time_watched = Column(Integer, default=0)
    
    # Engagement Metrics
    impressions = Column(BigInteger, default=0)
    impressions_unique = Column(BigInteger, default=0)
    reach = Column(BigInteger, default=0)
    clicks = Column(BigInteger, default=0)
    likes = Column(BigInteger, default=0)
    comments = Column(BigInteger, default=0)
    shares = Column(BigInteger, default=0)
    reactions = Column(JSONB, nullable=True)
    total_post_saves = Column(BigInteger, default=0)
    
    # Performance Scores
    pfm_score = Column(Numeric, nullable=True)
    performance_score = Column(Numeric, nullable=True)
    engagement_rate = Column(Numeric, nullable=True)
    ctr = Column(Numeric, nullable=True)
    
    # Product Info
    products = Column(ARRAY(String), nullable=True)
    primary_product_sku = Column(String, nullable=True)
    
    # Ads Info
    ads_details = Column(JSONB, nullable=True)
    ads_total_media_cost = Column(Numeric, nullable=True)
    ads_count = Column(Integer, default=0)
    ads_avg_cost_per_result = Column(Numeric, nullable=True)
    ads_cost_per_result_breakdown = Column(JSONB, nullable=True)
    campaign_details = Column(JSONB, nullable=True)
    targeting_details = Column(JSONB, nullable=True)
    
    # Classification
    content_type = Column(String, nullable=True)
    content_status = Column(String, nullable=True)
    
    # Boost
    boost_created_by = Column(String, nullable=True)
    boost_factor = Column(Numeric, default=1.0)
    boost_start_date = Column(Date, nullable=True)
    boost_expire_date = Column(Date, nullable=True)
    boost_reason = Column(Text, nullable=True)
    
    # Timestamps
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
    last_sync_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class FacebookCampaign(Base):
    """
    Facebook Campaign model
    """
    
    __tablename__ = "facebook_campaigns"
    __table_args__ = {'extend_existing': True}
    
    campaign_id = Column(String, primary_key=True)
    account_id = Column(String, nullable=True)
    name = Column(String, nullable=True)
    objective = Column(String, nullable=True)
    status = Column(String, nullable=True)  # ACTIVE, PAUSED, etc.
    daily_budget = Column(BigInteger, nullable=True)
    lifetime_budget = Column(BigInteger, nullable=True)
    start_time = Column(DateTime, nullable=True)
    stop_time = Column(DateTime, nullable=True)
    created_time = Column(DateTime, nullable=True)
    updated_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class FacebookAdset(Base):
    """
    Facebook Adset model
    """
    
    __tablename__ = "facebook_adsets"
    __table_args__ = {'extend_existing': True}
    
    adset_id = Column(String, primary_key=True)
    campaign_id = Column(String, nullable=True, index=True)
    account_id = Column(String, nullable=True)
    name = Column(String, nullable=True)
    status = Column(String, nullable=True)
    daily_budget = Column(BigInteger, nullable=True)
    lifetime_budget = Column(BigInteger, nullable=True)
    optimization_goal = Column(String, nullable=True)
    billing_event = Column(String, nullable=True)
    bid_amount = Column(BigInteger, nullable=True)
    targeting = Column(JSONB, nullable=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    created_time = Column(DateTime, nullable=True)
    updated_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class FacebookAd(Base):
    """
    Facebook Ad model
    """
    
    __tablename__ = "facebook_ads"
    __table_args__ = {'extend_existing': True}
    
    ad_id = Column(String, primary_key=True)
    adset_id = Column(String, nullable=True, index=True)
    name = Column(String, nullable=True)
    status = Column(String, nullable=True)
    creative = Column(JSONB, nullable=True)
    preview_url = Column(Text, nullable=True)
    post_id = Column(String, nullable=True)
    created_time = Column(DateTime, nullable=True)
    updated_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class FacebookAdsInsights(Base):
    """
    Facebook Ads Insights model - daily ad performance data
    """
    
    __tablename__ = "facebook_ads_insights"
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)  # UUID
    ad_id = Column(String, nullable=True, index=True)
    adset_id = Column(String, nullable=True)
    campaign_id = Column(String, nullable=True)
    account_id = Column(String, nullable=True)
    
    # Metrics
    impressions = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    spend = Column(Numeric, default=0)
    cpm = Column(Numeric, nullable=True)
    cpp = Column(Numeric, nullable=True)
    ctr = Column(Numeric, nullable=True)
    frequency = Column(Numeric, nullable=True)
    cost_per_result = Column(Numeric, nullable=True)
    
    # Actions data
    actions = Column(JSONB, nullable=True)
    action_values = Column(JSONB, nullable=True)
    video_actions = Column(JSONB, nullable=True)
    
    # Date range
    date_start = Column(Date, nullable=True, index=True)
    date_stop = Column(Date, nullable=True)
    
    created_at = Column(DateTime, nullable=True)


class FacebookPage(Base):
    """
    Facebook Page model
    """
    
    __tablename__ = "facebook_pages"
    __table_args__ = {'extend_existing': True}
    
    page_id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    category = Column(String, nullable=True)
    access_token = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class FacebookPost(Base):
    """
    Facebook Post model - raw posts from FB API
    """
    
    __tablename__ = "facebook_posts"
    __table_args__ = {'extend_existing': True}
    
    id = Column(String, primary_key=True)  # post_id
    page_id = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    story = Column(Text, nullable=True)
    type = Column(String, nullable=True)
    permalink_url = Column(Text, nullable=True)
    picture_url = Column(Text, nullable=True)
    full_picture_url = Column(Text, nullable=True)
    video_url = Column(Text, nullable=True)
    source = Column(Text, nullable=True)
    status_type = Column(String, nullable=True)
    created_time = Column(DateTime, nullable=True)
    updated_time = Column(DateTime, nullable=True)
    is_published = Column(Boolean, default=True)
    is_hidden = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
