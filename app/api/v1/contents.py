"""
Content API endpoints
"""
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_db, require_admin
from app.models import Content, ContentStaffAllocation
from app.models.enums import ContentStaffRole, ContentStatus, ContentType, Platform
from app.models.user import User
from app.schemas.common import DataResponse, ListResponse
from app.schemas.contents import TikTokImportRequest
from app.services.naming_service import NamingService
from app.services.thumbnail_service import process_content_thumbnail
from app.services.tiktok_service import TikTokService
from app.tasks import sync_tasks

router = APIRouter(prefix="/contents", tags=["Contents"])


@router.get("", response_model=ListResponse)
def get_contents(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    platform: Optional[str] = None,
    status: Optional[str] = None,
    content_type: Optional[str] = None,
    content_source: Optional[str] = None,
    content_tag: Optional[str] = None,  # Filter by content tag
    staff_id: Optional[int] = None,  # Filter by staff (employee) ID
    search: Optional[str] = None,
    creator: Optional[str] = None,
    expiring: Optional[str] = None,
    products: Optional[str] = None,  # Comma-separated product codes
    # Advanced filters for shortcuts
    sort_by: Optional[str] = None,  # pfm_score, views, platform_created_at
    sort_dir: Optional[str] = "desc",  # asc, desc
    min_pfm: Optional[float] = None,  # Minimum PFM score
    min_views: Optional[int] = None,  # Minimum views
    boosted: Optional[bool] = None,  # Has boost_factor > 1
    need_attention: Optional[bool] = None,  # Missing products or content_type
    no_targeting: Optional[bool] = None,  # No targeting template
    has_ads: Optional[str] = None,  # "yes" for active ads, "no" for no ads
    db: Session = Depends(get_db)
):
    """Get contents with filtering and pagination"""
    from datetime import datetime, timedelta

    from app.models.enums import ContentSource

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

    # Filter by content tag
    if content_tag:
        from sqlalchemy import cast, func
        from sqlalchemy.dialects.postgresql import JSONB
        # Filter contents that have this tag in their content_tags JSON array
        query = query.filter(
            cast(Content.content_tags, JSONB).contains([content_tag])
        )

    # Filter by staff (employee) ID
    if staff_id:
        from app.models.content import ContentStaffAllocation
        # Find contents that have this employee assigned
        query = query.filter(
            Content.id.in_(
                db.query(ContentStaffAllocation.content_id)
                .filter(
                    ContentStaffAllocation.employee_id == staff_id,
                    ContentStaffAllocation.deleted_at.is_(None)
                )
            )
        )

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

    # Filter by product codes (exact match - same products, same count)
    if products:
        product_list = sorted([p.strip() for p in products.split(',') if p.strip()])
        if product_list:
            from sqlalchemy import String, cast, func
            from sqlalchemy.dialects.postgresql import ARRAY, JSONB
            # Exact match: content must have exactly these products (no more, no less)
            # Compare sorted JSON arrays
            query = query.filter(
                cast(Content.product_codes, JSONB) == cast(product_list, JSONB)
            )

    # Advanced filters for shortcuts
    if min_pfm is not None:
        query = query.filter(Content.pfm_score >= min_pfm)

    if min_views is not None:
        query = query.filter(Content.views >= min_views)

    if boosted:
        query = query.filter(Content.boost_factor > 1)

    if need_attention:
        # Content that needs attention: missing products OR missing content_type
        query = query.filter(
            or_(
                Content.product_codes.is_(None),
                Content.product_codes == [],
                Content.content_type.is_(None),
                Content.content_type == ContentType.OTHER
            )
        )

    if no_targeting:
        # Content without targeting template
        query = query.filter(
            or_(
                Content.preferred_targeting_ids.is_(None),
                Content.preferred_targeting_ids == []
            )
        )

    if has_ads == "yes":
        query = query.filter(Content.ads_count > 0)
    elif has_ads == "no":
        query = query.filter(or_(Content.ads_count.is_(None), Content.ads_count == 0))

    # Get total count
    total = query.count()

    # Determine sort order
    sort_order = None
    if sort_by == "pfm_score":
        sort_order = Content.pfm_score.desc().nullslast() if sort_dir == "desc" else Content.pfm_score.asc().nullsfirst()
    elif sort_by == "views":
        sort_order = Content.views.desc().nullslast() if sort_dir == "desc" else Content.views.asc().nullsfirst()
    elif sort_by == "platform_created_at":
        sort_order = Content.platform_created_at.desc().nullslast() if sort_dir == "desc" else Content.platform_created_at.asc().nullsfirst()
    elif sort_by == "ads_total_cost":
        sort_order = Content.ads_total_cost.desc().nullslast() if sort_dir == "desc" else Content.ads_total_cost.asc().nullsfirst()
    else:
        # Default sort by platform_created_at DESC
        sort_order = Content.platform_created_at.desc().nullslast()

    # Apply pagination and ordering
    # Eager load staff_allocations for better performance
    from sqlalchemy.orm import joinedload
    contents = query.options(joinedload(Content.staff_allocations))\
        .order_by(sort_order)\
        .offset((page - 1) * page_size)\
        .limit(page_size)\
        .all()

    # Build targeting template lookup for displaying names
    from app.models.platform import TargetingTemplate
    all_targeting_ids = set()
    for c in contents:
        if c.preferred_targeting_ids:
            all_targeting_ids.update(c.preferred_targeting_ids)

    targeting_map = {}
    if all_targeting_ids:
        templates = db.query(TargetingTemplate).filter(
            TargetingTemplate.id.in_(list(all_targeting_ids))
        ).all()
        targeting_map = {t.id: t.name for t in templates}

    # Convert to dict
    data = []
    for c in contents:
        # Use thumbnail service to get best available thumbnail URL
        # (local if available, otherwise remote URL)
        thumbnail_url = process_content_thumbnail(c)

        data.append({
            "id": c.id,
            "platform": c.platform.value if c.platform else None,
            "platform_post_id": c.platform_post_id,
            "url": c.url,
            "caption": c.caption,
            "thumbnail_url": thumbnail_url,
            "platform_created_at": c.platform_created_at.isoformat() if c.platform_created_at else None,
            "content_type": c.content_type.value if c.content_type else None,
            "content_tags": c.content_tags or [],
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
            "preferred_targeting_ids": c.preferred_targeting_ids or [],
            "targeting_names": [targeting_map.get(tid, f"ID:{tid}") for tid in (c.preferred_targeting_ids or [])],
            "boost_factor": float(c.boost_factor) if c.boost_factor else 1.0,
            "boost_start_date": c.boost_start_date.isoformat() if c.boost_start_date else None,
            "boost_end_date": c.boost_end_date.isoformat() if c.boost_end_date else None,
            "boost_reason": c.boost_reason,
            "employee_id": c.employee_id,
            "influencer_id": c.influencer_id,
            "influencer_cost": float(c.influencer_cost) if c.influencer_cost else None,
            "expire_date": c.expire_date.isoformat() if c.expire_date else None,
            "staff_allocations": [
                {
                    "id": sa.id,
                    "employee_id": sa.employee_id,
                    "employee_name": sa.employee.display_name if sa.employee else None,
                    "role": sa.role if sa.role else None,
                    "percentage": float(sa.percentage) if sa.percentage else 0,
                    "notes": sa.notes
                }
                for sa in c.staff_allocations if sa.deleted_at is None
            ] if hasattr(c, 'staff_allocations') else [],
        })

    return ListResponse(
        success=True,
        data=data,
        total=total,
        page=page,
        page_size=page_size,
        pages=(total + page_size - 1) // page_size
    )


