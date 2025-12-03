"""
TikTok Targeting Cache Models

Cached TikTok targeting options to avoid API calls for every page load.
Sync daily via cronjob.
"""
from sqlalchemy import Column, Integer, String, JSON, DateTime, Enum, Text
from sqlalchemy.sql import func

from app.models.base import BaseModel
from app.models.enums import Platform


class TikTokInterestCategory(BaseModel):
    """
    Cached TikTok Interest Categories
    
    API: GET /open_api/v1.3/tool/interest_category/
    Sync: Daily cronjob
    """
    
    __tablename__ = "tiktok_interest_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # TikTok Interest ID
    interest_category_id = Column(String(50), unique=True, nullable=False, index=True)
    interest_category_name = Column(String(255), nullable=False)
    
    # Hierarchy
    level = Column(Integer, nullable=False, index=True)  # 1, 2, 3, 4
    parent_id = Column(String(50), nullable=True, index=True)  # Parent category ID
    sub_category_ids = Column(JSON, nullable=True)  # List of child IDs
    
    # Language
    language = Column(String(10), default="th")
    
    # Timestamps
    synced_at = Column(DateTime, server_default=func.now())


class TikTokActionCategory(BaseModel):
    """
    Cached TikTok Action/Behavior Categories
    
    API: GET /open_api/v1.3/tool/action_category/
    Sync: Daily cronjob
    """
    
    __tablename__ = "tiktok_action_categories"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # TikTok Action ID (NOT unique alone - same ID exists in VIDEO_RELATED and CREATOR_RELATED)
    action_category_id = Column(String(50), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Category type
    action_scene = Column(String(50), nullable=False, index=True)  # VIDEO_RELATED, CREATOR_RELATED, HASHTAG_RELATED
    
    # Hierarchy
    level = Column(Integer, nullable=False, index=True)
    parent_id = Column(String(50), nullable=True, index=True)
    sub_category_ids = Column(JSON, nullable=True)
    
    # Language
    language = Column(String(10), default="th")
    
    # Timestamps
    synced_at = Column(DateTime, server_default=func.now())


class TikTokRegion(BaseModel):
    """
    Cached TikTok Regions/Locations
    
    API: GET /open_api/v1.3/tool/region/
    Sync: Daily cronjob
    """
    
    __tablename__ = "tiktok_regions"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # TikTok Location ID
    location_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    
    # Region info
    region_code = Column(String(10), nullable=True, index=True)  # TH, US, etc.
    level = Column(String(50), nullable=True)  # COUNTRY, PROVINCE, etc. (TikTok returns string)
    parent_id = Column(String(50), nullable=True, index=True)
    
    # Language
    language = Column(String(10), default="th")
    
    # Timestamps
    synced_at = Column(DateTime, server_default=func.now())

