"""
TikTok Targeting API endpoints
"""
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.deps import get_db
from app.models import TargetingTemplate
from app.models.enums import Platform


router = APIRouter(prefix="/targeting", tags=["targeting"])


# ============================================
# Pydantic Schemas
# ============================================

class TargetingBase(BaseModel):
    targeting_code: str  # Unique code like "MF_SUN_MASS_18_54"
    name: str
    platform: str = "tiktok"
    
    # Targeting options
    age_range: Optional[List[str]] = None  # ["AGE_18_24", "AGE_25_34", "AGE_35_44"]
    gender: Optional[str] = None  # MALE, FEMALE, ALL
    locations: Optional[List[dict]] = None  # [{"id": "6252001", "name": "Thailand"}]
    languages: Optional[List[str]] = None
    interests: Optional[List[dict]] = None  # Interest categories
    behaviors: Optional[List[dict]] = None  # Action categories
    hashtags: Optional[List[dict]] = None  # [{"id": "...", "name": "..."}]
    custom_audiences: Optional[List[str]] = None
    excluded_audiences: Optional[List[str]] = None
    
    # Device targeting
    device_types: Optional[List[str]] = None  # ["MOBILE", "TABLET"]
    os_versions: Optional[dict] = None
    network_types: Optional[List[str]] = None  # ["WIFI", "4G", "5G"]
    
    # Audience estimation
    audience_size_lower: Optional[int] = None
    audience_size_upper: Optional[int] = None
    
    # Management
    is_approved: bool = False
    is_active: bool = True


class TargetingCreate(TargetingBase):
    pass


class TargetingUpdate(BaseModel):
    name: Optional[str] = None
    
    # Targeting options
    age_range: Optional[List[str]] = None
    gender: Optional[str] = None
    locations: Optional[List[dict]] = None
    languages: Optional[List[str]] = None
    interests: Optional[List[dict]] = None
    behaviors: Optional[List[dict]] = None
    hashtags: Optional[List[str]] = None
    custom_audiences: Optional[List[str]] = None
    excluded_audiences: Optional[List[str]] = None
    
    # Device targeting
    device_types: Optional[List[str]] = None
    os_versions: Optional[dict] = None
    network_types: Optional[List[str]] = None
    
    # Audience estimation
    audience_size_lower: Optional[int] = None
    audience_size_upper: Optional[int] = None
    
    # Management
    is_approved: Optional[bool] = None
    is_active: Optional[bool] = None


class TargetingResponse(TargetingBase):
    id: int
    
    class Config:
        from_attributes = True


class TargetingListResponse(BaseModel):
    id: int
    targeting_code: str
    name: str
    platform: str
    gender: Optional[str] = None
    locations: Optional[List[dict]] = None
    age_range: Optional[List[str]] = None
    languages: Optional[List[str]] = None
    interests: Optional[List[dict]] = None
    behaviors: Optional[List[dict]] = None
    hashtags: Optional[List[dict]] = None
    audience_size_lower: Optional[int] = None
    audience_size_upper: Optional[int] = None
    is_approved: bool
    is_active: bool
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


# ============================================
# Targeting CRUD
# ============================================

