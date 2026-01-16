"""
TikTok Ads Creation API endpoints
- Create ACE Ad (1 adgroup = 1 content)
- Create ABX Ad (add content to existing adgroup)
"""
from typing import Optional, List, Dict
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.deps import get_db, get_current_user
from app.models import AdAccount, Campaign, AdGroup, Ad, Content
from app.models.platform import TargetingTemplate
from app.models.enums import Platform, AdAccountStatus, AdStatus
from app.models.user import User
from app.services.tiktok_ads_service import TikTokAdsService
from app.services.naming_service import NamingService
from app.schemas.common import DataResponse, ListResponse


router = APIRouter(prefix="/ads", tags=["Ads"])

# ============================================
# Helpers
# ============================================


def _get_active_advertiser_or_404(db: Session, advertiser_id: str) -> AdAccount:
    """Return active TikTok advertiser account or raise 404."""
    advertiser = (
        db.query(AdAccount)
        .filter(
            AdAccount.platform == Platform.TIKTOK,
            AdAccount.external_account_id == advertiser_id,
            AdAccount.is_active == True,
        )
        .first()
    )
    if not advertiser:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Advertiser not found or inactive",
        )
    return advertiser


# ============================================
# Schemas
# ============================================

class AdvertiserResponse(BaseModel):
    id: int
    external_account_id: str
    name: str
    status: str
    
    class Config:
        from_attributes = True


class CampaignResponse(BaseModel):
    campaign_id: str
    campaign_name: str
    objective_type: Optional[str] = None
    budget: Optional[float] = None
    operation_status: Optional[str] = None
    

class CreateCampaignRequest(BaseModel):
    advertiser_id: str
    campaign_name: str
    objective_type: str = "VIDEO_VIEWS"
    budget_mode: str = "BUDGET_MODE_DAY"  # default day budget like legacy flow
    daily_budget: Optional[float] = 500.0  # fallback if userไม่กรอก


class CreateCampaignResponse(BaseModel):
    success: bool
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    message: Optional[str] = None


class CreateACEAdRequest(BaseModel):
    advertiser_id: str
    campaign_id: str
    campaign_name: str
    targeting_id: Optional[str] = None
    content_id: int
    adgroup_name: str
    ad_name: str
    optimization_goal: Optional[str] = None  # override default VIDEO_VIEW
    budget: Optional[float] = None  # daily budget for adgroup
    # Manual auth code input (fallback for influencer content without pre-registered auth)
    auth_code: Optional[str] = None


class CreateABXAdRequest(BaseModel):
    advertiser_id: str
    adgroup_id: str  # existing adgroup
    content_id: int
    ad_name: str
    # Manual auth code input (fallback for influencer content without pre-registered auth)
    auth_code: Optional[str] = None


class CreateAdResponse(BaseModel):
    success: bool
    adgroup_id: Optional[str] = None
    ad_id: Optional[str] = None
    message: Optional[str] = None


class SuggestNamesRequest(BaseModel):
    content_id: int
    product_codes: List[str] = []
    targeting_id: Optional[str] = None
    structure: str = "ACE"  # ACE or ABX


class SuggestNamesResponse(BaseModel):
    campaign_name: str
    adgroup_name: str
    ad_name: str


# ============================================
# Endpoints - Advertisers
# ============================================

@router.get("/advertisers", response_model=ListResponse[AdvertiserResponse])
def list_advertisers(
    platform: Platform = Platform.TIKTOK,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List active advertisers (ad accounts) for ACE/ABX ad creation
    """
    accounts = (
        db.query(AdAccount)
        .filter(
            AdAccount.platform == platform,
            AdAccount.is_active == True,
        )
        .order_by(AdAccount.name)
        .all()
    )
    
    return ListResponse(
        data=[
            AdvertiserResponse(
                id=acc.id,
                external_account_id=acc.external_account_id,
                name=acc.name,
                status="active" if acc.is_active else "inactive"
            )
            for acc in accounts
        ],
        total=len(accounts),
    )


# ============================================
# Endpoints - Campaigns
# ============================================

@router.get("/campaigns/{advertiser_id}", response_model=DataResponse[Dict])
def get_campaigns(
    advertiser_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch campaigns for a specific advertiser from local database (fast!)
    Data is synced from TikTok API periodically
    """
    ad_account = _get_active_advertiser_or_404(db, advertiser_id)
    
    # Query from local database instead of TikTok API
    campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.ad_account_id == ad_account.id,
            Campaign.deleted_at.is_(None),
        )
        .order_by(Campaign.name)
        .all()
    )
    
    # Map status enum to operation_status string
    def get_operation_status(status):
        if status == AdStatus.ACTIVE:
            return "ENABLE"
        elif status == AdStatus.PAUSED:
            return "DISABLE"
        return status.value if status else None
    
    return DataResponse(
        data={
            "list": [
                CampaignResponse(
                    campaign_id=c.external_campaign_id,
                    campaign_name=c.name,
                    objective_type=c.objective_raw or (c.objective.value if c.objective else None),
                    budget=float(c.daily_budget) if c.daily_budget else None,
                    operation_status=get_operation_status(c.status),
                ).model_dump()
                for c in campaigns
            ],
            "total": len(campaigns),
        }
    )


