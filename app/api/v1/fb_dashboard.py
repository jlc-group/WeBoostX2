"""
Facebook Dashboard API - Read from Legacy Database

API endpoints for Facebook Dashboard that read from existing
localhost:5433/postgres database.

READ-ONLY - No modifications to legacy data.
"""
from fastapi import APIRouter, Query, HTTPException, Response
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
import traceback
import re

from app.services.facebook.fb_legacy_mapper import get_legacy_mapper

router = APIRouter(prefix="/fb-dashboard", tags=["Facebook Dashboard"])


# ========================================
# Helper Functions
# ========================================

def extract_cpr_by_objective(cpr_breakdown, objective: str) -> dict:
    """
    Extract CPR data for a specific objective from cpr_breakdown
    
    Args:
        cpr_breakdown: dict with OUTCOME_AWARENESS, OUTCOME_ENGAGEMENT keys
        objective: 'OUTCOME_AWARENESS' or 'OUTCOME_ENGAGEMENT'
    
    Returns:
        dict with spend, results, cpr or None
    """
    if not cpr_breakdown or objective not in cpr_breakdown:
        return None
    
    obj_data = cpr_breakdown[objective]
    total_spend = obj_data.get('total_spend', 0) or 0
    total_results = obj_data.get('total_results', 0) or 0
    
    # Calculate CPR: spend / results
    cpr = total_spend / total_results if total_results > 0 else 0
    
    return {
        'spend': float(total_spend),
        'results': int(total_results),
        'cpr': round(cpr, 2)
    }


# ========================================
# Response Models
# ========================================

class DashboardSummary(BaseModel):
    pages_count: int
    posts_count: int
    videos_count: int
    campaigns_count: int
    adsets_count: int
    ads_count: int
    total_spend: float
    products_count: int


class PageInfo(BaseModel):
    id: str
    name: str
    category: Optional[str]
    likes: Optional[int]
    followers_count: Optional[int]
    picture_url: Optional[str]


class PostInfo(BaseModel):
    id: str
    page_id: str
    message: Optional[str]
    type: Optional[str]
    permalink_url: Optional[str]
    picture_url: Optional[str]
    created_time: Optional[datetime]
    # Performance
    views: Optional[int]
    likes: Optional[int]
    comments: Optional[int]
    shares: Optional[int]
    performance_score: Optional[float]
    ads_total_cost: Optional[float]


class CampaignInfo(BaseModel):
    campaign_id: str
    name: str
    status: Optional[str]
    objective: Optional[str]
    daily_budget: Optional[float]
    adsets_count: Optional[int]
    ads_count: Optional[int]
    total_spend: Optional[float]
    total_impressions: Optional[int]
    total_clicks: Optional[int]


# ========================================
# Endpoints
# ========================================

@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary():
    """
    Get dashboard summary stats
    
    Returns counts and totals for all Facebook data.
    """
    try:
        mapper = get_legacy_mapper()
        summary = mapper.get_dashboard_summary()
        return DashboardSummary(**summary)
    except Exception as e:
        error_detail = f"Database error: {str(e)}\n{traceback.format_exc()}"
        print(f"[FB-DASHBOARD ERROR] /summary: {error_detail}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages")