@router.get("", response_model=List[TargetingListResponse])
def get_targeting_list(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    platform: Optional[str] = "tiktok",
    is_active: Optional[bool] = None,
    is_approved: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all targeting templates with optional filtering"""
    query = db.query(TargetingTemplate)
    
    if platform:
        try:
            platform_enum = Platform(platform.lower())
            query = query.filter(TargetingTemplate.platform == platform_enum)
        except ValueError:
            pass
    
    if is_active is not None:
        query = query.filter(TargetingTemplate.is_active == is_active)
    
    if is_approved is not None:
        query = query.filter(TargetingTemplate.is_approved == is_approved)
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (TargetingTemplate.targeting_code.ilike(search_term)) | 
            (TargetingTemplate.name.ilike(search_term))
        )
    
    query = query.order_by(TargetingTemplate.targeting_code)
    
    results = query.offset(skip).limit(limit).all()
    
    # Convert platform enum to string
    return [
        TargetingListResponse(
            id=t.id,
            targeting_code=t.targeting_code,
            name=t.name,
            platform=t.platform.value if t.platform else "tiktok",
            gender=t.gender,
            locations=t.locations,
            age_range=t.age_range,
            languages=t.languages,
            interests=t.interests,
            behaviors=t.behaviors,
            hashtags=t.hashtags,
            audience_size_lower=t.audience_size_lower,
            audience_size_upper=t.audience_size_upper,
            is_approved=t.is_approved,
            is_active=t.is_active,
            created_at=t.created_at
        )
        for t in results
    ]


@router.get("/{targeting_id}", response_model=TargetingResponse)
def get_targeting(targeting_id: int, db: Session = Depends(get_db)):
    """Get single targeting template by ID"""
    targeting = db.query(TargetingTemplate).filter(
        TargetingTemplate.id == targeting_id,
        TargetingTemplate.deleted_at.is_(None)
    ).first()
    
    if not targeting:
        raise HTTPException(status_code=404, detail="Targeting template not found")
    
    # Convert to response
    return TargetingResponse(
        id=targeting.id,
        targeting_code=targeting.targeting_code,
        name=targeting.name,
        platform=targeting.platform.value if targeting.platform else "tiktok",
        age_range=targeting.age_range,
        gender=targeting.gender,
        locations=targeting.locations,
        languages=targeting.languages,
        interests=targeting.interests,
        behaviors=targeting.behaviors,
        hashtags=targeting.hashtags,
        custom_audiences=targeting.custom_audiences,
        excluded_audiences=targeting.excluded_audiences,
        device_types=targeting.device_types,
        os_versions=targeting.os_versions,
        network_types=targeting.network_types,
        audience_size_lower=targeting.audience_size_lower,
        audience_size_upper=targeting.audience_size_upper,
        is_approved=targeting.is_approved,
        is_active=targeting.is_active
    )


@router.get("/code/{targeting_code}", response_model=TargetingResponse)
def get_targeting_by_code(targeting_code: str, db: Session = Depends(get_db)):
    """Get single targeting template by code"""
    targeting = db.query(TargetingTemplate).filter(
        TargetingTemplate.targeting_code == targeting_code,
        TargetingTemplate.deleted_at.is_(None)
    ).first()
    
    if not targeting:
        raise HTTPException(status_code=404, detail="Targeting template not found")
    
    return TargetingResponse(
        id=targeting.id,
        targeting_code=targeting.targeting_code,
        name=targeting.name,
        platform=targeting.platform.value if targeting.platform else "tiktok",
        age_range=targeting.age_range,
        gender=targeting.gender,
        locations=targeting.locations,
        languages=targeting.languages,
        interests=targeting.interests,
        behaviors=targeting.behaviors,
        hashtags=targeting.hashtags,
        custom_audiences=targeting.custom_audiences,
        excluded_audiences=targeting.excluded_audiences,
        device_types=targeting.device_types,
        os_versions=targeting.os_versions,
        network_types=targeting.network_types,
        audience_size_lower=targeting.audience_size_lower,
        audience_size_upper=targeting.audience_size_upper,
        is_approved=targeting.is_approved,
        is_active=targeting.is_active
    )


@router.post("", response_model=TargetingResponse)
def create_targeting(targeting_in: TargetingCreate, db: Session = Depends(get_db)):
    """Create new targeting template"""
    # Check if code already exists
    existing = db.query(TargetingTemplate).filter(
        TargetingTemplate.targeting_code == targeting_in.targeting_code
    ).first()
    if existing:
        raise HTTPException(
            status_code=400, 
            detail=f"Targeting code '{targeting_in.targeting_code}' already exists"
        )
    
    # Convert platform string to enum
    try:
        platform_enum = Platform(targeting_in.platform.lower())
    except ValueError:
        platform_enum = Platform.TIKTOK
    
    targeting = TargetingTemplate(
        targeting_code=targeting_in.targeting_code,
        name=targeting_in.name,
        platform=platform_enum,
        age_range=targeting_in.age_range,
        gender=targeting_in.gender,
        locations=targeting_in.locations,
        languages=targeting_in.languages,
        interests=targeting_in.interests,
        behaviors=targeting_in.behaviors,
        hashtags=targeting_in.hashtags,
        custom_audiences=targeting_in.custom_audiences,
        excluded_audiences=targeting_in.excluded_audiences,
        device_types=targeting_in.device_types,
        os_versions=targeting_in.os_versions,
        network_types=targeting_in.network_types,
        audience_size_lower=targeting_in.audience_size_lower,
        audience_size_upper=targeting_in.audience_size_upper,
        is_approved=targeting_in.is_approved,
        is_active=targeting_in.is_active
    )
    
    db.add(targeting)
    db.commit()
    db.refresh(targeting)
    
    return TargetingResponse(
        id=targeting.id,
        targeting_code=targeting.targeting_code,
        name=targeting.name,
        platform=targeting.platform.value if targeting.platform else "tiktok",
        age_range=targeting.age_range,
        gender=targeting.gender,
        locations=targeting.locations,
        languages=targeting.languages,
        interests=targeting.interests,
        behaviors=targeting.behaviors,
        hashtags=targeting.hashtags,
        custom_audiences=targeting.custom_audiences,
        excluded_audiences=targeting.excluded_audiences,
        device_types=targeting.device_types,
        os_versions=targeting.os_versions,
        network_types=targeting.network_types,
        audience_size_lower=targeting.audience_size_lower,
        audience_size_upper=targeting.audience_size_upper,
        is_approved=targeting.is_approved,
        is_active=targeting.is_active
    )


@router.put("/{targeting_id}", response_model=TargetingResponse)
def update_targeting(
    targeting_id: int, 
    targeting_in: TargetingUpdate, 
    db: Session = Depends(get_db)
):
    """Update targeting template"""
    targeting = db.query(TargetingTemplate).filter(
        TargetingTemplate.id == targeting_id,
        TargetingTemplate.deleted_at.is_(None)
    ).first()
    
    if not targeting:
        raise HTTPException(status_code=404, detail="Targeting template not found")
    
    update_data = targeting_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(targeting, field, value)
    
    db.commit()
    db.refresh(targeting)
    
    return TargetingResponse(
        id=targeting.id,
        targeting_code=targeting.targeting_code,
        name=targeting.name,
        platform=targeting.platform.value if targeting.platform else "tiktok",
        age_range=targeting.age_range,
        gender=targeting.gender,
        locations=targeting.locations,
        languages=targeting.languages,
        interests=targeting.interests,
        behaviors=targeting.behaviors,
        hashtags=targeting.hashtags,
        custom_audiences=targeting.custom_audiences,
        excluded_audiences=targeting.excluded_audiences,
        device_types=targeting.device_types,
        os_versions=targeting.os_versions,
        network_types=targeting.network_types,
        audience_size_lower=targeting.audience_size_lower,
        audience_size_upper=targeting.audience_size_upper,
        is_approved=targeting.is_approved,
        is_active=targeting.is_active
    )


@router.delete("/{targeting_id}")
def delete_targeting(targeting_id: int, db: Session = Depends(get_db)):
    """Soft delete targeting template"""
    from datetime import datetime
    
    targeting = db.query(TargetingTemplate).filter(
        TargetingTemplate.id == targeting_id,
        TargetingTemplate.deleted_at.is_(None)
    ).first()
    
    if not targeting:
        raise HTTPException(status_code=404, detail="Targeting template not found")
    
    targeting.deleted_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Targeting template deleted", "id": targeting_id}


@router.post("/{targeting_id}/approve")
def approve_targeting(targeting_id: int, db: Session = Depends(get_db)):
    """Approve targeting template"""
    targeting = db.query(TargetingTemplate).filter(
        TargetingTemplate.id == targeting_id,
        TargetingTemplate.deleted_at.is_(None)
    ).first()
    
    if not targeting:
        raise HTTPException(status_code=404, detail="Targeting template not found")
    
    targeting.is_approved = True
    db.commit()
    
    return {"message": "Targeting template approved", "id": targeting_id}


@router.get("/active/list")
def get_active_targeting_codes(
    platform: str = "tiktok",
    db: Session = Depends(get_db)
):
    """Get list of active and approved targeting codes (for dropdown selection)"""
    try:
        platform_enum = Platform(platform.lower())
    except ValueError:
        platform_enum = Platform.TIKTOK
    
    targetings = db.query(
        TargetingTemplate.id,
        TargetingTemplate.targeting_code,
        TargetingTemplate.name,
        TargetingTemplate.gender,
        TargetingTemplate.audience_size_lower,
        TargetingTemplate.audience_size_upper
    ).filter(
        TargetingTemplate.platform == platform_enum,
        TargetingTemplate.is_active == True,
        TargetingTemplate.is_approved == True,
        TargetingTemplate.deleted_at.is_(None)
    ).order_by(TargetingTemplate.targeting_code).all()
    
    return [
        {
            "id": t.id,
            "targeting_code": t.targeting_code,
            "name": t.name,
            "gender": t.gender,
            "audience_size": f"{t.audience_size_lower:,} - {t.audience_size_upper:,}" if t.audience_size_lower and t.audience_size_upper else None
        }
        for t in targetings
    ]


# ============================================
# TikTok API - Fetch Targeting Options
# ============================================

@router.get("/tiktok/interests")
def get_tiktok_interests(language: str = "th"):
    """
    Fetch interest categories from TikTok API (hierarchical tree structure)
    
    Returns categories with level 1-4, each with:
    - interest_category_id
    - interest_category_name  
    - level
    - sub_category_ids (children)
    """
    from app.services.tiktok_targeting_service import TikTokTargetingService
    
    result = TikTokTargetingService.fetch_interest_categories(language=language)
    
    if "error" in result and result.get("data") == []:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result


@router.get("/tiktok/actions")
def get_tiktok_actions(language: str = "th"):
    """
    Fetch action categories from TikTok API
    
    Returns categories grouped by action_scene:
    - VIDEO_RELATED
    - CREATOR_RELATED
    - HASHTAG_RELATED
    """
    from app.services.tiktok_targeting_service import TikTokTargetingService
    
    result = TikTokTargetingService.fetch_action_categories(language=language)
    
    if "error" in result and result.get("data") == []:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result


@router.get("/tiktok/regions")
def get_tiktok_regions(language: str = "th", country: str = "TH"):
    """
    Fetch available regions/locations from TikTok API
    
    Returns list of regions with:
    - location_id
    - name
    - region_code
    - level
    """
    from app.services.tiktok_targeting_service import TikTokTargetingService
    
    result = TikTokTargetingService.fetch_regions(language=language)
    
    if "error" in result and result.get("data") == []:
        raise HTTPException(status_code=500, detail=result["error"])
    
    # Filter by country if specified
    if country and country != "ALL":
        filtered_data = [r for r in result.get("all_regions", []) if r.get("region_code") == country]
        result["data"] = filtered_data
        result["count"] = len(filtered_data)
    
    return result


@router.get("/tiktok/languages")
def get_tiktok_languages():
    """
    Fetch available languages from TikTok API
    """
    from app.services.tiktok_targeting_service import TikTokTargetingService
    
    result = TikTokTargetingService.fetch_languages()
    
    if "error" in result and result.get("data") == []:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result


@router.get("/tiktok/hashtags")
def search_tiktok_hashtags(keywords: str):
    """
    Search hashtags by keywords from TikTok API
    
    Query params:
    - keywords: Search term (min 2 characters)
    """
    from app.services.tiktok_targeting_service import TikTokTargetingService
    
    if len(keywords) < 2:
        return {"success": True, "data": [], "count": 0}
    
    # Convert single keyword string to list for API
    result = TikTokTargetingService.recommend_hashtags(keywords=[keywords])
    
    if "error" in result:
        return result  # Return error but don't raise exception for hashtag search
    
    return result


@router.post("/tiktok/hashtags/status")
def check_tiktok_hashtag_status(payload: dict):
    """
    Check status of hashtags (ONLINE/OFFLINE)
    
    Payload:
    - keyword_ids: List of hashtag IDs
    """
    from app.services.tiktok_targeting_service import TikTokTargetingService
    
    keyword_ids = payload.get("keyword_ids", [])
    if not keyword_ids:
        return {"success": True, "data": [], "count": 0}
        
    result = TikTokTargetingService.check_hashtag_status(keyword_ids=keyword_ids)
    
    if "error" in result:
        # Don't fail hard, return error structure
        return {"success": False, "error": result["error"]}
    
    return result


@router.post("/tiktok/audience-size")
def get_tiktok_audience_size(request: dict):
    """
    Get estimated audience size for targeting criteria (same format as old system)
    
    Request body:
    - locations: List of {id, name} objects
    - interests: List of {id, name} objects  
    - age_group: List of age group IDs (AGE_18_24, etc.)
    - gender: GENDER_UNLIMITED, GENDER_MALE, GENDER_FEMALE
    - languages: List of language codes
    - video_related_categories: List of action category IDs
    - creator_related_categories: List of action category IDs
    - hashtag_related_categories: List of keyword IDs
    """
    from app.services.tiktok_targeting_service import TikTokTargetingService
    
    # Extract location IDs from locations array (same as old system) or direct ID list
    locations = request.get("locations", [])
    location_ids = request.get("location_ids", [])
    if locations:
        location_ids.extend([str(loc.get("id")) for loc in locations if loc.get("id")])
    
    # Deduplicate location IDs
    if location_ids:
        location_ids = list(set(location_ids))
    
    # Extract interest IDs from interests array (same as old system) or direct ID list
    interests = request.get("interests", [])
    interest_category_ids = request.get("interest_category_ids", [])
    if interests:
        interest_category_ids.extend([str(i.get("id")) for i in interests if i.get("id")])
    
    # Deduplicate interest IDs
    if interest_category_ids:
        interest_category_ids = list(set(interest_category_ids))
    
    # Support both old format (age_group) and new format (age_groups)
    age_groups = request.get("age_group") or request.get("age_groups") or []
    
    # Get action categories directly (frontend sends this now)
    action_categories = request.get("action_categories", [])
    
    result = TikTokTargetingService.get_audience_size(
        location_ids=location_ids if location_ids else None,
        age_groups=age_groups if age_groups else None,
        gender=request.get("gender", "GENDER_UNLIMITED"),
        languages=request.get("languages"),
        interest_category_ids=interest_category_ids if interest_category_ids else None,
        action_categories=action_categories
    )
    
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    
    return result


@router.get("/options/age-groups")
def get_age_groups():
    """Get available age group options (static)"""
    from app.services.tiktok_targeting_service import TikTokTargetingService
    return TikTokTargetingService.get_age_groups()


@router.get("/options/genders")
def get_genders():
    """Get available gender options (static)"""
    from app.services.tiktok_targeting_service import TikTokTargetingService
    return TikTokTargetingService.get_genders()


# ============================================
# Cached Data from Database (Faster than API)
# ============================================

@router.get("/cache/interests")
def get_cached_interests(language: str = "th", db: Session = Depends(get_db)):
    """
    Get Interest Categories from local cache (database)
    
    Much faster than API call (~50ms vs ~2s).
    Data is synced daily via cronjob.
    
    Falls back to TikTok API if cache is empty.
    """
    from app.models.targeting_cache import TikTokInterestCategory
    
    # Try to get from database first
    categories = db.query(TikTokInterestCategory).filter(
        TikTokInterestCategory.language == language
    ).all()
    
    if categories:
        # Build tree structure from flat list
        cat_dict = {}
        root_categories = []
        
        for cat in categories:
            cat_data = {
                "interest_category_id": cat.interest_category_id,
                "interest_category_name": cat.interest_category_name,
                "level": cat.level,
                "parent_id": cat.parent_id,
                "sub_category_ids": cat.sub_category_ids or []
            }
            cat_dict[cat.interest_category_id] = cat_data
            
            if cat.level == 1:
                root_categories.append(cat_data)
        
        return {
            "success": True,
            "source": "database",
            "data": list(cat_dict.values()),
            "count": len(categories),
            "synced_at": categories[0].synced_at.isoformat() if categories else None
        }
    
    # Fallback to API if cache is empty
    from app.services.tiktok_targeting_service import TikTokTargetingService
    result = TikTokTargetingService.fetch_interest_categories(language=language)
    result["source"] = "api"
    return result


@router.get("/cache/actions")
def get_cached_actions(language: str = "th", db: Session = Depends(get_db)):
    """
    Get Action Categories from local cache (database)
    
    Much faster than API call.
    Falls back to TikTok API if cache is empty.
    """
    from app.models.targeting_cache import TikTokActionCategory
    
    # Try to get from database first
    categories = db.query(TikTokActionCategory).filter(
        TikTokActionCategory.language == language
    ).all()
    
    if categories:
        video_related = []
        creator_related = []
        
        for cat in categories:
            cat_data = {
                "action_category_id": cat.action_category_id,
                "name": cat.name,
                "description": cat.description,
                "level": cat.level,
                "parent_id": cat.parent_id,
                "sub_category_ids": cat.sub_category_ids or []
            }
            
            if cat.action_scene == "VIDEO_RELATED":
                video_related.append(cat_data)
            elif cat.action_scene == "CREATOR_RELATED":
                creator_related.append(cat_data)
        
        return {
            "success": True,
            "source": "database",
            "video_related": video_related,
            "creator_related": creator_related,
            "count": len(categories),
            "synced_at": categories[0].synced_at.isoformat() if categories else None
        }
    
    # Fallback to API if cache is empty
    from app.services.tiktok_targeting_service import TikTokTargetingService
    result = TikTokTargetingService.fetch_action_categories(language=language)
    result["source"] = "api"
    return result


@router.get("/cache/regions")
def get_cached_regions(language: str = "th", country: str = "TH", db: Session = Depends(get_db)):
    """
    Get Regions from local cache (database)
    
    Much faster than API call.
    Falls back to TikTok API if cache is empty.
    """
    from app.models.targeting_cache import TikTokRegion
    
    # Try to get from database first
    query = db.query(TikTokRegion).filter(
        TikTokRegion.language == language
    )
    
    if country and country != "ALL":
        query = query.filter(TikTokRegion.region_code == country)
    
    regions = query.all()
    
    if regions:
        return {
            "success": True,
            "source": "database",
            "data": [
                {
                    "location_id": r.location_id,
                    "name": r.name,
                    "region_code": r.region_code,
                    "level": r.level,
                    "parent_id": r.parent_id
                }
                for r in regions
            ],
            "count": len(regions),
            "synced_at": regions[0].synced_at.isoformat() if regions else None
        }
    
    # Fallback to API if cache is empty
    from app.services.tiktok_targeting_service import TikTokTargetingService
    result = TikTokTargetingService.fetch_regions(language=language)
    result["source"] = "api"
    return result


@router.post("/cache/sync")
def sync_targeting_cache(language: str = "th"):
    """
    Manually trigger sync of TikTok targeting data to local cache
    
    Usually runs daily via cronjob, but can be triggered manually.
    """
    from app.tasks.sync_targeting import sync_all_tiktok_targeting
    
    result = sync_all_tiktok_targeting(language=language)
    
    if not result.get("success"):
        raise HTTPException(status_code=500, detail="Sync failed")
    
    return result
