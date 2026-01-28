"""
TikTok Legacy API endpoints
สำหรับเชื่อมต่อกับตาราง tiktok_posts เดิมใน starcontent database
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, desc, asc, case, cast, Integer
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.models.tiktok_legacy import TiktokPost, ABXAdgroupLegacy, TiktokTargeting, ProductGroupLegacy
from app.schemas.common import DataResponse, ListResponse

router = APIRouter(prefix="/tiktok", tags=["TikTok Legacy"])


# ============================================
# Pydantic Schemas
# ============================================

class TiktokContentStats(BaseModel):
    """TikTok content statistics"""
    total_posts: int
    total_views: int
    total_likes: int
    total_comments: int
    total_shares: int
    total_bookmarks: int
    avg_pfm_score: float
    
    # By content type
    by_content_type: dict
    by_content_status: dict
    
    # Ads stats
    posts_with_ace: int
    posts_with_abx: int
    total_ace_ads: int
    total_abx_ads: int


class TiktokPostSummary(BaseModel):
    """Summary of a TikTok post"""
    item_id: str
    url: Optional[str]
    caption: Optional[str]
    thumbnail_url: Optional[str]
    video_duration: Optional[float]
    
    # Metrics
    video_views: int
    likes: int
    comments: int
    shares: int
    bookmarks: int
    reach: int
    
    # Score
    pfm_score: float
    
    # Classification
    content_type: Optional[str]
    content_status: Optional[str]
    products: Optional[str]
    
    # Ads
    ace_ad_count: int
    abx_ad_count: int
    
    # Dates
    create_time: Optional[datetime]
    
    class Config:
        from_attributes = True


# ============================================
# API Endpoints
# ============================================

@router.get("/stats", response_model=DataResponse)
def get_tiktok_stats(db: Session = Depends(get_db)):
    """Get TikTok content statistics for dashboard"""
    
    # Total counts and sums
    totals = db.query(
        func.count(TiktokPost.item_id).label('total'),
        func.sum(TiktokPost.video_views).label('views'),
        func.sum(TiktokPost.likes).label('likes'),
        func.sum(TiktokPost.comments).label('comments'),
        func.sum(TiktokPost.shares).label('shares'),
        func.sum(TiktokPost.bookmarks).label('bookmarks'),
        func.avg(TiktokPost.pfm_score).label('avg_pfm'),
        func.sum(case((TiktokPost.ace_ad_count > 0, 1), else_=0)).label('posts_with_ace'),
        func.sum(case((TiktokPost.abx_ad_count > 0, 1), else_=0)).label('posts_with_abx'),
        func.sum(TiktokPost.ace_ad_count).label('total_ace'),
        func.sum(TiktokPost.abx_ad_count).label('total_abx'),
    ).first()
    
    # By content type
    content_type_stats = db.query(
        TiktokPost.content_type,
        func.count(TiktokPost.item_id).label('count')
    ).group_by(TiktokPost.content_type).all()
    
    by_content_type = {row[0] or 'UNKNOWN': row[1] for row in content_type_stats}
    
    # By content status
    content_status_stats = db.query(
        TiktokPost.content_status,
        func.count(TiktokPost.item_id).label('count')
    ).group_by(TiktokPost.content_status).all()
    
    by_content_status = {row[0] or 'UNKNOWN': row[1] for row in content_status_stats}
    
    stats = TiktokContentStats(
        total_posts=totals.total or 0,
        total_views=int(totals.views or 0),
        total_likes=int(totals.likes or 0),
        total_comments=int(totals.comments or 0),
        total_shares=int(totals.shares or 0),
        total_bookmarks=int(totals.bookmarks or 0),
        avg_pfm_score=float(totals.avg_pfm or 0),
        by_content_type=by_content_type,
        by_content_status=by_content_status,
        posts_with_ace=int(totals.posts_with_ace or 0),
        posts_with_abx=int(totals.posts_with_abx or 0),
        total_ace_ads=int(totals.total_ace or 0),
        total_abx_ads=int(totals.total_abx or 0),
    )
    
    return DataResponse(success=True, data=stats.model_dump())


@router.get("/contents", response_model=ListResponse)
def get_tiktok_contents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    # Filters
    content_type: Optional[str] = None,
    content_status: Optional[str] = None,
    products: Optional[str] = None,
    search: Optional[str] = None,
    min_views: Optional[int] = None,
    min_pfm: Optional[float] = None,
    has_ace: Optional[bool] = None,
    has_abx: Optional[bool] = None,
    # Sorting - default to create_time DESC (latest first)
    sort_by: Optional[str] = Query("create_time", description="Sort field: create_time, video_views, pfm_score, likes"),
    sort_dir: Optional[str] = Query("desc", description="Sort direction: asc, desc"),
    db: Session = Depends(get_db)
):
    """Get TikTok contents with filtering and pagination"""
    
    query = db.query(TiktokPost)
    
    # Apply filters
    if content_type:
        query = query.filter(TiktokPost.content_type == content_type)
    
    if content_status:
        query = query.filter(TiktokPost.content_status == content_status)
    
    if products:
        # Search in products field (can be like "[L10]" or "J3")
        query = query.filter(TiktokPost.products.ilike(f"%{products}%"))
    
    if search:
        query = query.filter(
            or_(
                TiktokPost.caption.ilike(f"%{search}%"),
                TiktokPost.item_id.ilike(f"%{search}%"),
            )
        )
    
    if min_views:
        query = query.filter(TiktokPost.video_views >= min_views)
    
    if min_pfm:
        query = query.filter(TiktokPost.pfm_score >= min_pfm)
    
    if has_ace is not None:
        if has_ace:
            query = query.filter(TiktokPost.ace_ad_count > 0)
        else:
            query = query.filter(
                or_(TiktokPost.ace_ad_count == 0, TiktokPost.ace_ad_count.is_(None))
            )
    
    if has_abx is not None:
        if has_abx:
            query = query.filter(TiktokPost.abx_ad_count > 0)
        else:
            query = query.filter(
                or_(TiktokPost.abx_ad_count == 0, TiktokPost.abx_ad_count.is_(None))
            )
    
    # Get total count
    total = query.count()
    
    # Sorting
    sort_column = getattr(TiktokPost, sort_by, TiktokPost.video_views)
    if sort_dir == "asc":
        query = query.order_by(asc(sort_column).nulls_last())
    else:
        query = query.order_by(desc(sort_column).nulls_last())
    
    # Pagination
    offset = (page - 1) * page_size
    posts = query.offset(offset).limit(page_size).all()
    
    # Convert to summary
    items = []
    for post in posts:
        items.append({
            "item_id": post.item_id,
            "url": post.url,
            "caption": post.caption[:200] + "..." if post.caption and len(post.caption) > 200 else post.caption,
            "thumbnail_url": post.thumbnail_url,
            "video_duration": post.video_duration,
            "video_views": post.video_views or 0,
            "likes": post.likes or 0,
            "comments": post.comments or 0,
            "shares": post.shares or 0,
            "bookmarks": post.bookmarks or 0,
            "reach": post.reach or 0,
            "pfm_score": float(post.pfm_score or 0),
            "content_type": post.content_type,
            "content_status": post.content_status,
            "products": post.products,
            "ace_ad_count": post.ace_ad_count or 0,
            "abx_ad_count": post.abx_ad_count or 0,
            "create_time": post.create_time.isoformat() if post.create_time else None,
        })
    
    return ListResponse(
        success=True,
        data=items,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/contents/{item_id}")
def get_tiktok_content_detail(item_id: str, db: Session = Depends(get_db)):
    """Get single TikTok content detail"""
    
    post = db.query(TiktokPost).filter(TiktokPost.item_id == item_id).first()
    
    if not post:
        raise HTTPException(status_code=404, detail="Content not found")
    
    return DataResponse(
        success=True,
        data={
            "item_id": post.item_id,
            "url": post.url,
            "caption": post.caption,
            "thumbnail_url": post.thumbnail_url,
            "video_duration": post.video_duration,
            "video_views": post.video_views or 0,
            "likes": post.likes or 0,
            "comments": post.comments or 0,
            "shares": post.shares or 0,
            "bookmarks": post.bookmarks or 0,
            "reach": post.reach or 0,
            "pfm_score": float(post.pfm_score or 0),
            "content_type": post.content_type,
            "content_status": post.content_status,
            "products": post.products,
            "products_json": post.products_json,
            "ace_ad_count": post.ace_ad_count or 0,
            "abx_ad_count": post.abx_ad_count or 0,
            "ace_details": post.ace_details,
            "abx_details": post.abx_details,
            "ads_details": post.ads_details,
            "ads_total_media_cost": post.ads_total_media_cost,
            "creator_details": post.creator_details,
            "targeting_details": post.targeting_details,
            "total_time_watched": post.total_time_watched,
            "average_time_watched": post.average_time_watched,
            "full_video_watched_rate": post.full_video_watched_rate,
            "boost_factor": float(post.boost_factor or 1),
            "boost_start_date": post.boost_start_date.isoformat() if post.boost_start_date else None,
            "boost_expire_date": post.boost_expire_date.isoformat() if post.boost_expire_date else None,
            "boost_reason": post.boost_reason,
            "content_expire_date": post.content_expire_date.isoformat() if post.content_expire_date else None,
            "create_time": post.create_time.isoformat() if post.create_time else None,
            "update_time": post.update_time.isoformat() if post.update_time else None,
        }
    )


@router.get("/top-contents")
def get_top_tiktok_contents(
    limit: int = Query(10, ge=1, le=50),
    sort_by: Optional[str] = Query("video_views", description="video_views, pfm_score, likes"),
    content_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get top performing TikTok contents"""
    
    query = db.query(TiktokPost)
    
    if content_type:
        query = query.filter(TiktokPost.content_type == content_type)
    
    # Sort by specified field
    sort_column = getattr(TiktokPost, sort_by, TiktokPost.video_views)
    query = query.order_by(desc(sort_column).nulls_last())
    
    posts = query.limit(limit).all()
    
    items = []
    for post in posts:
        items.append({
            "item_id": post.item_id,
            "caption": post.caption[:100] + "..." if post.caption and len(post.caption) > 100 else post.caption,
            "thumbnail_url": post.thumbnail_url,
            "video_views": post.video_views or 0,
            "likes": post.likes or 0,
            "pfm_score": float(post.pfm_score or 0),
            "content_type": post.content_type,
            "products": post.products,
        })
    
    return DataResponse(success=True, data=items)