def get_pages():
    """
    Get all Facebook pages
    """
    try:
        mapper = get_legacy_mapper()
        pages = mapper.get_pages()
        return {"data": pages, "total": len(pages)}
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /pages: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/posts")
def get_posts(
    page_id: Optional[str] = Query(None, description="Filter by page ID"),
    post_type: Optional[str] = Query(None, description="Filter by post type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get Facebook posts with performance data
    
    Returns posts mapped to WeBoostX Content format.
    """
    try:
        mapper = get_legacy_mapper()
        posts = mapper.get_posts(
            page_id=page_id,
            post_type=post_type,
            limit=limit,
            offset=offset
        )
        total = mapper.get_posts_count(page_id=page_id)
        return {
            "data": posts,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /posts: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# IMPORTANT: These specific routes MUST come BEFORE /posts/{post_id}
# Otherwise FastAPI will match "top" and "recent" as post_id values

@router.get("/posts/top/performance")
def get_top_posts(
    limit: int = Query(10, ge=1, le=100)
):
    """
    Get top performing posts by performance score
    """
    try:
        mapper = get_legacy_mapper()
        posts = mapper.get_top_posts_by_performance(limit=limit)
        return {"data": posts, "total": len(posts)}
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /posts/top/performance: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/posts/recent")
def get_recent_posts(
    limit: int = Query(20, ge=1, le=100)
):
    """
    Get most recent posts
    """
    try:
        mapper = get_legacy_mapper()
        posts = mapper.get_recent_posts(limit=limit)
        return {"data": posts, "total": len(posts)}
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /posts/recent: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# Generic post_id route AFTER the specific routes above
@router.get("/posts/{post_id}")
def get_post_detail(post_id: str):
    """
    Get single post with all details and insights
    """
    try:
        mapper = get_legacy_mapper()
        post = mapper.get_post_by_id(post_id)
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")
        
        insights = mapper.get_post_insights(post_id)
        
        return {
            "post": post,
            "insights": insights
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /posts/{post_id}: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/videos")
def get_videos(
    page_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get Facebook video posts with insights
    """
    try:
        mapper = get_legacy_mapper()
        videos = mapper.get_video_posts(
            page_id=page_id,
            limit=limit,
            offset=offset
        )
        return {
            "data": videos,
            "total": len(videos),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /videos: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/campaigns")
def get_campaigns(
    account_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get Facebook campaigns
    """
    try:
        mapper = get_legacy_mapper()
        campaigns = mapper.get_campaigns(
            account_id=account_id,
            status=status,
            limit=limit,
            offset=offset
        )
        total = mapper.get_campaigns_count(account_id=account_id)
        return {
            "data": campaigns,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /campaigns: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/campaigns/performance")
def get_campaigns_performance():
    """
    Get campaigns with aggregated performance metrics
    """
    try:
        mapper = get_legacy_mapper()
        campaigns = mapper.get_campaigns_performance()
        return {"data": campaigns, "total": len(campaigns)}
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /campaigns/performance: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/adsets")
def get_adsets(
    campaign_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get Facebook adsets
    """
    try:
        mapper = get_legacy_mapper()
        adsets = mapper.get_adsets(
            campaign_id=campaign_id,
            limit=limit,
            offset=offset
        )
        total = mapper.get_adsets_count(campaign_id=campaign_id)
        return {
            "data": adsets,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /adsets: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/ads")
def get_ads(
    adset_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """
    Get Facebook ads
    """
    try:
        mapper = get_legacy_mapper()
        ads = mapper.get_ads(
            adset_id=adset_id,
            limit=limit,
            offset=offset
        )
        total = mapper.get_ads_count(adset_id=adset_id)
        return {
            "data": ads,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /ads: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/ad-accounts")
def get_ad_accounts():
    """
    Get all Facebook ad accounts
    """
    try:
        mapper = get_legacy_mapper()
        accounts = mapper.get_ad_accounts()
        return {"data": accounts, "total": len(accounts)}
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /ad-accounts: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/ads-insights")
def get_ads_insights(
    ad_id: Optional[str] = Query(None),
    date_start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_end: Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(1000, ge=1, le=10000),
):
    """
    Get ads performance insights
    """
    try:
        mapper = get_legacy_mapper()
        insights = mapper.get_ads_insights(
            ad_id=ad_id,
            date_start=date_start,
            date_end=date_end,
            limit=limit
        )
        return {"data": insights, "total": len(insights)}
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /ads-insights: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# ========================================
# Content-style endpoints for /contents/facebook page
# ========================================

# IMPORTANT: /contents/stats MUST come BEFORE /contents to avoid path matching issues
@router.get("/contents/stats")
def get_fb_contents_stats():
    """
    Get summary statistics for Facebook contents page
    """
    try:
        mapper = get_legacy_mapper()
        
        # Get aggregate stats
        stats = mapper.db.query_one("""
            SELECT 
                COUNT(*) as total_posts,
                COALESCE(SUM(impressions), 0) as total_impressions,
                COALESCE(SUM(reach), 0) as total_reach,
                COALESCE(SUM(video_views), 0) as total_views,
                COALESCE(SUM(likes), 0) as total_likes,
                AVG(CASE WHEN pfm_score > 0 THEN pfm_score END) as average_fb_score
            FROM facebook_posts_performance
        """)
        
        return {
            "total_posts": stats['total_posts'] if stats else 0,
            "total_impressions": int(stats['total_impressions']) if stats else 0,
            "total_reach": int(stats['total_reach']) if stats else 0,
            "total_views": int(stats['total_views']) if stats else 0,
            "total_likes": int(stats['total_likes']) if stats else 0,
            "average_fb_score": float(stats['average_fb_score']) if stats and stats['average_fb_score'] else None
        }
        
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /contents/stats: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@router.get("/contents")
def get_fb_contents(
    search: Optional[str] = Query(None),
    post_type: Optional[str] = Query(None),
    sort: Optional[str] = Query("newest"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """
    Get Facebook posts with performance - formatted for Contents page
    
    Includes: thumbnail, metrics, post_saves, cost_per_result
    """
    try:
        mapper = get_legacy_mapper()
        
        # Simple query first, then process thumbnails in Python
        # Join media_storage twice: once by local_thumbnail_id, once by source_post_id as fallback
        sql = """
            SELECT 
                pp.id,
                pp.post_id as platform_post_id,
                pp.url,
                pp.caption,
                pp.thumbnail_url as pp_thumbnail,
                pp.local_thumbnail_id,
                pp.post_type,
                pp.video_views as views,
                pp.impressions,
                pp.reach,
                pp.likes,
                pp.comments,
                pp.shares,
                pp.total_post_saves as saves,
                pp.pfm_score as fb_score,
                pp.engagement_rate,
                pp.ads_total_media_cost as ads_total_cost,
                pp.ads_avg_cost_per_result as cost_per_result,
                pp.ads_count,
                pp.ads_details,
                pp.ads_cost_per_result_breakdown as cpr_breakdown,
                COALESCE(p.created_time, pp.create_time) as platform_created_at,
                pp.create_time as pp_create_time,
                p.picture_url as p_picture,
                p.full_picture_url as p_full_picture,
                pg.name as page_name,
                ms.original_url as ms_original_url,
                ms.is_stored_in_db as ms_stored_in_db,
                ms.id as ms_id,
                ms2.id as ms2_id,
                ms2.original_url as ms2_original_url,
                ms2.is_stored_in_db as ms2_stored_in_db
            FROM facebook_posts_performance pp
            LEFT JOIN facebook_posts p ON pp.post_id = p.id
            LEFT JOIN facebook_pages pg ON pp.channel_acc_id = pg.id
            LEFT JOIN media_storage ms ON pp.local_thumbnail_id = ms.id
            LEFT JOIN LATERAL (
                SELECT id, original_url, is_stored_in_db 
                FROM media_storage 
                WHERE source_post_id = pp.post_id 
                AND is_stored_in_db = TRUE
                ORDER BY created_at DESC
                LIMIT 1
            ) ms2 ON TRUE
            WHERE 1=1
        """
        params = []
        
        if search:
            sql += " AND (pp.caption ILIKE %s OR pp.post_id ILIKE %s)"
            params.extend([f"%{search}%", f"%{search}%"])
        
        if post_type:
            sql += " AND pp.post_type = %s"
            params.append(post_type)
        
        # Sort order - use COALESCE to handle posts without p.created_time (like reels)
        if sort == "impressions":
            sql += " ORDER BY pp.impressions DESC NULLS LAST"
        elif sort == "reach":
            sql += " ORDER BY pp.reach DESC NULLS LAST"
        elif sort == "engagement":
            sql += " ORDER BY pp.engagement_rate DESC NULLS LAST"
        else:  # newest - use COALESCE to include reels with pp.create_time
            sql += " ORDER BY COALESCE(p.created_time, pp.create_time) DESC NULLS LAST"
        
        sql += " LIMIT %s OFFSET %s"
        params.extend([limit, skip])
        
        results = mapper.db.query(sql, tuple(params) if params else None)
        
        # Process results to pick best thumbnail
        processed = []
        for row in results:
            # Determine best thumbnail URL with priority:
            # 1. Direct CDN URL (https://)
            # 2. localhost:8000/media/<uuid> -> transform to our endpoint
            # 3. media_storage.original_url (CDN)
            # 4. facebook_posts picture URLs
            thumbnail_url = None
            pp_thumb = row.get('pp_thumbnail')
            
            if pp_thumb:
                if pp_thumb.startswith('https://'):
                    # Direct Facebook CDN URL - use as is
                    thumbnail_url = pp_thumb
                elif 'localhost:8000/media/' in pp_thumb:
                    # Legacy media server URL - extract UUID and use our endpoint
                    match = re.search(r'/media/([a-f0-9\-]{36})', pp_thumb)
                    if match:
                        media_uuid = match.group(1)
                        thumbnail_url = f"/api/v1/fb-dashboard/media/{media_uuid}"
                elif pp_thumb.startswith('http://localhost'):
                    # Other localhost URL - try to extract media ID
                    match = re.search(r'/media/([a-f0-9\-]{36})', pp_thumb)
                    if match:
                        media_uuid = match.group(1)
                        thumbnail_url = f"/api/v1/fb-dashboard/media/{media_uuid}"
            
            # Fallbacks if no thumbnail yet
            if not thumbnail_url:
                # Try media_storage via local_thumbnail_id
                if row.get('local_thumbnail_id') and row.get('ms_stored_in_db'):
                    thumbnail_url = f"/api/v1/fb-dashboard/media/{row['local_thumbnail_id']}"
                # Try media_storage via source_post_id (ms2)
                elif row.get('ms2_id') and row.get('ms2_stored_in_db'):
                    thumbnail_url = f"/api/v1/fb-dashboard/media/{row['ms2_id']}"
                elif row.get('ms_original_url') and row['ms_original_url'].startswith('https://'):
                    thumbnail_url = row['ms_original_url']
                elif row.get('ms2_original_url') and row['ms2_original_url'].startswith('https://'):
                    thumbnail_url = row['ms2_original_url']
                elif row.get('p_full_picture') and row['p_full_picture'].startswith('https://'):
                    thumbnail_url = row['p_full_picture']
                elif row.get('p_picture') and row['p_picture'].startswith('https://'):
                    thumbnail_url = row['p_picture']
            
            processed.append({
                'id': row['id'],
                'platform_post_id': row['platform_post_id'],
                'url': row['url'],
                'caption': row['caption'],
                'thumbnail_url': thumbnail_url,
                'post_type': row['post_type'],
                'views': row['views'] or 0,
                'impressions': row['impressions'] or 0,
                'reach': row['reach'] or 0,
                'likes': row['likes'] or 0,
                'comments': row['comments'] or 0,
                'shares': row['shares'] or 0,
                'saves': row['saves'] or 0,
                'fb_score': float(row['fb_score']) if row['fb_score'] else None,
                'engagement_rate': float(row['engagement_rate']) if row['engagement_rate'] else None,
                'ads_total_cost': float(row['ads_total_cost']) if row['ads_total_cost'] else 0,
                'cost_per_result': float(row['cost_per_result']) if row['cost_per_result'] else None,
                'ads_count': row['ads_count'] or 0,
                'ads_details': row['ads_details'] if row.get('ads_details') else None,
                'cpr_breakdown': row.get('cpr_breakdown'),
                # Extract CPR by objective
                'cpr_aw': extract_cpr_by_objective(row.get('cpr_breakdown'), 'OUTCOME_AWARENESS'),
                'cpr_eg': extract_cpr_by_objective(row.get('cpr_breakdown'), 'OUTCOME_ENGAGEMENT'),
                'platform_created_at': row['platform_created_at'].isoformat() if row['platform_created_at'] else None,
                'page_name': row['page_name'],
            })
        
        return processed
        
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /contents: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# ========================================
# Post Ads Insights endpoint
# ========================================

@router.get("/posts/{post_id}/ads")
def get_post_ads_insights(post_id: str):
    """
    Get detailed ads insights for a specific post
    
    Returns:
    - ads_summary: total cost, total reach, total clicks
    - ads: list of ads with their insights
    """
    try:
        mapper = get_legacy_mapper()
        
        # Get ads_details from facebook_posts_performance
        post_data = mapper.db.query_one("""
            SELECT 
                pp.post_id,
                pp.caption,
                pp.ads_count,
                pp.ads_details,
                pp.ads_total_media_cost,
                pp.ads_avg_cost_per_result,
                pp.ads_cost_per_result_breakdown
            FROM facebook_posts_performance pp
            WHERE pp.post_id = %s
        """, (post_id,))
        
        if not post_data:
            raise HTTPException(status_code=404, detail="Post not found")
        
        # Get detailed insights from facebook_ads_insights for each ad
        ads_details = post_data.get('ads_details') or []
        
        # Extract ad_ids from ads_details
        ad_ids = [ad.get('ad_id') for ad in ads_details if ad.get('ad_id')]
        
        detailed_insights = []
        if ad_ids:
            # Get latest insights for each ad
            placeholders = ','.join(['%s'] * len(ad_ids))
            insights_data = mapper.db.query(f"""
                SELECT DISTINCT ON (ai.ad_id)
                    ai.ad_id,
                    ai.impressions,
                    ai.reach,
                    ai.clicks,
                    ai.spend,
                    ai.cpm,
                    ai.cpp,
                    ai.ctr,
                    ai.frequency,
                    ai.cost_per_result,
                    ai.actions,
                    ai.video_play_actions,
                    ai.date_start,
                    ai.date_stop,
                    a.name as ad_name,
                    a.status as ad_status,
                    a.preview_url
                FROM facebook_ads_insights ai
                LEFT JOIN facebook_ads a ON ai.ad_id = a.ad_id
                WHERE ai.ad_id IN ({placeholders})
                ORDER BY ai.ad_id, ai.date_stop DESC NULLS LAST
            """, tuple(ad_ids))
            
            for insight in insights_data:
                detailed_insights.append({
                    'ad_id': insight['ad_id'],
                    'ad_name': insight.get('ad_name'),
                    'ad_status': insight.get('ad_status'),
                    'preview_url': insight.get('preview_url'),
                    'impressions': insight.get('impressions') or 0,
                    'reach': insight.get('reach') or 0,
                    'clicks': insight.get('clicks') or 0,
                    'spend': float(insight['spend']) if insight.get('spend') else 0,
                    'cpm': float(insight['cpm']) if insight.get('cpm') else 0,
                    'cpp': float(insight['cpp']) if insight.get('cpp') else 0,
                    'ctr': float(insight['ctr']) if insight.get('ctr') else 0,
                    'frequency': float(insight['frequency']) if insight.get('frequency') else 0,
                    'cost_per_result': float(insight['cost_per_result']) if insight.get('cost_per_result') else None,
                    'actions': insight.get('actions'),
                    'video_play_actions': insight.get('video_play_actions'),
                    'date_range': f"{insight.get('date_start')} - {insight.get('date_stop')}" if insight.get('date_start') else None
                })
        
        return {
            'post_id': post_id,
            'caption': (post_data.get('caption') or '')[:100] + '...' if post_data.get('caption') else None,
            'ads_count': post_data.get('ads_count') or 0,
            'total_spend': float(post_data['ads_total_media_cost']) if post_data.get('ads_total_media_cost') else 0,
            'avg_cost_per_result': float(post_data['ads_avg_cost_per_result']) if post_data.get('ads_avg_cost_per_result') else None,
            'ads_summary': ads_details,  # Quick summary from cached data
            'ads_insights': detailed_insights,  # Detailed insights from facebook_ads_insights
            'cpr_breakdown': post_data.get('ads_cost_per_result_breakdown')
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /posts/{post_id}/ads: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# ========================================
# Media Serving endpoint
# ========================================

@router.get("/media/{media_id}")
def get_media(media_id: str):
    """
    Serve media file from database (binary data from media_storage.file_data)
    
    This replaces the need for localhost:8000/media/* URLs
    """
    try:
        mapper = get_legacy_mapper()
        
        # Get media binary data from media_storage
        result = mapper.db.query_one("""
            SELECT file_data, content_type, file_size, original_url
            FROM media_storage 
            WHERE id = %s 
            AND is_stored_in_db = TRUE 
            AND download_status = 'success'
        """, (media_id,))
        
        if not result:
            raise HTTPException(status_code=404, detail="Media not found")
        
        file_data = result.get('file_data')
        content_type = result.get('content_type') or 'image/jpeg'
        
        if not file_data:
            raise HTTPException(status_code=404, detail="Media binary data not found")
        
        # Convert memoryview to bytes if needed
        if isinstance(file_data, memoryview):
            file_data = bytes(file_data)
        
        # Return binary response with proper headers
        return Response(
            content=file_data,
            media_type=content_type,
            headers={
                "Content-Length": str(len(file_data)),
                "Cache-Control": "public, max-age=31536000",  # Cache 1 year
                "X-Media-ID": media_id,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[FB-DASHBOARD ERROR] /media/{media_id}: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error retrieving media: {str(e)}")
