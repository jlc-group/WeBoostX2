"""
Content API endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional

from app.core.deps import get_db
from app.core.config import settings
from app.models import Content
from app.models.enums import Platform, ContentStatus, ContentType
from app.schemas.common import DataResponse, ListResponse
from app.services.tiktok_service import TikTokService

router = APIRouter(prefix="/contents", tags=["Contents"])


@router.get("", response_model=ListResponse)
def get_contents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    platform: Optional[str] = None,
    status: Optional[str] = None,
    content_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get contents with filtering and pagination"""
    
    query = db.query(Content).filter(Content.deleted_at.is_(None))
    
    # Apply filters
    if platform:
        try:
            platform_enum = Platform(platform.lower())
            query = query.filter(Content.platform == platform_enum)
        except ValueError:
            pass
    
    if status:
        try:
            status_enum = ContentStatus(status.lower())
            query = query.filter(Content.status == status_enum)
        except ValueError:
            pass
    
    if content_type:
        try:
            type_enum = ContentType(content_type.lower())
            query = query.filter(Content.content_type == type_enum)
        except ValueError:
            pass
    
    if search:
        query = query.filter(
            or_(
                Content.caption.ilike(f"%{search}%"),
                Content.creator_name.ilike(f"%{search}%"),
                Content.platform_post_id.ilike(f"%{search}%")
            )
        )
    
    # Get total count
    total = query.count()
    
    # Apply pagination and ordering
    contents = query.order_by(Content.created_at.desc())\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()
    
    # Convert to dict
    data = []
    for c in contents:
        data.append({
            "id": c.id,
            "platform": c.platform.value if c.platform else None,
            "platform_post_id": c.platform_post_id,
            "url": c.url,
            "caption": c.caption,
            "thumbnail_url": c.thumbnail_url,
            "platform_created_at": c.platform_created_at.isoformat() if c.platform_created_at else None,
            "content_type": c.content_type.value if c.content_type else None,
            "status": c.status.value if c.status else None,
            "creator_name": c.creator_name,
            "views": c.views,
            "likes": c.likes,
            "comments": c.comments,
            "shares": c.shares,
            "saves": c.saves,
            "pfm_score": float(c.pfm_score) if c.pfm_score else 0,
            "fb_score": float(c.fb_score) if c.fb_score else 0,
            "unified_score": float(c.unified_score) if c.unified_score else 0,
            "ads_total_cost": float(c.ads_total_cost) if c.ads_total_cost else 0,
        })
    
    return ListResponse(
        success=True,
        data=data,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/stats")
def get_content_stats(db: Session = Depends(get_db)):
    """Get content statistics"""
    
    # Count by platform
    tiktok_count = db.query(Content).filter(
        Content.platform == Platform.TIKTOK,
        Content.deleted_at.is_(None)
    ).count()
    
    facebook_count = db.query(Content).filter(
        Content.platform == Platform.FACEBOOK,
        Content.deleted_at.is_(None)
    ).count()
    
    instagram_count = db.query(Content).filter(
        Content.platform == Platform.INSTAGRAM,
        Content.deleted_at.is_(None)
    ).count()
    
    # Average PFM
    avg_pfm = db.query(func.avg(Content.pfm_score)).filter(
        Content.pfm_score.isnot(None),
        Content.deleted_at.is_(None)
    ).scalar() or 0
    
    return DataResponse(
        success=True,
        data={
            "tiktok": tiktok_count,
            "facebook": facebook_count,
            "instagram": instagram_count,
            "avg_pfm": float(avg_pfm)
        }
    )


@router.post("/sync")
def sync_contents(db: Session = Depends(get_db)):
    """Sync contents from all platforms"""
    
    results = {
        "tiktok": {"success": False, "synced": 0},
        "facebook": {"success": False, "synced": 0},
        "instagram": {"success": False, "synced": 0}
    }
    
    total_synced = 0
    
    # Resolve effective TikTok credentials
    # - access_token: ใช้ TikTokService.get_access_token() (รองรับทั้ง token ตรง ๆ และ refresh token)
    # - business_id: ใช้จาก settings (TIKTOK_BUSINESS_ID หรือ BUSINESS_ID)
    access_token = TikTokService.get_access_token()
    business_id = settings.tiktok_business_id

    # Sync TikTok
    if access_token and business_id:
        try:
            result = TikTokService.fetch_and_sync_all_videos(
                access_token,
                business_id,
                fetch_type="latest",
            )
            results["tiktok"] = {
                "success": result.get("success", False),
                "synced": result.get("total_synced", 0),
                "details": result,
            }
            total_synced += result.get("total_synced", 0)
        except Exception as e:
            results["tiktok"]["error"] = str(e)
    else:
        if not access_token:
            results["tiktok"]["message"] = "TikTok access token not configured"
        if not business_id:
            results["tiktok"]["message"] = (
                results["tiktok"].get("message", "")
                + " | TikTok business ID not configured"
            ).strip(" |")
    
    # TODO: Sync Facebook
    # TODO: Sync Instagram
    
    return DataResponse(
        success=True,
        data={
            "synced": total_synced,
            "details": results
        },
        message=f"Synced {total_synced} contents"
    )


@router.post("/recalculate-pfm")
def recalculate_pfm(db: Session = Depends(get_db)):
    """Recalculate PFM scores for all TikTok content"""
    
    updated = TikTokService.update_all_pfm_scores()
    
    return DataResponse(
        success=True,
        data={"updated": updated},
        message=f"Updated PFM for {updated} contents"
    )


@router.get("/{content_id}")
def get_content(content_id: int, db: Session = Depends(get_db)):
    """Get single content by ID"""
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    return DataResponse(
        success=True,
        data={
            "id": content.id,
            "platform": content.platform.value if content.platform else None,
            "platform_post_id": content.platform_post_id,
            "url": content.url,
            "caption": content.caption,
            "thumbnail_url": content.thumbnail_url,
            "platform_created_at": content.platform_created_at.isoformat() if content.platform_created_at else None,
            "content_type": content.content_type.value if content.content_type else None,
            "content_source": content.content_source.value if content.content_source else None,
            "status": content.status.value if content.status else None,
            "product_codes": content.product_codes,
            "creator_name": content.creator_name,
            "creator_id": content.creator_id,
            "video_duration": float(content.video_duration) if content.video_duration else 0,
            "views": content.views,
            "impressions": content.impressions,
            "reach": content.reach,
            "likes": content.likes,
            "comments": content.comments,
            "shares": content.shares,
            "saves": content.saves,
            "total_watch_time": float(content.total_watch_time) if content.total_watch_time else 0,
            "avg_watch_time": float(content.avg_watch_time) if content.avg_watch_time else 0,
            "completion_rate": float(content.completion_rate) if content.completion_rate else 0,
            "pfm_score": float(content.pfm_score) if content.pfm_score else 0,
            "fb_score": float(content.fb_score) if content.fb_score else 0,
            "unified_score": float(content.unified_score) if content.unified_score else 0,
            "ads_total_cost": float(content.ads_total_cost) if content.ads_total_cost else 0,
            "ace_ad_count": content.ace_ad_count,
            "abx_ad_count": content.abx_ad_count,
            "platform_metrics": content.platform_metrics,
            "created_at": content.created_at.isoformat() if content.created_at else None,
            "updated_at": content.updated_at.isoformat() if content.updated_at else None,
        }
    )


@router.put("/{content_id}")
def update_content(
    content_id: int,
    content_type: Optional[str] = None,
    status: Optional[str] = None,
    product_codes: Optional[list] = None,
    db: Session = Depends(get_db)
):
    """Update content"""
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    if content_type:
        try:
            content.content_type = ContentType(content_type.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid content type")
    
    if status:
        try:
            content.status = ContentStatus(status.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
    
    if product_codes is not None:
        content.product_codes = product_codes
    
    db.commit()
    
    return DataResponse(
        success=True,
        message="Content updated"
    )

