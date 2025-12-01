"""
Platform and Ad Account models
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, Text, Date, JSON, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.models.enums import Platform, AdAccountStatus


class AdAccount(BaseModel):
    """Ad account for each platform (TikTok Advertiser / Facebook Ad Account)"""
    
    __tablename__ = "ad_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Platform info
    platform = Column(Enum(Platform), nullable=False, index=True)
    external_account_id = Column(String(100), nullable=False, index=True)  # TikTok advertiser_id / FB act_xxx
    
    # Account details
    name = Column(String(255), nullable=False)
    status = Column(Enum(AdAccountStatus), default=AdAccountStatus.ACTIVE)
    timezone = Column(String(50), nullable=True)
    currency = Column(String(10), default="THB")
    
    # Tracking
    start_date = Column(Date, nullable=True)  # When started using this account
    
    # Platform-specific config (JSON)
    config = Column(JSON, nullable=True)
    
    # Credentials (encrypted or reference)
    access_token_ref = Column(String(255), nullable=True)  # Reference to secure storage
    
    # Relationships
    campaigns = relationship("Campaign", back_populates="ad_account")
    contents = relationship("Content", back_populates="ad_account")
    
    class Config:
        # Unique constraint: one external account per platform
        __table_args__ = (
            {"extend_existing": True}
        )


class TargetingTemplate(BaseModel):
    """Reusable targeting templates"""
    
    __tablename__ = "targeting_templates"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Basic info
    name = Column(String(255), nullable=False)
    platform = Column(Enum(Platform), nullable=False, index=True)
    
    # Targeting options (JSON for flexibility across platforms)
    age_range = Column(JSON, nullable=True)  # {"min": 18, "max": 44} or ["AGE_18_24", "AGE_25_34"]
    gender = Column(String(20), nullable=True)  # MALE, FEMALE, ALL
    locations = Column(JSON, nullable=True)  # List of location IDs
    languages = Column(JSON, nullable=True)
    interests = Column(JSON, nullable=True)  # Interest category IDs
    behaviors = Column(JSON, nullable=True)  # Action/behavior categories
    custom_audiences = Column(JSON, nullable=True)
    excluded_audiences = Column(JSON, nullable=True)
    
    # Device targeting
    device_types = Column(JSON, nullable=True)
    os_versions = Column(JSON, nullable=True)
    network_types = Column(JSON, nullable=True)
    
    # Audience estimation
    audience_size_lower = Column(Integer, nullable=True)
    audience_size_upper = Column(Integer, nullable=True)
    
    # Management
    is_approved = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Raw platform-specific targeting (for advanced cases)
    raw_targeting = Column(JSON, nullable=True)

