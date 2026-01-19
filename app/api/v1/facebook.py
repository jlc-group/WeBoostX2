"""
Facebook Content API Endpoints
Provides REST API for Facebook posts and sync operations
"""
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.deps import get_db
from app.core.config import settings
from app.models.content import Content
from app.models.platform import AdAccount
from app.models.enums import Platform
from app.services.facebook.fb_sync import FacebookSyncService

router = APIRouter(prefix="/facebook", tags=["Facebook"])


# ========================================
# Config Endpoints
# ========================================

@router.get("/config/pages")
async def get_facebook_pages():
    """Get configured Facebook Page IDs from environment"""
    page_ids = settings.fb_page_ids
    return {
        "pages": [
            {"id": pid, "name": f"Page {pid}"} for pid in page_ids
        ]
    }


# ========================================
# Pydantic Schemas
# ========================================

class FacebookPostResponse(BaseModel):
    """Response schema for Facebook post"""
    id: int
    platform_post_id: str
    url: Optional[str] = None
    caption: Optional[str] = None
    thumbnail_url: Optional[str] = None
    platform_created_at: Optional[datetime] = None
    views: int = 0
    impressions: int = 0
    reach: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    fb_score: Optional[float] = None

    class Config:
        from_attributes = True


class SyncRequest(BaseModel):
    """Request schema for sync operation"""
    page_id: str
    ad_account_id: Optional[int] = None
    days_back: int = 365
    skip_insights: bool = True  # Skip insights for faster sync (default)


class SyncResponse(BaseModel):
    """Response schema for sync operation"""
    status: str
    message: str
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


class PageSummary(BaseModel):
    """Summary of a Facebook page's content"""
    page_id: str
    total_posts: int
    total_videos: int
    total_impressions: int
    total_reach: int
    last_synced: Optional[datetime]


# ========================================
# Content Endpoints
# ========================================

@router.get("/contents", response_model=List[FacebookPostResponse])
async def list_facebook_contents(
    page_id: Optional[str] = Query(None, description="Filter by page ID"),
    ad_account_id: Optional[int] = Query(None, description="Filter by ad account"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """
    List Facebook content (posts) from database.
    Use page_id or ad_account_id to filter results.
    """
    query = db.query(Content).filter(Content.platform == Platform.FACEBOOK)

    if page_id:
        query = query.filter(
            Content.platform_metrics.op("->")("page_id").astext == page_id
        )

    if ad_account_id:
        query = query.filter(Content.ad_account_id == ad_account_id)

    # Order by created date desc
    query = query.order_by(Content.platform_created_at.desc())

    contents = query.offset(skip).limit(limit).all()

    return [
        FacebookPostResponse(
            id=c.id,
            platform_post_id=c.platform_post_id,
            url=c.url,
            caption=c.caption,
            thumbnail_url=c.thumbnail_url,
            platform_created_at=c.platform_created_at,
            views=c.views or 0,
            impressions=c.impressions or 0,
            reach=c.reach or 0,
            likes=c.likes or 0,
            comments=c.comments or 0,
            shares=c.shares or 0,
            fb_score=float(c.fb_score) if c.fb_score else None,
        )
        for c in contents
    ]


@router.get("/contents/{content_id}", response_model=FacebookPostResponse)
async def get_facebook_content(
    content_id: int,
    db: Session = Depends(get_db),
):
    """Get a single Facebook content by ID"""
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.platform == Platform.FACEBOOK,
    ).first()

    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    return FacebookPostResponse(
        id=content.id,
        platform_post_id=content.platform_post_id,
        url=content.url,
        caption=content.caption,
        thumbnail_url=content.thumbnail_url,
        platform_created_at=content.platform_created_at,
        views=content.views or 0,
        impressions=content.impressions or 0,
        reach=content.reach or 0,
        likes=content.likes or 0,
        comments=content.comments or 0,
        shares=content.shares or 0,
        fb_score=float(content.fb_score) if content.fb_score else None,
    )


@router.get("/contents/stats/summary")
async def get_facebook_summary(
    page_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get summary statistics for Facebook content"""
    from sqlalchemy import func

    query = db.query(Content).filter(Content.platform == Platform.FACEBOOK)

    if page_id:
        query = query.filter(
            Content.platform_metrics.op("->")("page_id").astext == page_id
        )

    # Aggregate stats
    stats = db.query(
        func.count(Content.id).label("total"),
        func.sum(Content.impressions).label("impressions"),
        func.sum(Content.reach).label("reach"),
        func.sum(Content.views).label("views"),
        func.sum(Content.likes).label("likes"),
        func.avg(Content.fb_score).label("avg_score"),
    ).filter(Content.platform == Platform.FACEBOOK).first()

    return {
        "total_posts": stats.total or 0,
        "total_impressions": int(stats.impressions or 0),
        "total_reach": int(stats.reach or 0),
        "total_views": int(stats.views or 0),
        "total_likes": int(stats.likes or 0),
        "average_fb_score": float(stats.avg_score) if stats.avg_score else None,
    }


# ========================================
# Sync Endpoints
# ========================================

@router.post("/sync/posts", response_model=SyncResponse)
async def sync_facebook_posts(
    request: SyncRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Sync Facebook posts from a page to database.
    Runs in background for large syncs.
    """
    sync_service = FacebookSyncService(db=db)

    try:
        stats = await sync_service.sync_posts(
            page_id=request.page_id,
            ad_account_id=request.ad_account_id,
            days_back=request.days_back,
            skip_insights=request.skip_insights,
        )

        return SyncResponse(
            status="completed",
            message=f"Synced posts from page {request.page_id}",
            created=stats.get("created", 0),
            updated=stats.get("updated", 0),
            skipped=stats.get("skipped", 0),
            errors=stats.get("errors", 0),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await sync_service.close()


@router.post("/sync/videos", response_model=SyncResponse)
async def sync_facebook_videos(
    request: SyncRequest,
    db: Session = Depends(get_db),
):
    """Sync Facebook video posts from a page"""
    sync_service = FacebookSyncService(db=db)

    try:
        stats = await sync_service.sync_video_posts(
            page_id=request.page_id,
            ad_account_id=request.ad_account_id,
            days_back=request.days_back,
        )

        return SyncResponse(
            status="completed",
            message=f"Synced videos from page {request.page_id}",
            created=stats.get("created", 0),
            updated=stats.get("updated", 0),
            errors=stats.get("errors", 0),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await sync_service.close()


@router.post("/sync/ad-accounts")
async def sync_facebook_ad_accounts(
    db: Session = Depends(get_db),
):
    """Sync Facebook ad accounts to database"""
    sync_service = FacebookSyncService(db=db)

    try:
        accounts = await sync_service.sync_ad_accounts()

        return {
            "status": "completed",
            "message": f"Synced {len(accounts)} ad accounts",
            "accounts": [
                {"id": acc.id, "name": acc.name, "external_id": acc.external_account_id}
                for acc in accounts
            ],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await sync_service.close()


# ========================================
# Ad Accounts Endpoints
# ========================================

@router.get("/ad-accounts")
async def list_facebook_ad_accounts(
    db: Session = Depends(get_db),
):
    """List Facebook ad accounts from database"""
    accounts = db.query(AdAccount).filter(
        AdAccount.platform == Platform.FACEBOOK
    ).all()

    return [
        {
            "id": acc.id,
            "external_id": acc.external_account_id,
            "name": acc.name,
            "status": acc.status.value if acc.status else None,
            "currency": acc.currency,
            "is_active": acc.is_active,
        }
        for acc in accounts
    ]