@router.get("/best-each-product")
def get_best_content_each_product(
    platform: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get the best content (highest PFM score) for each product"""
    from datetime import datetime

    from sqlalchemy import text

    # Build platform condition - cast to platform enum type
    platform_condition = ""
    params = {}
    if platform:
        # PostgreSQL enum needs uppercase value
        platform_condition = "AND c.platform = CAST(:platform AS platform)"
        params["platform"] = platform.upper()

    # Use raw SQL for complex query with JSON array elements
    # Use subquery to filter valid arrays first, then expand
    query = text(f"""
        WITH valid_contents AS (
            -- First filter to only contents with valid array product_codes
            SELECT c.*
            FROM contents c
            WHERE c.deleted_at IS NULL
              AND c.product_codes IS NOT NULL
              AND c.product_codes::text LIKE '[%'  -- Simple check for array
              AND c.pfm_score IS NOT NULL
              AND c.pfm_score > 0
              AND (c.expire_date IS NULL OR c.expire_date > CURRENT_DATE)
              {platform_condition}
        ),
        content_products AS (
            -- Now expand the product_codes array
            SELECT
                vc.*,
                jsonb_array_elements_text(vc.product_codes::jsonb) AS product_code
            FROM valid_contents vc
        ),
        best_per_product AS (
            SELECT
                product_code,
                MAX(pfm_score) AS max_pfm
            FROM content_products
            GROUP BY product_code
        )
        SELECT DISTINCT cp.id
        FROM content_products cp
        JOIN best_per_product bp
            ON cp.product_code = bp.product_code
            AND cp.pfm_score = bp.max_pfm
        ORDER BY cp.id
    """)

    result = db.execute(query, params).fetchall()
    content_ids = [row[0] for row in result]

    if not content_ids:
        return ListResponse(
            success=True,
            data=[],
            total=0,
            page=1,
            page_size=len(content_ids) or 1,
            pages=1
        )

    # Fetch full content objects
    from sqlalchemy.orm import joinedload
    contents = db.query(Content)\
        .options(joinedload(Content.staff_allocations))\
        .filter(Content.id.in_(content_ids))\
        .order_by(Content.pfm_score.desc().nullslast())\
        .all()

    # Build targeting template lookup
    from app.models.platform import TargetingTemplate
    all_targeting_ids = set()
    for c in contents:
        if c.preferred_targeting_ids:
            all_targeting_ids.update(c.preferred_targeting_ids)

    targeting_map = {}
    if all_targeting_ids:
        templates = db.query(TargetingTemplate).filter(
            TargetingTemplate.id.in_(list(all_targeting_ids))
        ).all()
        targeting_map = {t.id: t.name for t in templates}

    # Convert to dict
    data = []
    for c in contents:
        thumbnail_url = process_content_thumbnail(c)

        data.append({
            "id": c.id,
            "platform": c.platform.value if c.platform else None,
            "platform_post_id": c.platform_post_id,
            "url": c.url,
            "caption": c.caption,
            "thumbnail_url": thumbnail_url,
            "platform_created_at": c.platform_created_at.isoformat() if c.platform_created_at else None,
            "content_type": c.content_type.value if c.content_type else None,
            "content_tags": c.content_tags or [],
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
            "preferred_targeting_ids": c.preferred_targeting_ids or [],
            "targeting_names": [targeting_map.get(tid, f"ID:{tid}") for tid in (c.preferred_targeting_ids or [])],
            "boost_factor": float(c.boost_factor) if c.boost_factor else 1.0,
            "boost_start_date": c.boost_start_date.isoformat() if c.boost_start_date else None,
            "boost_end_date": c.boost_end_date.isoformat() if c.boost_end_date else None,
            "boost_reason": c.boost_reason,
            "employee_id": c.employee_id,
            "influencer_id": c.influencer_id,
            "influencer_cost": float(c.influencer_cost) if c.influencer_cost else None,
            "expire_date": c.expire_date.isoformat() if c.expire_date else None,
            "staff_allocations": [
                {
                    "id": sa.id,
                    "employee_id": sa.employee_id,
                    "employee_name": sa.employee.display_name if sa.employee else None,
                    "role": sa.role if sa.role else None,
                    "percentage": float(sa.percentage) if sa.percentage else 0,
                    "notes": sa.notes
                }
                for sa in c.staff_allocations if sa.deleted_at is None
            ] if hasattr(c, 'staff_allocations') else [],
        })

    return ListResponse(
        success=True,
        data=data,
        total=len(data),
        page=1,
        page_size=len(data) or 1,
        pages=1
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
    """Sync contents and ads from all platforms"""
    from app.tasks import sync_tasks

    results = {
        "tiktok": {"success": False, "synced": 0},
        "facebook": {"success": False, "synced": 0},
        "instagram": {"success": False, "synced": 0},
        "ads": {"success": False, "synced": 0}
    }

    total_synced = 0

    # Resolve effective TikTok credentials
    # - access_token: ใช้ TikTokService.get_access_token() (รองรับทั้ง token ตรง ๆ และ refresh token)
    # - business_id: ใช้จาก settings (TIKTOK_BUSINESS_ID หรือ BUSINESS_ID)
    access_token = TikTokService.get_access_token()
    business_id = settings.tiktok_business_id

    # Sync TikTok Content
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


@router.post("/sync-ads")
def sync_ads_to_content(
    days: int = 7,
    db: Session = Depends(get_db)
):
    """
    Sync TikTok Ads และ map กลับไปหา Content

    Flow ใหม่:
    1. ดึง Ads ที่มี spend ใน N วันล่าสุด (ไม่ดึงทั้งหมด)
    2. ดึง metadata ของ Ads เหล่านั้น
    3. ดึง lifetime cost ของ Ads เหล่านั้น
    4. อัพเดท Ads, Content.ads_count และ Content.ads_total_cost

    Args:
        days: จำนวนวันที่จะดึง ads ที่มี activity (default=7)
    """
    try:
        ads_result = sync_tasks.sync_tiktok_ads(days=days)
        total_spend = ads_result.get("total_spend_synced", 0)
        return DataResponse(
            success=True,
            data={
                "ads_synced": ads_result.get("processed", 0),
                "mapped_contents": ads_result.get("success", 0),
                "total_spend": total_spend,
                "details": ads_result
            },
            message=f"Synced {ads_result.get('processed', 0)} ads (฿{total_spend:,.2f}), mapped to {ads_result.get('success', 0)} contents"
        )
    except Exception as e:
        return DataResponse(
            success=False,
            data={},
            message=f"Error syncing ads: {str(e)}"
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


# ============================================
# Naming helpers for Boost / Ads creation
# ============================================


class BoostNamingRequest(BaseModel):
    """ข้อมูล minimal สำหรับสร้างชื่อ campaign/adgroup/ad จาก content"""

    product_codes: List[str] = []
    objective_code: str = "VV"
    strategy_code: Optional[str] = None
    period_code: Optional[str] = None

    structure_code: str = "ACE"  # ACE / ABX
    content_style_code: Optional[str] = None  # SALE / BR / REV / ECOM / OTH
    targeting_code: Optional[str] = None

    content_code: Optional[str] = None  # เช่น C7606 หรือ item_id
    angle_code: Optional[str] = None  # เช่น DOCTOR / REVIEW / UGC


@router.post("/{content_id}/suggest-names")
def suggest_boost_names(
    content_id: int,
    payload: BoostNamingRequest,
    db: Session = Depends(get_db),
):
    """
    สร้างชื่อ default สำหรับ Campaign / AdGroup / Ad จาก content + ตัวเลือกเบื้องต้น

    ใช้ตอนเปิด modal Boost ที่หน้า Content:
    - frontend ส่ง product_codes / objective / structure / content_style / targeting ฯลฯ
    - backend คืนชื่อที่ generate แล้วไปเติมใน input ให้ user แก้ไขต่อได้
    """
    content = (
        db.query(Content)
        .filter(Content.id == content_id, Content.deleted_at.is_(None))
        .first()
    )
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")

    # ถ้า frontend ไม่ส่ง product_codes มา ให้ fallback จาก content.product_codes
    product_codes = payload.product_codes or (content.product_codes or [])

    campaign_name = NamingService.generate_campaign_name(
        product_codes=product_codes,
        objective_code=payload.objective_code,
        strategy_code=payload.strategy_code,
        period_code=payload.period_code,
    )

    adgroup_name = NamingService.generate_adgroup_name(
        product_codes=product_codes,
        structure_code=payload.structure_code,
        content_style_code=payload.content_style_code,
        targeting_code=payload.targeting_code,
        index=1,
    )

    # สร้าง content_code default ถ้าไม่ได้ส่งมา
    content_code = payload.content_code or f"C{content_id}"

    ad_name = NamingService.generate_ad_name(
        product_codes=product_codes,
        structure_code=payload.structure_code,
        targeting_code=payload.targeting_code,
        content_code=content_code,
        content_style_code=payload.content_style_code,
        angle_code=payload.angle_code,
    )

    return DataResponse(
        success=True,
        data={
            "campaign_name": campaign_name,
            "adgroup_name": adgroup_name,
            "ad_name": ad_name,
        },
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
            "thumbnail_url": process_content_thumbnail(content),
            "platform_created_at": content.platform_created_at.isoformat() if content.platform_created_at else None,
            "content_type": content.content_type.value if content.content_type else None,
            "content_tags": content.content_tags or [],
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
            "employee_id": content.employee_id,
            "influencer_id": content.influencer_id,
            "influencer_cost": float(content.influencer_cost) if content.influencer_cost else None,
            "expire_date": content.expire_date.isoformat() if content.expire_date else None,
            "staff_allocations": [
                {
                    "id": sa.id,
                    "employee_id": sa.employee_id,
                    "employee_name": sa.employee.display_name if sa.employee else None,
                    "role": sa.role if sa.role else None,
                    "percentage": float(sa.percentage) if sa.percentage else 0,
                    "notes": sa.notes
                }
                for sa in content.staff_allocations if sa.deleted_at is None
            ],
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
    import traceback
    from datetime import date as date_type
    from datetime import datetime

    from app.models.enums import ContentSource

    try:
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

        # Update content tags
        if "content_tags" in payload:
            content.content_tags = payload["content_tags"] if payload["content_tags"] else []

        # Update product codes
        if "product_codes" in payload:
            content.product_codes = payload["product_codes"]

        # Update employee_id (legacy - keep for backward compatibility)
        if "employee_id" in payload:
            content.employee_id = payload["employee_id"] if payload["employee_id"] else None

        # Update staff_allocations (new multi-staff system)
        if "staff_allocations" in payload:
            staff_allocations = payload["staff_allocations"]

            # Filter out empty allocations (no employee_id)
            staff_allocations = [sa for sa in staff_allocations if sa.get("employee_id")]

            # Validate: percentage รวมกันต้อง = 100% (ถ้ามี allocations)
            if staff_allocations:
                total_percentage = sum(float(sa.get("percentage", 0)) for sa in staff_allocations)
                if abs(total_percentage - 100.0) > 0.01:  # Allow small floating point error
                    raise HTTPException(
                        status_code=400,
                        detail=f"Staff allocations percentage must sum to 100%. Current sum: {total_percentage}%"
                    )

            # ลบ allocations เก่าทั้งหมด (soft delete)
            db.query(ContentStaffAllocation).filter(
                ContentStaffAllocation.content_id == content_id,
                ContentStaffAllocation.deleted_at.is_(None)
            ).update({"deleted_at": datetime.now()})
            db.flush()  # Flush to ensure soft delete is applied before adding new ones

            # เพิ่ม allocations ใหม่
            if staff_allocations:
                for sa_data in staff_allocations:
                    # Ensure employee_id is integer
                    employee_id = int(sa_data["employee_id"]) if sa_data.get("employee_id") else None
                    if not employee_id:
                        continue  # Skip if no employee_id

                    # Role เป็น string (lowercase)
                    role_str = sa_data.get("role", "other").lower()
                    # Validate role - must be one of the valid values
                    valid_roles = ['actor', 'editor', 'creative', 'cameraman', 'director', 'producer', 'other']
                    if role_str not in valid_roles:
                        role_str = 'other'

                    allocation = ContentStaffAllocation(
                        content_id=content_id,
                        employee_id=employee_id,
                        role=role_str,  # ใช้ string โดยตรง
                        percentage=float(sa_data.get("percentage", 0)),
                        notes=sa_data.get("notes")
                    )
                    db.add(allocation)

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

        # Update preferred_targeting_ids (multi-select targeting templates)
        if "preferred_targeting_ids" in payload:
            targeting_ids = payload["preferred_targeting_ids"]
            if targeting_ids and isinstance(targeting_ids, list):
                # Validate that all IDs exist
                from app.models import TargetingTemplate
                valid_ids = [t.id for t in db.query(TargetingTemplate.id).filter(
                    TargetingTemplate.id.in_(targeting_ids)
                ).all()]
                content.preferred_targeting_ids = valid_ids
            else:
                content.preferred_targeting_ids = None

        db.commit()

        return DataResponse(
            success=True,
            message="Content updated"
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        traceback.print_exc()
        print(f"[update_content] Error: {error_msg}")
        print(f"[update_content] Payload: {payload}")
        raise HTTPException(
            status_code=500,
            detail=f"Error updating content: {error_msg}"
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

    This function fetches real-time data from TikTok API and updates:
    1. Spend data (lifetime spend per ad) - via Report API
    2. Ad details (ad_name, adgroup_name, campaign_name, operation_status, etc.) - via Ad API
    3. Adgroup details (budget, budget_mode, operation_status) - via Adgroup API
    4. Updates content.ads_details, ads_total_cost, ace_ad_count, abx_ad_count in DB
    """
    import concurrent.futures

    from app.models import ABXAdgroup
    from app.services.tiktok_ads_service import TikTokAdsService

    if not ads_details:
        return ads_details

    # Group ads by advertiser_id and collect IDs
    advertiser_ads = {}
    all_ad_ids_by_advertiser = {}
    all_adgroup_ids_by_advertiser = {}

    for ad in ads_details:
        advertiser_id = ad.get('advertiser_id')
        adgroup_id = ad.get('adgroup_id')
        ad_id = ad.get('ad_id')

        if advertiser_id:
            if advertiser_id not in advertiser_ads:
                advertiser_ads[advertiser_id] = []
                all_ad_ids_by_advertiser[advertiser_id] = []
                all_adgroup_ids_by_advertiser[advertiser_id] = set()

            advertiser_ads[advertiser_id].append(ad)

            if ad_id:
                all_ad_ids_by_advertiser[advertiser_id].append(str(ad_id))
            if adgroup_id:
                all_adgroup_ids_by_advertiser[advertiser_id].add(adgroup_id)

    total_ad_cost = 0.0
    ace_count = 0
    abx_count = 0
    general_count = 0

    # Fetch real-time data from TikTok API for each advertiser
    # Use ThreadPoolExecutor for parallel API calls (like old system)
    for advertiser_id, ads in advertiser_ads.items():
        if not advertiser_id:
            continue

        ad_ids_for_this = all_ad_ids_by_advertiser.get(advertiser_id, [])
        adgroup_ids_for_this = list(all_adgroup_ids_by_advertiser.get(advertiser_id, []))

        # Initialize maps
        ad_spend_map = {}
        ad_details_map = {}
        adgroup_map = {}

        try:
            # Parallel API calls for better performance
            # NOTE: Use requests instead of httpx for Report API (httpx has issues with TikTok)
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                # 1. Fetch lifetime spend for this advertiser (real-time!)
                future_spend = executor.submit(
                    TikTokAdsService.fetch_lifetime_spend_by_advertiser,
                    advertiser_id
                )

                # 2. Fetch ad details (ad_name, campaign_name, adgroup_name, status, etc.)
                future_ad_details = executor.submit(
                    TikTokAdsService.fetch_ad_details_batch,
                    advertiser_id,
                    ad_ids_for_this
                )

                # 3. Fetch adgroup details (budget, budget_mode, operation_status)
                future_adgroup = executor.submit(
                    TikTokAdsService.fetch_adgroup_details,
                    advertiser_id,
                    adgroup_ids_for_this
                )

                # Wait for all to complete
                ad_spend_map = future_spend.result()
                ad_details_map = future_ad_details.result()
                adgroup_map = future_adgroup.result()

            # Update each ad with real-time data
            for ad in ads:
                ad_id = ad.get('ad_id')
                adgroup_id = ad.get('adgroup_id')

                # 1. Update spend (real-time from Report API)
                # NOTE: Convert ad_id to string for comparison (TikTok API returns string IDs)
                ad_id_str = str(ad_id) if ad_id else None

                if ad_id_str and ad_id_str in ad_spend_map:
                    spend = ad_spend_map[ad_id_str]
                    ad['ad_total_cost'] = spend
                    ad['spend'] = spend
                    total_ad_cost += spend
                    print(f"[refresh] Updated ad {ad_id_str} spend: {spend}")
                else:
                    # Keep existing value if not found in API response
                    old_cost = float(ad.get('ad_total_cost') or ad.get('spend') or 0)
                    ad['ad_total_cost'] = old_cost
                    ad['spend'] = old_cost
                    total_ad_cost += old_cost
                    print(f"[refresh] ad {ad_id_str} NOT in spend_map, using old cost: {old_cost}")

                # 2. Update ad details (ad_name, campaign_name, adgroup_name, status, etc.)
                if ad_id and ad_id in ad_details_map:
                    ad_info = ad_details_map[ad_id]
                    ad['ad_name'] = ad_info.get('ad_name') or ad.get('ad_name')
                    ad['campaign_id'] = ad_info.get('campaign_id') or ad.get('campaign_id')
                    ad['campaign_name'] = ad_info.get('campaign_name') or ad.get('campaign_name')
                    ad['adgroup_id'] = ad_info.get('adgroup_id') or ad.get('adgroup_id')
                    ad['adgroup_name'] = ad_info.get('adgroup_name') or ad.get('adgroup_name')
                    ad['operation_status'] = ad_info.get('operation_status') or ad.get('operation_status')
                    ad['secondary_status'] = ad_info.get('secondary_status') or ad.get('secondary_status')
                    ad['display_name'] = ad_info.get('display_name') or ad.get('display_name')
                    ad['create_time'] = ad_info.get('create_time') or ad.get('create_time')
                    ad['modify_time'] = ad_info.get('modify_time') or ad.get('modify_time')
                    ad['tiktok_item_id'] = ad_info.get('tiktok_item_id') or ad.get('tiktok_item_id')

                # 3. Update adgroup info (budget, budget_mode, status)
                if adgroup_id and adgroup_id in adgroup_map:
                    ag_info = adgroup_map[adgroup_id]
                    budget = ag_info.get('budget', 0)
                    # TikTok API returns budget in micro-units (x1,000,000) for some cases
                    if budget and budget > 100000:
                        budget = budget / 1000000
                    ad['adgroup_budget'] = budget
                    ad['adgroup_budget_mode'] = ag_info.get('budget_mode')
                    ad['adgroup_status'] = ag_info.get('operation_status')
                    # Update operation_status from adgroup if not already set from ad_details
                    if not ad.get('operation_status'):
                        ad['operation_status'] = ag_info.get('operation_status')
                    if not ad.get('secondary_status'):
                        ad['secondary_status'] = ag_info.get('secondary_status')

                # 4. Classify ACE/ABX/General based on name patterns
                ad_name = (ad.get('ad_name') or '').upper()
                campaign_name = (ad.get('campaign_name') or '').upper()
                adgroup_name = (ad.get('adgroup_name') or '').upper()

                if '_ABX_' in ad_name or '_ABX_' in campaign_name or '_ABX_' in adgroup_name:
                    ad['type'] = 'ABX'
                    abx_count += 1
                elif '_ACE_' in ad_name or '_ACE_' in campaign_name or '_ACE_' in adgroup_name or '_ACEBOOSTX_' in campaign_name:
                    ad['type'] = 'ACE'
                    ace_count += 1
                else:
                    ad['type'] = 'GENERAL'
                    general_count += 1

        except Exception as e:
            print(f"[refresh_tiktok_ads_data] Error fetching data for advertiser {advertiser_id}: {e}")
            # Still classify ads even if API fails - use name-based detection
            for ad in ads:
                ad_name = (ad.get('ad_name') or '').upper()
                campaign_name = (ad.get('campaign_name') or '').upper()
                adgroup_name = (ad.get('adgroup_name') or '').upper()

                # Keep existing spend
                old_cost = float(ad.get('ad_total_cost') or ad.get('spend') or 0)
                total_ad_cost += old_cost

                if '_ABX_' in ad_name or '_ABX_' in campaign_name or '_ABX_' in adgroup_name:
                    ad['type'] = 'ABX'
                    abx_count += 1
                elif '_ACE_' in ad_name or '_ACE_' in campaign_name or '_ACE_' in adgroup_name or '_ACEBOOSTX_' in campaign_name:
                    ad['type'] = 'ACE'
                    ace_count += 1
                else:
                    ad['type'] = 'GENERAL'
                    general_count += 1

    # Update content in database
    content.ads_count = len(ads_details)
    content.ace_ad_count = ace_count
    content.abx_ad_count = abx_count
    content.ads_total_cost = total_ad_cost
    content.ace_details = [ad for ad in ads_details if ad.get('type') == 'ACE'] or None
    content.abx_details = [ad for ad in ads_details if ad.get('type') == 'ABX'] or None

    # Update ads_details in database
    platform_key = content.platform.value.lower()
    content.ads_details = {platform_key: ads_details}
    db.commit()

    print(f"[refresh_tiktok_ads_data] Updated content {content.id}: "
          f"total_cost=฿{total_ad_cost:,.2f}, ads={len(ads_details)}, "
          f"ACE={ace_count}, ABX={abx_count}, General={general_count}")

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

