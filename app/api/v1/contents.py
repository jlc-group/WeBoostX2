"""
Content API endpoints
"""
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.core.deps import get_db, require_admin
from app.core.config import settings
from app.models import Content
from app.models.enums import Platform, ContentStatus, ContentType
from app.schemas.common import DataResponse, ListResponse
from app.schemas.contents import TikTokImportRequest
from app.services.tiktok_service import TikTokService
from app.models.user import User

router = APIRouter(prefix="/contents", tags=["Contents"])


@router.get("", response_model=ListResponse)
def get_contents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    platform: Optional[str] = None,
    status: Optional[str] = None,
    content_type: Optional[str] = None,
    content_source: Optional[str] = None,
    search: Optional[str] = None,
    creator: Optional[str] = None,
    expiring: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get contents with filtering and pagination"""
    from app.models.enums import ContentSource
    from datetime import datetime, timedelta
    
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
    
    # Filter by content source (influencer, page, staff)
    if content_source:
        try:
            source_enum = ContentSource(content_source.lower())
            query = query.filter(Content.content_source == source_enum)
        except ValueError:
            pass
    
    # Filter by creator name
    if creator:
        query = query.filter(Content.creator_name == creator)
    
    # Filter by expiring soon (within 7 days)
    if expiring == 'soon':
        today = datetime.now().date()
        expire_threshold = today + timedelta(days=7)
        query = query.filter(
            Content.expire_date.isnot(None),
            Content.expire_date <= expire_threshold,
            Content.expire_date >= today
        )
    
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
            "content_source": c.content_source.value if c.content_source else None,
            "status": c.status.value if c.status else None,
            "creator_name": c.creator_name,
            "creator_id": c.creator_id,
            "video_duration": float(c.video_duration) if c.video_duration else 0,
            "avg_watch_time": float(c.avg_watch_time) if c.avg_watch_time else 0,
            "views": c.views,
            "impressions": c.impressions,
            "reach": c.reach,
            "likes": c.likes,
            "comments": c.comments,
            "shares": c.shares,
            "saves": c.saves,
            "completion_rate": float(c.completion_rate) if c.completion_rate else 0,
            "pfm_score": float(c.pfm_score) if c.pfm_score else 0,
            "fb_score": float(c.fb_score) if c.fb_score else 0,
            "unified_score": float(c.unified_score) if c.unified_score else 0,
            "ads_total_cost": float(c.ads_total_cost) if c.ads_total_cost else 0,
            "ads_count": c.ads_count or 0,
            "ace_ad_count": c.ace_ad_count or 0,
            "abx_ad_count": c.abx_ad_count or 0,
            "product_codes": c.product_codes or [],
            "boost_factor": float(c.boost_factor) if c.boost_factor else 1.0,
            "boost_start_date": c.boost_start_date.isoformat() if c.boost_start_date else None,
            "boost_end_date": c.boost_end_date.isoformat() if c.boost_end_date else None,
            "boost_reason": c.boost_reason,
            "employee_id": c.employee_id,
            "influencer_id": c.influencer_id,
            "influencer_cost": float(c.influencer_cost) if c.influencer_cost else None,
            "expire_date": c.expire_date.isoformat() if c.expire_date else None,
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


_TIKTOK_ITEM_ID_RE = re.compile(r"video/(\d+)")
_DIGITS_RE = re.compile(r"^\d+$")


def _extract_item_id(raw: str) -> Optional[str]:
    """ดึง item_id จาก string ที่อาจเป็นทั้งเลขล้วนหรือ TikTok URL"""
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None

    # ถ้าเป็น URL ที่มี /video/1234567890
    m = _TIKTOK_ITEM_ID_RE.search(s)
    if m:
        return m.group(1)

    # ถ้าเป็นเลขล้วน
    if _DIGITS_RE.match(s):
        return s

    return None


@router.post("/import-tiktok", response_model=DataResponse[dict])
def import_tiktok_content(
    payload: TikTokImportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Import TikTok Content เข้าระบบด้วย item_id หรือ URL
    - รับรายการ item_id/URL ทีละบรรทัด
    - ดึง item details จาก API เดิม
    - สร้าง/อัปเดต Content ในตาราง contents
    """

    raw_items = payload.items or []
    item_ids = []

    for raw in raw_items:
        item_id = _extract_item_id(raw)
        if item_id:
            item_ids.append(item_id)

    # unique และตัดค่าว่างออก
    seen = set()
    unique_ids = []
    for i in item_ids:
        if i and i not in seen:
            seen.add(i)
            unique_ids.append(i)

    if not unique_ids:
        return DataResponse(
            success=False,
            message="ไม่พบ TikTok item_id ที่ถูกต้องในรายการที่ส่งมา",
        )

    result = TikTokService.ensure_contents_for_item_ids(unique_ids, db=db)

    msg = (
        f"นำเข้า TikTok content สำเร็จ "
        f"(requested={result.get('requested', 0)}, "
        f"created/updated={result.get('created_or_updated', 0)}, "
        f"failed={result.get('failed', 0)})"
    )

    return DataResponse(
        success=True,
        data=result,
        message=msg,
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
    payload: dict,
    db: Session = Depends(get_db)
):
    """Update content with full data"""
    from app.models.enums import ContentSource
    from datetime import datetime, date as date_type
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    # Update content type
    if "content_type" in payload:
        try:
            content.content_type = ContentType(payload["content_type"].lower())
        except ValueError:
            pass
    
    # Update status
    if "status" in payload:
        try:
            content.status = ContentStatus(payload["status"].lower())
        except ValueError:
            pass
    
    # Update content source
    if "content_source" in payload:
        try:
            content.content_source = ContentSource(payload["content_source"].lower())
        except ValueError:
            pass
    
    # Update product codes
    if "product_codes" in payload:
        content.product_codes = payload["product_codes"]
    
    # Update employee_id
    if "employee_id" in payload:
        content.employee_id = payload["employee_id"] if payload["employee_id"] else None
    
    # Update influencer_cost
    if "influencer_cost" in payload:
        content.influencer_cost = payload["influencer_cost"] if payload["influencer_cost"] else None
    
    # Update expire_date
    if "expire_date" in payload:
        expire_str = payload["expire_date"]
        if expire_str:
            try:
                content.expire_date = datetime.strptime(expire_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        else:
            content.expire_date = None
    
    db.commit()
    
    return DataResponse(
        success=True,
        message="Content updated"
    )


@router.get("/{content_id}/ads")
def get_content_ads(content_id: int, refresh: bool = False, db: Session = Depends(get_db)):
    """Get ads for a specific content. Set refresh=true to fetch real-time data from TikTok API."""
    from app.models import Ad
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    ads_list = []
    total_cost = 0.0
    ace_count = 0
    abx_count = 0
    
    # Parse ads_details from content (handles both dict and list formats)
    ads_details_raw = content.ads_details
    ads_from_details = []
    
    if ads_details_raw:
        # Handle format: {'tiktok': [...]} or {'facebook': [...]}
        if isinstance(ads_details_raw, dict):
            for platform, ads in ads_details_raw.items():
                if isinstance(ads, list):
                    ads_from_details.extend(ads)
        # Handle format: [...]
        elif isinstance(ads_details_raw, list):
            ads_from_details = ads_details_raw
    
    # If refresh requested and we have TikTok ads, fetch real-time data
    if refresh and content.platform.value == 'tiktok' and ads_from_details:
        try:
            from app.services.tiktok_ads_service import TikTokAdsService
            ads_from_details = refresh_tiktok_ads_data(content, ads_from_details, db)
        except Exception as e:
            print(f"Error refreshing TikTok ads: {e}")
    
    # Process ads from details
    for ad_detail in ads_from_details:
        if isinstance(ad_detail, dict):
            # Detect ACE/ABX/General by checking ad_name pattern
            # ACE: created by our system with _ACE_ pattern (1 adgroup = 1 content)
            # ABX: created by our system with _ABX_ pattern (1 adgroup = N contents)
            # General: created directly in TikTok Ads Manager (no pattern)
            ad_name = (ad_detail.get("ad_name") or "").upper()
            campaign_name = (ad_detail.get("campaign_name") or "").upper()
            adgroup_name = (ad_detail.get("adgroup_name") or "").upper()
            
            if "_ABX_" in ad_name or "_ABX_" in campaign_name or "_ABX_" in adgroup_name:
                ad_type = "ABX"
                abx_count += 1
            elif "_ACE_" in ad_name or "_ACE_" in campaign_name or "_ACE_" in adgroup_name:
                ad_type = "ACE"
                ace_count += 1
            else:
                # General: ads created directly in TikTok Ads Manager
                ad_type = "GENERAL"
                # Don't count as ACE or ABX - these are manually created ads
            
            spend = float(ad_detail.get("ad_total_cost") or ad_detail.get("spend") or 0)
            total_cost += spend
            
            ads_list.append({
                "id": ad_detail.get("ad_id") or ad_detail.get("adgroup_id"),
                "ad_id": ad_detail.get("ad_id"),
                "adgroup_id": ad_detail.get("adgroup_id"),
                "campaign_id": ad_detail.get("campaign_id"),
                "type": ad_type,
                "ad_name": ad_detail.get("ad_name"),
                "adgroup_name": ad_detail.get("adgroup_name"),
                "campaign_name": ad_detail.get("campaign_name"),
                "status": ad_detail.get("operation_status") or ad_detail.get("status") or "UNKNOWN",
                "secondary_status": ad_detail.get("secondary_status"),
                "budget": float(ad_detail.get("adgroup_budget") or ad_detail.get("budget") or 0),
                "budget_mode": ad_detail.get("adgroup_budget_mode") or ad_detail.get("budget_mode"),
                "spend": spend,
                "total_cost": spend,
                "advertiser_id": ad_detail.get("advertiser_id"),
                "create_time": ad_detail.get("create_time"),
                "modify_time": ad_detail.get("modify_time"),
            })
    
    # Also check Ad model if we don't have ads from details
    if not ads_list:
        ads = db.query(Ad).filter(Ad.content_id == content_id).all()
        for ad in ads:
            ad_type = "ABX" if ad.ad_type and "abx" in ad.ad_type.lower() else "ACE"
            spend = float(ad.total_spend) if ad.total_spend else 0
            total_cost += spend
            
            if ad_type == "ABX":
                abx_count += 1
            else:
                ace_count += 1
            
            ads_list.append({
                "id": ad.id,
                "ad_id": ad.external_ad_id,
                "type": ad_type,
                "ad_name": ad.name,
                "adgroup_name": ad.name,
                "status": ad.status.value if ad.status else "UNKNOWN",
                "budget": float(ad.daily_budget) if ad.daily_budget else 0,
                "spend": spend,
                "total_cost": spend,
                "advertiser_id": ad.external_ad_account_id,
            })
    
    return DataResponse(
        success=True,
        data=ads_list,
        meta={
            "content_id": content_id,
            "platform_post_id": content.platform_post_id,
            "total_ads": len(ads_list),
            "ace_count": ace_count,
            "abx_count": abx_count,
            "total_cost": total_cost
        }
    )


def refresh_tiktok_ads_data(content, ads_details: list, db: Session) -> list:
    """
    Refresh ads data from TikTok API (similar to old system's get_updated_ads_details)
    
    This function:
    1. Fetches real-time spend data from TikTok Report API
    2. Fetches adgroup budget and status from TikTok AdGroup API
    3. Updates content.ads_details, ads_total_cost, ace_ad_count, abx_ad_count
    """
    from app.services.tiktok_ads_service import TikTokAdsService
    from app.models import ABXAdgroup
    
    if not ads_details:
        return ads_details
    
    # Get ABX adgroup IDs for ACE/ABX classification
    abx_adgroup_ids = set()
    abx_adgroups = db.query(ABXAdgroup.external_adgroup_id).all()
    for row in abx_adgroups:
        if row[0]:
            abx_adgroup_ids.add(row[0])
    
    # Group ads by advertiser_id
    advertiser_ads = {}
    all_ad_ids = []
    all_adgroup_ids = set()
    
    for ad in ads_details:
        advertiser_id = ad.get('advertiser_id')
        adgroup_id = ad.get('adgroup_id')
        ad_id = ad.get('ad_id')
        
        if advertiser_id:
            if advertiser_id not in advertiser_ads:
                advertiser_ads[advertiser_id] = []
            advertiser_ads[advertiser_id].append(ad)
        
        if adgroup_id:
            all_adgroup_ids.add(adgroup_id)
        if ad_id:
            all_ad_ids.append(ad_id)
    
    # Use existing ads_total_cost from DB (synced hourly by cron)
    # Don't reset it to 0!
    total_ad_cost = float(content.ads_total_cost or 0)
    ace_count = 0
    abx_count = 0
    
    # Fetch real-time data from TikTok API for each advertiser
    # Use optimized methods that fetch only specific ad_ids/adgroup_ids (MUCH FASTER!)
    for advertiser_id, ads in advertiser_ads.items():
        if not advertiser_id:
            continue
        
        # Collect unique adgroup_ids for this advertiser only
        adgroup_ids_for_this = list(set(ad.get('adgroup_id') for ad in ads if ad.get('adgroup_id')))
            
        try:
            # 1. Spend data: Use existing value from DB (synced by cron hourly)
            #    TikTok Report API doesn't support filter by ad_id
            ad_spend_map = {}  # Will use existing ad_total_cost from ads_details
            
            # 2. Get adgroup details for SPECIFIC adgroup_ids only (fast! ~1-2 sec)
            #    This gives us real-time budget and status!
            adgroup_map = TikTokAdsService.fetch_adgroup_details(advertiser_id, adgroup_ids_for_this)
            
            # 3. Update each ad with real-time data
            for ad in ads:
                ad_id = ad.get('ad_id')
                adgroup_id = ad.get('adgroup_id')
                
                # Spend: Keep existing value from DB (synced hourly by cron)
                # TikTok Report API doesn't support filter by ad_id
                # Don't recalculate total_ad_cost - use content.ads_total_cost
                old_cost = float(ad.get('ad_total_cost') or ad.get('spend') or 0)
                ad['ad_total_cost'] = old_cost
                
                # Update adgroup info
                if adgroup_id and adgroup_id in adgroup_map:
                    ag_info = adgroup_map[adgroup_id]
                    budget = ag_info.get('budget', 0)
                    # TikTok API returns budget in micro-units (x1,000,000) for some cases
                    if budget and budget > 100000:
                        budget = budget / 1000000
                    ad['adgroup_budget'] = budget
                    ad['adgroup_budget_mode'] = ag_info.get('budget_mode')
                    ad['adgroup_status'] = ag_info.get('operation_status')
                    ad['operation_status'] = ag_info.get('operation_status')
                    ad['secondary_status'] = ag_info.get('secondary_status')
                
                # Classify ACE/ABX/General based on ad_name pattern
                # ACE: ad_name contains "_ACE_" (created by our system, 1 adgroup = 1 content)
                # ABX: ad_name contains "_ABX_" (created by our system, 1 adgroup = N contents)
                # General: no pattern found (created directly in TikTok Ads Manager)
                ad_name = (ad.get('ad_name') or '').upper()
                campaign_name = (ad.get('campaign_name') or '').upper()
                adgroup_name = (ad.get('adgroup_name') or '').upper()
                
                if '_ABX_' in ad_name or '_ABX_' in campaign_name or '_ABX_' in adgroup_name:
                    ad['type'] = 'ABX'
                    abx_count += 1
                elif '_ACE_' in ad_name or '_ACE_' in campaign_name or '_ACE_' in adgroup_name:
                    ad['type'] = 'ACE'
                    ace_count += 1
                else:
                    # General: ads created directly in TikTok Ads Manager (not through our system)
                    ad['type'] = 'GENERAL'
                    # Don't count as ACE or ABX
                    
        except Exception as e:
            print(f"Error fetching data for advertiser {advertiser_id}: {e}")
            # Still classify ads even if API fails - use name-based detection
            for ad in ads:
                ad_name = (ad.get('ad_name') or '').upper()
                campaign_name = (ad.get('campaign_name') or '').upper()
                adgroup_name = (ad.get('adgroup_name') or '').upper()
                
                if '_ABX_' in ad_name or '_ABX_' in campaign_name or '_ABX_' in adgroup_name:
                    ad['type'] = 'ABX'
                    abx_count += 1
                elif '_ACE_' in ad_name or '_ACE_' in campaign_name or '_ACE_' in adgroup_name:
                    ad['type'] = 'ACE'
                    ace_count += 1
                else:
                    ad['type'] = 'GENERAL'
    
    # Update content in database
    # Keep existing ads_total_cost from DB (synced hourly by cron)
    # Only update counts, details, and adgroup info (budget, status)
    content.ads_count = len(ads_details)
    content.ace_ad_count = ace_count
    content.abx_ad_count = abx_count
    content.ace_details = [ad for ad in ads_details if ad.get('type') == 'ACE'] or None
    content.abx_details = [ad for ad in ads_details if ad.get('type') == 'ABX'] or None
    
    # Update ads_details in database
    platform_key = content.platform.value.lower()
    content.ads_details = {platform_key: ads_details}
    db.commit()
    
    print(f"[refresh_tiktok_ads_data] Updated content {content.id}: "
          f"total_cost={total_ad_cost:.2f} (from DB), ads={len(ads_details)}, "
          f"ACE={ace_count}, ABX={abx_count}")
    
    return ads_details


@router.post("/{content_id}/boost")
def set_content_boost(content_id: int, payload: dict, db: Session = Depends(get_db)):
    """Set boost for content"""
    from datetime import datetime, timedelta
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    boost_factor = payload.get("boost_factor", 1.5)
    boost_duration = payload.get("boost_duration", 7)  # days
    boost_reason = payload.get("boost_reason", "")
    
    # Calculate dates
    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=boost_duration)
    
    content.boost_factor = boost_factor
    content.boost_start_date = start_date
    content.boost_end_date = end_date
    content.boost_reason = boost_reason
    
    db.commit()
    
    return DataResponse(
        success=True,
        message=f"Boost set to {boost_factor}x for {boost_duration} days",
        data={
            "boost_factor": boost_factor,
            "boost_start_date": start_date.isoformat(),
            "boost_end_date": end_date.isoformat()
        }
    )