@router.post("/campaigns/create", response_model=DataResponse[CreateCampaignResponse])
def create_campaign(
    payload: CreateCampaignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new campaign on TikTok
    """
    _get_active_advertiser_or_404(db, payload.advertiser_id)
    
    # If budget_mode is DAY but budget not provided, use sensible default
    daily_budget = payload.daily_budget
    if payload.budget_mode == "BUDGET_MODE_DAY" and (daily_budget is None or daily_budget <= 0):
        daily_budget = 500.0
    
    result = TikTokAdsService.create_campaign(
        advertiser_id=payload.advertiser_id,
        campaign_name=payload.campaign_name,
        objective_type=payload.objective_type,
        budget_mode=payload.budget_mode,
        daily_budget=daily_budget,
    )
    
    return DataResponse(
        data=CreateCampaignResponse(**result),
        message="Campaign created" if result.get("success") else result.get("message", "Failed"),
    )


# ============================================
# Endpoints - AdGroups (for ABX)
# ============================================

@router.get("/adgroups/{advertiser_id}", response_model=DataResponse[Dict])
def get_abx_adgroups(
    advertiser_id: str,
    campaign_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch ABX adgroups for a specific advertiser/campaign from local database (fast!)
    ABX adgroups are identified by having "_ABX_" in their name
    Data is synced from TikTok API periodically
    """
    ad_account = _get_active_advertiser_or_404(db, advertiser_id)
    
    # Build query from local database
    query = (
        db.query(AdGroup)
        .filter(
            AdGroup.ad_account_id == ad_account.id,
            AdGroup.deleted_at.is_(None),
            AdGroup.name.contains("_ABX_"),  # Only ABX adgroups
        )
    )
    
    # Filter by campaign if provided
    if campaign_id:
        # Find internal campaign id from external id
        campaign = db.query(Campaign).filter(
            Campaign.external_campaign_id == campaign_id,
            Campaign.ad_account_id == ad_account.id,
        ).first()
        if campaign:
            query = query.filter(AdGroup.campaign_id == campaign.id)
        else:
            # Campaign not found - return empty
            return DataResponse(data={"list": [], "total": 0})
    
    adgroups = query.order_by(AdGroup.name).all()
    
    # Map status enum to operation_status string
    def get_operation_status(status):
        if status == AdStatus.ACTIVE:
            return "ENABLE"
        elif status == AdStatus.PAUSED:
            return "DISABLE"
        return status.value if status else None
    
    # Get campaign external ids for response
    campaign_ids = {ag.campaign_id for ag in adgroups}
    campaigns_map = {}
    if campaign_ids:
        campaigns = db.query(Campaign).filter(Campaign.id.in_(campaign_ids)).all()
        campaigns_map = {c.id: c.external_campaign_id for c in campaigns}
    
    return DataResponse(
        data={
            "list": [
                {
                    "adgroup_id": ag.external_adgroup_id,
                    "adgroup_name": ag.name,
                    "campaign_id": campaigns_map.get(ag.campaign_id, ""),
                    "operation_status": get_operation_status(ag.status),
                    "budget": float(ag.daily_budget) if ag.daily_budget else None,
                }
                for ag in adgroups
            ],
            "total": len(adgroups),
        }
    )


class CreateAdgroupRequest(BaseModel):
    advertiser_id: str
    campaign_id: str
    adgroup_name: str
    targeting_id: Optional[str] = None
    budget: float = 500.0
    structure: str = "ABX"  # 'ACE' or 'ABX'


class CreateAdgroupResponse(BaseModel):
    success: bool
    adgroup_id: Optional[str] = None
    message: Optional[str] = None


@router.post("/adgroups/create", response_model=DataResponse[CreateAdgroupResponse])
def create_adgroup(
    payload: CreateAdgroupRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new AdGroup on TikTok (for ABX or ACE)
    """
    _get_active_advertiser_or_404(db, payload.advertiser_id)
    
    # Get targeting data if provided
    targeting_data = None
    if payload.targeting_id:
        targeting = db.query(TargetingTemplate).filter(
            TargetingTemplate.id == int(payload.targeting_id)
        ).first()
        if targeting:
            targeting_data = targeting.settings
    
    result = TikTokAdsService.create_adgroup(
        advertiser_id=payload.advertiser_id,
        campaign_id=payload.campaign_id,
        adgroup_name=payload.adgroup_name,
        targeting=targeting_data,
        budget=payload.budget,
    )
    
    return DataResponse(
        data=CreateAdgroupResponse(**result),
        message="AdGroup created" if result.get("success") else result.get("message", "Failed"),
    )


# ============================================
# Endpoints - Create Ads
# ============================================

@router.post("/ace/create", response_model=DataResponse[CreateAdResponse])
def create_ace_ad(
    payload: CreateACEAdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create ACE Ad (new adgroup + ad for a single content)
    
    ACE = 1 AdGroup per 1 Content
    
    For Influencer content:
    - ถ้ามี SparkAdAuth bound อยู่แล้ว → ใช้ identity_id จาก SparkAdAuth
    - ถ้าไม่มี และส่ง auth_code มา → authorize ก่อนแล้วค่อย create
    - ถ้าไม่มีทั้งสอง → return error พร้อม needs_auth_code=true
    """
    from app.models import SparkAdAuth, SparkAuthStatus
    from app.models.enums import ContentSource
    from app.services.spark_auth_service import SparkAuthService
    
    advertiser = _get_active_advertiser_or_404(db, payload.advertiser_id)
    # Validate content exists
    content = db.query(Content).filter(Content.id == payload.content_id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found"
        )
    
    if content.platform != Platform.TIKTOK:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content platform is not TikTok"
        )
    
    if not content.platform_post_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content does not have a TikTok item ID"
        )
    
    # Get targeting data if provided
    targeting_data = None
    if payload.targeting_id:
        targeting = db.query(TargetingTemplate).filter(
            TargetingTemplate.id == int(payload.targeting_id)
        ).first()
        if targeting:
            targeting_data = targeting.settings
    
    # Bind content to advertiser if not set; otherwise enforce same advertiser
    if content.ad_account_id is None:
        content.ad_account_id = advertiser.id
        db.commit()
        db.refresh(content)
    elif content.ad_account_id != advertiser.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content is linked to a different advertiser account"
        )
    
    # ============================================
    # Resolve identity for Spark Ads
    # ============================================
    identity_id = None
    identity_type = "TT_USER"
    spark_auth = None
    
    # Check if content is INFLUENCER
    is_influencer = content.content_source == ContentSource.INFLUENCER
    
    if is_influencer:
        # For Influencer content: check SparkAdAuth first
        spark_auth = db.query(SparkAdAuth).filter(
            SparkAdAuth.content_id == content.id,
            SparkAdAuth.status.in_([SparkAuthStatus.AUTHORIZED, SparkAuthStatus.BOUND]),
            SparkAdAuth.deleted_at.is_(None),
        ).first()
        
        if spark_auth and spark_auth.is_usable:
            # Use identity from SparkAdAuth
            identity_id = spark_auth.identity_id
            identity_type = "AUTH_CODE"
        elif payload.auth_code:
            # Manual auth code provided - authorize it first
            auth_result = SparkAuthService.authorize_single(
                auth_code=payload.auth_code,
                ad_account_id=advertiser.id,
                influencer_name=content.creator_name,
                imported_by=current_user.id,
            )
            
            if auth_result.get("authorized", 0) > 0:
                # Get the newly created SparkAdAuth
                details = auth_result.get("details", [])
                if details and details[0].get("status") in ["authorized", "bound"]:
                    # Refetch to get the identity_id
                    spark_auth = db.query(SparkAdAuth).filter(
                        SparkAdAuth.auth_code == payload.auth_code,
                        SparkAdAuth.deleted_at.is_(None),
                    ).first()
                    
                    if spark_auth:
                        identity_id = spark_auth.identity_id
                        identity_type = "AUTH_CODE"
                        
                        # Bind to content if not already bound
                        if not spark_auth.content_id:
                            spark_auth.content_id = content.id
                            spark_auth.status = SparkAuthStatus.BOUND
                            db.commit()
            
            if not identity_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to authorize auth code: {auth_result.get('details', [{}])[0].get('error', 'Unknown error')}"
                )
        else:
            # No SparkAdAuth and no manual auth_code
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Influencer content requires auth code. Please provide auth_code or pre-register it.",
                    "needs_auth_code": True,
                    "content_id": content.id,
                }
            )
    else:
        # For Official/Staff content: use standard identity lookup
        identity_id = TikTokAdsService.get_identity_id(payload.advertiser_id, content.platform_post_id)
        
        if not identity_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Identity ID not found for this content/advertiser"
            )
    
    # Create adgroup + ad on TikTok
    result = TikTokAdsService.create_ace_adgroup_and_ad(
        advertiser_id=payload.advertiser_id,
        campaign_id=payload.campaign_id,
        tiktok_item_id=content.platform_post_id,
        adgroup_name=payload.adgroup_name,
        ad_name=payload.ad_name,
        targeting=targeting_data,
        budget=payload.budget or 200.0,
        optimization_goal=payload.optimization_goal or "VIDEO_VIEW",
        identity_id=identity_id,
        identity_type=identity_type,
    )
    
    if result.get("success"):
        # Mark SparkAdAuth as used
        if spark_auth:
            ad_id_str = result.get("ad_id")
            if ad_id_str:
                # Find or create internal Ad record
                ad = db.query(Ad).filter(Ad.external_ad_id == ad_id_str).first()
                spark_auth.status = SparkAuthStatus.USED
                spark_auth.used_at = datetime.utcnow()
                if ad:
                    spark_auth.used_in_ad_id = ad.id
                db.commit()
        
        # Sync the new ad back to our database
        ad_account = db.query(AdAccount).filter(
            AdAccount.external_account_id == payload.advertiser_id
        ).first()
        if ad_account:
            TikTokAdsService.sync_ads_for_account(db, ad_account, days=1)
    
    return DataResponse(
        data=CreateAdResponse(**result),
        message="ACE Ad created successfully" if result.get("success") else result.get("message", "Failed"),
    )


