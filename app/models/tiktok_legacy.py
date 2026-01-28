"""
TikTok Legacy models - สำหรับเชื่อมต่อกับตาราง tiktok_posts เดิม
ใช้สำหรับ backward compatibility กับ database schema เก่า
"""
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, Text, Numeric
from sqlalchemy.dialects.postgresql import JSONB, JSON
from sqlalchemy.ext.declarative import declarative_base

from app.models.base import Base


class TiktokPost(Base):
    """
    Legacy TikTok Post model - maps to existing tiktok_posts table
    """
    
    __tablename__ = "tiktok_posts"
    
    # Primary Key
    item_id = Column(String, primary_key=True, index=True)
    
    # Timestamps
    create_time = Column(DateTime, nullable=True)
    update_time = Column(DateTime, nullable=True)
    
    # Channel Info
    channel_acc_id = Column(String, nullable=True)
    channel_type = Column(Integer, nullable=True)
    
    # Content Info
    url = Column(String, nullable=True)
    caption = Column(String, nullable=True)
    thumbnail_url = Column(String, nullable=True)
    video_duration = Column(Float, nullable=True)
    
    # Watch Metrics
    total_time_watched = Column(Float, nullable=True)
    average_time_watched = Column(Float, nullable=True)
    full_video_watched_rate = Column(Float, nullable=True)
    
    # Engagement Metrics
    impression_sources = Column(JSONB, nullable=True)
    reach = Column(Integer, default=0)
    video_views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    bookmarks = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    
    # Performance Score
    pfm_score = Column(Float, default=0)
    
    # Product & Classification
    products = Column(String, nullable=True)
    products_json = Column(JSONB, nullable=True)
    content_type = Column(String, nullable=True)
    content_status = Column(String, nullable=True)
    
    # Creator Info
    creator_details = Column(JSONB, nullable=True)
    
    # Cost & Budget
    created_cost_content = Column(Float, default=0)
    created_budget_date = Column(Date, nullable=True)
    
    # Ads Info
    ads_details = Column(JSONB, nullable=True)
    ads_total_media_cost = Column(Float, nullable=True)
    
    # ACE/ABX Ads
    ace_ad_count = Column(Integer, default=0)
    ace_details = Column(JSON, nullable=True)
    abx_ad_count = Column(Integer, default=0)
    abx_details = Column(JSON, nullable=True)
    
    # Targeting
    targeting_details = Column(JSON, nullable=True)
    targeting2_details = Column(JSON, nullable=True)
    
    # Expiration
    content_expire_date = Column(DateTime, nullable=True)
    
    # OFPM
    ofpm_details = Column(JSONB, nullable=True)
    
    # Boost
    boost_created_by = Column(String, nullable=True)
    boost_factor = Column(Numeric, default=1.0)
    boost_start_date = Column(Date, nullable=True)
    boost_expire_date = Column(Date, nullable=True)
    boost_reason = Column(Text, nullable=True)


class ABXAdgroupLegacy(Base):
    """
    Legacy ABX Adgroup model - maps to existing abx_adgroup table
    """
    
    __tablename__ = "abx_adgroup"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    adgroup_id = Column(String, nullable=False, unique=True, index=True)
    adgroup_name = Column(String, nullable=False)
    targeting_id = Column(String, nullable=False)
    group_style = Column(String, nullable=False)  # SALE, REVIEW, BRANDING
    product_group = Column(String, nullable=False)
    pfm_score = Column(Numeric, nullable=True)
    
    create_time = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    
    campaign_id = Column(String, nullable=True)
    advertiser_id = Column(String, nullable=True)
    
    plan_adgroup_budget = Column(Numeric, nullable=True)
    plan_adgroup_status = Column(String, nullable=True)
    
    update_by = Column(String, nullable=True)
    update_time = Column(DateTime, nullable=True)
    
    product_group_json = Column(JSONB, nullable=True)
    ad_count = Column(Integer, nullable=True)
    budget_update_time = Column(DateTime, nullable=True)
    
    is_active = Column(Boolean, nullable=True)
    is_currentplan = Column(Boolean, nullable=True)


class TiktokTargeting(Base):
    """
    Legacy TikTok Targeting model - maps to existing tiktok_targeting table
    """
    
    __tablename__ = "tiktok_targeting"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=True)
    
    age = Column(JSONB, nullable=True)
    gender = Column(String, nullable=True)
    location = Column(JSONB, nullable=True)
    language = Column(JSONB, nullable=True)
    
    interest_categories = Column(JSONB, nullable=True)
    action_categories = Column(JSONB, nullable=True)
    hashtags = Column(JSONB, nullable=True)
    
    create_user = Column(String, nullable=True)
    create_time = Column(DateTime, nullable=True)
    is_approve = Column(Boolean, nullable=True)
    
    device_types = Column(JSONB, nullable=True)
    network_types = Column(JSONB, nullable=True)
    
    audience_lower = Column(Integer, nullable=True)
    audience_upper = Column(Integer, nullable=True)
    status = Column(Boolean, nullable=True)


class ProductGroupLegacy(Base):
    """
    Legacy Product Group model - maps to existing product_groups table
    """
    
    __tablename__ = "product_groups"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=True)
    products = Column(JSONB, nullable=True)
    is_active = Column(Boolean, nullable=True)
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)


class ProductLegacy(Base):
    """
    Legacy Product model - maps to existing products table
    """
    
    __tablename__ = "products"
    __table_args__ = {'extend_existing': True}
    
    code = Column(String, primary_key=True)
    productname = Column(String, nullable=True)
    status = Column(String, nullable=True)
    allocate_status = Column(Boolean, nullable=True)


class DailyAdSpend(Base):
    """
    Daily Ad Spend model - maps to existing daily_ad_spend table
    Stores daily advertising spend by product, platform, and ad type
    """
    
    __tablename__ = "daily_ad_spend"
    __table_args__ = {'extend_existing': True}
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=True, index=True)
    product_code = Column(String, nullable=True)
    platform = Column(String, nullable=True)  # TikTok, Facebook, etc.
    ad_type = Column(String, nullable=True)  # ABX, ACE, etc.
    actual_spend = Column(Numeric, nullable=True)
    currency = Column(String, nullable=True, default='THB')
    metrics = Column(JSONB, nullable=True)  # cpm, ctr, impressions, etc.
    created_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    created_by = Column(String, nullable=True)