@router.delete("/{content_id}/boost")
def remove_content_boost(content_id: int, db: Session = Depends(get_db)):
    """Remove boost from content"""
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    content.boost_factor = 1.0
    content.boost_start_date = None
    content.boost_end_date = None
    content.boost_reason = None
    
    db.commit()
    
    return DataResponse(
        success=True,
        message="Boost removed"
    )


@router.post("/bulk-update")
def bulk_update_contents(payload: dict, db: Session = Depends(get_db)):
    """Bulk update multiple contents"""
    from datetime import datetime
    from app.models.enums import ContentSource
    
    ids = payload.get("ids", [])
    updates = payload.get("updates", {})
    
    if not ids:
        raise HTTPException(status_code=400, detail="No content IDs provided")
    
    # Get contents
    contents = db.query(Content).filter(
        Content.id.in_(ids),
        Content.deleted_at.is_(None)
    ).all()
    
    updated_count = 0
    
    for content in contents:
        # Update content type
        if "content_type" in updates:
            try:
                content.content_type = ContentType(updates["content_type"].lower())
            except ValueError:
                pass
        
        # Update status
        if "status" in updates:
            try:
                content.status = ContentStatus(updates["status"].lower())
            except ValueError:
                pass
        
        # Update expire_date
        if "expire_date" in updates:
            expire_str = updates["expire_date"]
            if expire_str:
                try:
                    content.expire_date = datetime.strptime(expire_str, "%Y-%m-%d").date()
                except ValueError:
                    pass
            else:
                content.expire_date = None
        
        updated_count += 1
    
    db.commit()
    
    return DataResponse(
        success=True,
        data={"updated": updated_count},
        message=f"Updated {updated_count} contents"
    )


