"""
Settings-related schemas
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel

from app.models.enums import Platform, AdAccountStatus


class AdAccountBase(BaseModel):
    """Base fields for ad account"""

    name: str
    platform: Platform
    external_account_id: str
    status: AdAccountStatus = AdAccountStatus.ACTIVE
    timezone: Optional[str] = None
    currency: Optional[str] = "THB"
    config: Optional[Dict[str, Any]] = None


class AdAccountCreate(AdAccountBase):
    """Create ad account payload"""

    pass


class AdAccountUpdate(BaseModel):
    """Update ad account payload"""

    name: Optional[str] = None
    status: Optional[AdAccountStatus] = None
    timezone: Optional[str] = None
    currency: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class AdAccountResponse(AdAccountBase):
    """Ad account response"""

    id: int

    class Config:
        from_attributes = True


class TikTokConfig(BaseModel):
    """TikTok API configuration stored in DB"""

    business_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    refresh_token: Optional[str] = None
    direct_access_token: Optional[str] = None  # override token if needed


class TikTokChannelsConfig(BaseModel):
    """Official TikTok channels (company accounts) stored in DB"""

    channels: List[str] = []

