"""
Campaign, AdGroup, Ad models - unified across platforms
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, Text, Date, DateTime, JSON, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, SoftDeleteMixin
from app.models.enums import (
    Platform,
    AdStatus,
    CampaignObjective,
    OptimizationGoal,
    BudgetType,
    ContentType,
    AdGroupStructure,
)


class Campaign(BaseModel, SoftDeleteMixin):
    """Campaign model - unified for TikTok and Facebook"""
    
    __tablename__ = "campaigns"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Platform & Account
    # ============================================
    platform = Column(Enum(Platform), nullable=False, index=True)
    ad_account_id = Column(Integer, ForeignKey("ad_accounts.id"), nullable=False, index=True)
    external_campaign_id = Column(String(100), nullable=False, index=True)
    
    # ============================================
    # Campaign Info
    # ============================================
    name = Column(String(255), nullable=False)
    status = Column(Enum(AdStatus), default=AdStatus.ACTIVE, index=True)
    
    # Objective & Goal
    objective = Column(Enum(CampaignObjective), nullable=True)
    objective_raw = Column(String(100), nullable=True)  # Original platform value
    
    # ============================================
    # Budget
    # ============================================
    budget_type = Column(Enum(BudgetType), nullable=True)
    daily_budget = Column(Numeric(15, 2), nullable=True)
    lifetime_budget = Column(Numeric(15, 2), nullable=True)
    
    # ============================================
    # Schedule
    # ============================================
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    
    # ============================================
    # Platform-specific data
    # ============================================
    platform_data = Column(JSON, nullable=True)
    
    # ============================================
    # Sync tracking
    # ============================================
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    
    # ============================================
    # Relationships
    # ============================================
    ad_account = relationship("AdAccount", back_populates="campaigns")
    ad_groups = relationship("AdGroup", back_populates="campaign")


class AdGroup(BaseModel, SoftDeleteMixin):
    """
    AdGroup model - TikTok AdGroup / Facebook AdSet
    """
    
    __tablename__ = "ad_groups"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Platform & Account & Campaign
    # ============================================
    platform = Column(Enum(Platform), nullable=False, index=True)
    ad_account_id = Column(Integer, ForeignKey("ad_accounts.id"), nullable=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    external_adgroup_id = Column(String(100), nullable=False, index=True)
    
    # ============================================
    # AdGroup Info
    # ============================================
    name = Column(String(255), nullable=False)
    status = Column(Enum(AdStatus), default=AdStatus.ACTIVE, index=True)

    # ============================================
    # Structure & Strategy (WeBoostX 2.0)
    # ============================================
    # NOTE: These columns are not yet in the database - uncomment when migration is run
    # โครงสร้างความสัมพันธ์ระหว่าง adgroup กับ content:
    # - SINGLE_CONTENT: 1 adgroup / 1 content (ACE-style หรือคลิปเดี่ยว)
    # - MULTI_CONTENT: 1 adgroup / หลาย content (ABX-style, multi creative)
    # - UNKNOWN: ยังไม่จัดประเภท / สร้างเองนอกระบบ
    # structure = Column(Enum(AdGroupStructure), default=AdGroupStructure.UNKNOWN, index=True)

    # แท็กชื่อกลยุทธ์ที่ระบบใช้จัดการ adgroup นี้ เช่น "ACE", "ABX", "BRANDING_MULTI"
    # ไม่บังคับ schema ให้ตายตัว เพื่อให้เพิ่ม strategy ใหม่ได้ง่าย
    # strategy_tag = Column(String(100), nullable=True, index=True)

    # content_style หลักของ adgroup นี้ (ใช้ ContentType เดียวกับตาราง contents)
    # เช่น SALE / REVIEW / BRANDING / ECOM – ช่วยให้ optimizer เลือก/กรองง่ายขึ้น
    # content_style = Column(Enum(ContentType), nullable=True, index=True)
    
    # ============================================
    # Optimization
    # ============================================
    optimization_goal = Column(Enum(OptimizationGoal), nullable=True)
    optimization_goal_raw = Column(String(100), nullable=True)
    billing_event = Column(String(50), nullable=True)
    bid_strategy = Column(String(50), nullable=True)
    bid_amount = Column(Numeric(12, 2), nullable=True)
    
    # ============================================
    # Budget
    # ============================================
    budget_type = Column(Enum(BudgetType), nullable=True)
    daily_budget = Column(Numeric(15, 2), nullable=True)
    lifetime_budget = Column(Numeric(15, 2), nullable=True)
    
    # ============================================
    # Schedule
    # ============================================
    start_time = Column(DateTime(timezone=True), nullable=True)
    end_time = Column(DateTime(timezone=True), nullable=True)
    schedule = Column(JSON, nullable=True)  # Day-parting schedule
    
    # ============================================
    # Targeting
    # ============================================
    targeting_template_id = Column(Integer, ForeignKey("targeting_templates.id"), nullable=True)
    targeting = Column(JSON, nullable=True)  # Actual targeting used
    
    # ============================================
    # Performance Metrics (aggregated)
    # ============================================
    total_spend = Column(Numeric(15, 2), default=0)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    
    # Calculated metrics
    ctr = Column(Numeric(8, 4), nullable=True)
    cpc = Column(Numeric(10, 2), nullable=True)
    cpm = Column(Numeric(10, 2), nullable=True)
    roas = Column(Numeric(10, 2), nullable=True)
    
    # ============================================
    # Platform-specific data
    # ============================================
    platform_data = Column(JSON, nullable=True)
    
    # ============================================
    # Sync tracking
    # ============================================
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    
    # ============================================
    # Relationships
    # ============================================
    ad_account = relationship("AdAccount", back_populates="ad_groups")
    campaign = relationship("Campaign", back_populates="ad_groups")
    ads = relationship("Ad", back_populates="ad_group")


class Ad(BaseModel, SoftDeleteMixin):
    """Individual Ad"""
    
    __tablename__ = "ads"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Platform & Account & AdGroup
    # ============================================
    platform = Column(Enum(Platform), nullable=False, index=True)
    ad_account_id = Column(Integer, ForeignKey("ad_accounts.id"), nullable=True, index=True)
    ad_group_id = Column(Integer, ForeignKey("ad_groups.id"), nullable=False, index=True)
    external_ad_id = Column(String(100), nullable=False, index=True)
    
    # ============================================
    # Content Link
    # ============================================
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=True, index=True)
    
    # For Facebook: object_story_id to link to content
    creative_id = Column(String(100), nullable=True)
    object_story_id = Column(String(100), nullable=True)
    
    # ============================================
    # Ad Info
    # ============================================
    name = Column(String(255), nullable=False)
    status = Column(Enum(AdStatus), default=AdStatus.ACTIVE, index=True)
    
    # ============================================
    # Performance Metrics
    # ============================================
    total_spend = Column(Numeric(15, 2), default=0)
    impressions = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    video_views = Column(Integer, default=0)
    thruplay = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    purchases = Column(Integer, default=0)
    purchase_value = Column(Numeric(15, 2), default=0)
    
    # Calculated metrics
    ctr = Column(Numeric(8, 4), nullable=True)
    cpc = Column(Numeric(10, 2), nullable=True)
    cpm = Column(Numeric(10, 2), nullable=True)
    cvr = Column(Numeric(8, 4), nullable=True)
    roas = Column(Numeric(10, 2), nullable=True)
    frequency = Column(Numeric(6, 2), nullable=True)
    
    # ============================================
    # Platform-specific metrics
    # ============================================
    platform_metrics = Column(JSON, nullable=True)
    
    # ============================================
    # Sync tracking
    # ============================================
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    
    # ============================================
    # Relationships
    # ============================================
    ad_account = relationship("AdAccount", back_populates="ads")
    ad_group = relationship("AdGroup", back_populates="ads")
    content = relationship("Content", back_populates="ads")


class AdPerformanceHistory(BaseModel):
    """Daily performance snapshots for ads"""
    
    __tablename__ = "ad_performance_history"
    
    id = Column(Integer, primary_key=True, index=True)
    ad_account_id = Column(Integer, ForeignKey("ad_accounts.id"), nullable=True, index=True)
    ad_id = Column(Integer, ForeignKey("ads.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    
    # Metrics for this day
    spend = Column(Numeric(15, 2), default=0)
    impressions = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    video_views = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    purchases = Column(Integer, default=0)
    purchase_value = Column(Numeric(15, 2), default=0)
    
    # All metrics (JSON)
    metrics = Column(JSON, nullable=True)