# ============================================
# AdGroup Control APIs
# ============================================

@router.post("/{content_id}/ads/{adgroup_id}/status")
def update_adgroup_status(
    content_id: int,
    adgroup_id: str,
    payload: dict,
    db: Session = Depends(get_db)
):
    """
    Update AdGroup status via TikTok API
    
    Body:
    {
        "status": "ENABLE" | "DISABLE",
        "advertiser_id": "7221065902056292354"
    }
    """
    from app.services.tiktok_ads_service import TikTokAdsService
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    status = payload.get("status")
    advertiser_id = payload.get("advertiser_id")
    
    if not status or status not in ["ENABLE", "DISABLE"]:
        raise HTTPException(status_code=400, detail="Invalid status. Use 'ENABLE' or 'DISABLE'")
    
    if not advertiser_id:
        raise HTTPException(status_code=400, detail="Missing advertiser_id")
    
    # Call TikTok API
    result = TikTokAdsService.update_adgroup_status(advertiser_id, [adgroup_id], status)
    
    if result.get("success"):
        # Update local database
        _update_adgroup_in_content(content, adgroup_id, {"operation_status": status, "adgroup_status": status}, db)
        
        return DataResponse(
            success=True,
            message=f"AdGroup status updated to {status}",
            data={"adgroup_id": adgroup_id, "status": status}
        )
    else:
        return DataResponse(
            success=False,
            message=result.get("message", "Failed to update status"),
            data=result
        )