@router.get("/content-types")
def get_content_types(db: Session = Depends(get_db)):
    """Get list of available content types"""
    
    types = db.query(
        TiktokPost.content_type,
        func.count(TiktokPost.item_id).label('count')
    ).group_by(TiktokPost.content_type).order_by(desc('count')).all()
    
    return DataResponse(
        success=True,
        data=[{"type": t[0], "count": t[1]} for t in types if t[0]]
    )


@router.get("/content-statuses")
def get_content_statuses(db: Session = Depends(get_db)):
    """Get list of available content statuses"""
    
    statuses = db.query(
        TiktokPost.content_status,
        func.count(TiktokPost.item_id).label('count')
    ).group_by(TiktokPost.content_status).order_by(desc('count')).all()
    
    return DataResponse(
        success=True,
        data=[{"status": s[0], "count": s[1]} for s in statuses if s[0]]
    )


@router.get("/products-list")
def get_products_list(db: Session = Depends(get_db)):
    """Get list of products from tiktok_posts"""
    
    products = db.query(
        TiktokPost.products,
        func.count(TiktokPost.item_id).label('count')
    ).filter(
        TiktokPost.products.isnot(None),
        TiktokPost.products != '[]'
    ).group_by(TiktokPost.products).order_by(desc('count')).limit(50).all()
    
    return DataResponse(
        success=True,
        data=[{"products": p[0], "count": p[1]} for p in products]
    )
