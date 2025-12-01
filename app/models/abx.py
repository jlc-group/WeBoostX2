"""
ABX (Adgroup-Based) models - TikTok specific automation
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, Text, DateTime, JSON, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.models.enums import Platform, ContentType, AdStatus


class ABXAdgroup(BaseModel):
    """
    ABX Adgroup - managed adgroups for budget optimization
    This is the core of ABX automation system
    """
    
    __tablename__ = "abx_adgroups"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Platform & External Reference
    # ============================================
    platform = Column(Enum(Platform), default=Platform.TIKTOK, nullable=False, index=True)
    external_adgroup_id = Column(String(100), unique=True, nullable=False, index=True)
    external_campaign_id = Column(String(100), nullable=True)
    external_advertiser_id = Column(String(100), nullable=True)
    
    # Link to internal adgroup
    ad_group_id = Column(Integer, ForeignKey("ad_groups.id"), nullable=True, index=True)
    
    # ============================================
    # ABX Configuration
    # ============================================
    name = Column(String(255), nullable=False)
    
    # Classification
    group_style = Column(Enum(ContentType), nullable=True)  # SALE, REVIEW, BRANDING, ECOM
    product_group_id = Column(Integer, ForeignKey("product_groups.id"), nullable=True, index=True)
    
    # Targeting
    targeting_template_id = Column(Integer, ForeignKey("targeting_templates.id"), nullable=True)
    
    # ============================================
    # Status & Control
    # ============================================
    status = Column(Enum(AdStatus), default=AdStatus.ACTIVE, index=True)
    is_active = Column(Boolean, default=True)
    is_current_plan = Column(Boolean, default=False)  # Part of current budget plan
    
    # ============================================
    # Budget Planning
    # ============================================
    plan_budget = Column(Numeric(12, 2), nullable=True)  # Planned budget
    plan_status = Column(String(50), nullable=True)  # Plan status
    
    # ============================================
    # Performance
    # ============================================
    pfm_score = Column(Numeric(5, 2), nullable=True)  # Aggregated PFM of ads in group
    ad_count = Column(Integer, default=0)
    good_pfm_ad_count = Column(Integer, default=0)
    
    # Spend tracking
    total_spend = Column(Numeric(15, 2), default=0)
    today_spend = Column(Numeric(12, 2), default=0)
    
    # ============================================
    # Tracking
    # ============================================
    budget_updated_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # ============================================
    # Relationships
    # ============================================
    product_group = relationship("ProductGroup", back_populates="abx_adgroups")


class ABXBudgetLog(BaseModel):
    """Log of ABX budget changes"""
    
    __tablename__ = "abx_budget_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    abx_adgroup_id = Column(Integer, ForeignKey("abx_adgroups.id"), nullable=False, index=True)
    
    # Change details
    previous_budget = Column(Numeric(12, 2), nullable=True)
    new_budget = Column(Numeric(12, 2), nullable=True)
    change_reason = Column(Text, nullable=True)
    change_type = Column(String(50), nullable=True)  # auto, manual, rule
    
    # Context
    pfm_score_at_change = Column(Numeric(5, 2), nullable=True)
    metrics_snapshot = Column(JSON, nullable=True)
    
    # Who/what made the change
    triggered_by = Column(String(100), nullable=True)  # user_id or "system"