@router.post("/{content_id}/ads/{adgroup_id}/budget")
def update_adgroup_budget_api(
    content_id: int,
    adgroup_id: str,
    payload: dict,
    db: Session = Depends(get_db)
):
    """
    Update AdGroup budget via TikTok API
    
    Body:
    {
        "budget": 5000,
        "advertiser_id": "7221065902056292354"
    }
    """
    from app.services.tiktok_ads_service import TikTokAdsService
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    budget = payload.get("budget")
    advertiser_id = payload.get("advertiser_id")
    
    if budget is None or budget < 0:
        raise HTTPException(status_code=400, detail="Invalid budget. Must be a positive number")
    
    if not advertiser_id:
        raise HTTPException(status_code=400, detail="Missing advertiser_id")
    
    # Call TikTok API
    result = TikTokAdsService.update_adgroup_budget(advertiser_id, adgroup_id, float(budget))
    
    if result.get("success"):
        # Update local database
        _update_adgroup_in_content(content, adgroup_id, {"adgroup_budget": budget}, db)
        
        return DataResponse(
            success=True,
            message=f"AdGroup budget updated to ฿{budget:,.0f}",
            data={"adgroup_id": adgroup_id, "budget": budget}
        )
    else:
        return DataResponse(
            success=False,
            message=result.get("message", "Failed to update budget"),
            data=result
        )