@router.post("/abx/create", response_model=DataResponse[CreateAdResponse])
def create_abx_ad(
    payload: CreateABXAdRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create ABX Ad (add content to existing adgroup)
    
    ABX = Multiple content in 1 AdGroup
    
    For Influencer content:
    - ถ้ามี SparkAdAuth bound อยู่แล้ว → ใช้ identity_id จาก SparkAdAuth
    - ถ้าไม่มี และส่ง auth_code มา → authorize ก่อนแล้วค่อย create
    - ถ้าไม่มีทั้งสอง → return error พร้อม needs_auth_code=true
    """
    from app.models import SparkAdAuth, SparkAuthStatus
    from app.models.enums import ContentSource
    from app.services.spark_auth_service import SparkAuthService
    
    advertiser = _get_active_advertiser_or_404(db, payload.advertiser_id)
    # Validate content exists
    content = db.query(Content).filter(Content.id == payload.content_id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found"
        )
    
    if content.platform != Platform.TIKTOK:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content platform is not TikTok"
        )
    
    if not content.platform_post_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content does not have a TikTok item ID"
        )
    
    # Bind content to advertiser if not set; otherwise enforce same advertiser
    if content.ad_account_id is None:
        content.ad_account_id = advertiser.id
        db.commit()
        db.refresh(content)
    elif content.ad_account_id != advertiser.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content is linked to a different advertiser account"
        )
    
    # ============================================
    # Resolve identity for Spark Ads
    # ============================================
    identity_id = None
    identity_type = "TT_USER"
    spark_auth = None
    
    # Check if content is INFLUENCER
    is_influencer = content.content_source == ContentSource.INFLUENCER
    
    if is_influencer:
        # For Influencer content: check SparkAdAuth first
        spark_auth = db.query(SparkAdAuth).filter(
            SparkAdAuth.content_id == content.id,
            SparkAdAuth.status.in_([SparkAuthStatus.AUTHORIZED, SparkAuthStatus.BOUND]),
            SparkAdAuth.deleted_at.is_(None),
        ).first()
        
        if spark_auth and spark_auth.is_usable:
            # Use identity from SparkAdAuth
            identity_id = spark_auth.identity_id
            identity_type = "AUTH_CODE"
        elif payload.auth_code:
            # Manual auth code provided - authorize it first
            auth_result = SparkAuthService.authorize_single(
                auth_code=payload.auth_code,
                ad_account_id=advertiser.id,
                influencer_name=content.creator_name,
                imported_by=current_user.id,
            )
            
            if auth_result.get("authorized", 0) > 0:
                # Get the newly created SparkAdAuth
                spark_auth = db.query(SparkAdAuth).filter(
                    SparkAdAuth.auth_code == payload.auth_code,
                    SparkAdAuth.deleted_at.is_(None),
                ).first()
                
                if spark_auth:
                    identity_id = spark_auth.identity_id
                    identity_type = "AUTH_CODE"
                    
                    # Bind to content if not already bound
                    if not spark_auth.content_id:
                        spark_auth.content_id = content.id
                        spark_auth.status = SparkAuthStatus.BOUND
                        db.commit()
            
            if not identity_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to authorize auth code: {auth_result.get('details', [{}])[0].get('error', 'Unknown error')}"
                )
        else:
            # No SparkAdAuth and no manual auth_code
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Influencer content requires auth code. Please provide auth_code or pre-register it.",
                    "needs_auth_code": True,
                    "content_id": content.id,
                }
            )
    else:
        # For Official/Staff content: use standard identity lookup
        identity_id = TikTokAdsService.get_identity_id(payload.advertiser_id, content.platform_post_id)
        
        if not identity_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Identity ID not found for this content/advertiser"
            )
    
    # Create ad in existing adgroup on TikTok
    result = TikTokAdsService.create_abx_ad(
        advertiser_id=payload.advertiser_id,
        adgroup_id=payload.adgroup_id,
        tiktok_item_id=content.platform_post_id,
        ad_name=payload.ad_name,
        identity_id=identity_id,
        identity_type=identity_type,
    )
    
    if result.get("success"):
        # Mark SparkAdAuth as used
        if spark_auth:
            ad_id_str = result.get("ad_id")
            if ad_id_str:
                ad = db.query(Ad).filter(Ad.external_ad_id == ad_id_str).first()
                spark_auth.status = SparkAuthStatus.USED
                spark_auth.used_at = datetime.utcnow()
                if ad:
                    spark_auth.used_in_ad_id = ad.id
                db.commit()
        
        # Sync the new ad back to our database
        ad_account = db.query(AdAccount).filter(
            AdAccount.external_account_id == payload.advertiser_id
        ).first()
        if ad_account:
            TikTokAdsService.sync_ads_for_account(db, ad_account, days=1)
    
    return DataResponse(
        data=CreateAdResponse(**result),
        message="ABX Ad created successfully" if result.get("success") else result.get("message", "Failed"),
    )


# ============================================
# Endpoints - Name Suggestions
# ============================================

@router.post("/suggest-names", response_model=DataResponse[SuggestNamesResponse])
def suggest_ad_names(
    payload: SuggestNamesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate suggested names for Campaign, AdGroup, and Ad
    based on products, targeting, and structure
    """
    # Get content info
    content = db.query(Content).filter(Content.id == payload.content_id).first()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Content not found"
        )
    
    # Use content's product_codes if not provided
    product_codes = payload.product_codes or content.product_codes or []
    
    # Map content_type to style code
    content_style = None
    if content.content_type:
        style_map = {
            "sale": "SALE",
            "review": "REV",
            "branding": "BR",
            "ecom": "ECOM",
            "e-commerce": "ECOM",
        }
        content_style = style_map.get(content.content_type.lower(), "OTH")
    
    # Determine structure code
    structure_code = "ACE" if payload.structure.upper() == "ACE" else "ABX"
    
    # Generate names using NamingService
    campaign_name = NamingService.generate_campaign_name(
        product_codes=product_codes,
        objective_code="VV",  # Default to Video Views
        strategy_code=None,
        period_code=None,
    )
    
    adgroup_name = NamingService.generate_adgroup_name(
        product_codes=product_codes,
        structure_code=structure_code,
        content_style_code=content_style,
        targeting_code=payload.targeting_id,
    )
    
    ad_name = NamingService.generate_ad_name(
        product_codes=product_codes,
        structure_code=structure_code,
        targeting_code=payload.targeting_id,
        content_code=content.platform_post_id,
        content_style_code=content_style,
        angle_code=None,
    )
    
    return DataResponse(
        data=SuggestNamesResponse(
            campaign_name=campaign_name,
            adgroup_name=adgroup_name,
            ad_name=ad_name,
        )
    )


# ============================================
# Endpoints - Targeting
# ============================================

@router.get("/targeting-templates", response_model=ListResponse[Dict])
def list_targeting_templates(
    db: Session = Depends(get_db),
):
    """
    List available targeting templates
    """
    templates = db.query(TargetingTemplate).filter(
        TargetingTemplate.is_active == True
    ).order_by(TargetingTemplate.name).all()
    
    return ListResponse(
        data=[
            {
                "id": t.id,
                "name": t.name,
                "targeting_code": t.targeting_code,
            }
            for t in templates
        ],
        total=len(templates),
    )