@router.post("/{content_id}/ads/{adgroup_id}/update")
def update_adgroup_budget_and_status(
    content_id: int,
    adgroup_id: str,
    payload: dict,
    db: Session = Depends(get_db)
):
    """
    Update AdGroup budget AND status via TikTok API
    
    Body:
    {
        "budget": 5000,  (optional)
        "status": "ENABLE" | "DISABLE",  (optional)
        "advertiser_id": "7221065902056292354"
    }
    """
    from app.services.tiktok_ads_service import TikTokAdsService
    
    content = db.query(Content).filter(
        Content.id == content_id,
        Content.deleted_at.is_(None)
    ).first()
    
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    budget = payload.get("budget")
    status = payload.get("status")
    advertiser_id = payload.get("advertiser_id")
    
    if not advertiser_id:
        raise HTTPException(status_code=400, detail="Missing advertiser_id")
    
    if budget is None and status is None:
        raise HTTPException(status_code=400, detail="Provide at least budget or status to update")
    
    if status and status not in ["ENABLE", "DISABLE"]:
        raise HTTPException(status_code=400, detail="Invalid status. Use 'ENABLE' or 'DISABLE'")
    
    # Call TikTok API
    result = TikTokAdsService.update_adgroup_budget_and_status(
        advertiser_id,
        adgroup_id,
        budget=float(budget) if budget is not None else None,
        status=status
    )
    
    if result.get("success"):
        # Update local database
        updates = {}
        if budget is not None:
            updates["adgroup_budget"] = budget
        if status:
            updates["operation_status"] = status
            updates["adgroup_status"] = status
        
        _update_adgroup_in_content(content, adgroup_id, updates, db)
        
        message_parts = []
        if budget is not None:
            message_parts.append(f"Budget: ฿{budget:,.0f}")
        if status:
            message_parts.append(f"Status: {status}")
        
        return DataResponse(
            success=True,
            message=f"AdGroup updated - {', '.join(message_parts)}",
            data={"adgroup_id": adgroup_id, "budget": budget, "status": status}
        )
    else:
        return DataResponse(
            success=False,
            message="Failed to update adgroup",
            data=result
        )


def _update_adgroup_in_content(content: Content, adgroup_id: str, updates: dict, db: Session):
    """Helper function to update adgroup info in content.ads_details"""
    if not content.ads_details:
        return
    
    platform_key = content.platform.value.lower()
    ads_list = content.ads_details.get(platform_key, [])
    
    for ad in ads_list:
        if ad.get("adgroup_id") == adgroup_id:
            ad.update(updates)
    
    # Update ace_details and abx_details too
    if content.ace_details:
        for ad in content.ace_details:
            if ad.get("adgroup_id") == adgroup_id:
                ad.update(updates)
    
    if content.abx_details:
        for ad in content.abx_details:
            if ad.get("adgroup_id") == adgroup_id:
                ad.update(updates)
    
    # Recalculate ads_total_cost if budget was updated
    total_cost = 0
    for ad in ads_list:
        spend = ad.get("ad_total_cost") or ad.get("spend") or 0
        if isinstance(spend, (int, float)):
            total_cost += spend
    
    content.ads_total_cost = total_cost
    content.ads_details = {platform_key: ads_list}
    db.commit()

