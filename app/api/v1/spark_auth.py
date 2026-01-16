"""
Spark Ad Authorization API Routes

Endpoints for managing Influencer Auth Codes:
1. Bulk import auth codes
2. List/query auth codes
3. Manual authorize (fallback ตอนสร้าง ad)
4. Check auth status for content
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, get_current_active_user
from app.models import User, SparkAuthStatus
from app.services.spark_auth_service import SparkAuthService

router = APIRouter(prefix="/spark-auth", tags=["Spark Auth"])


# ============================================
# Pydantic Models
# ============================================

class AuthCodeInput(BaseModel):
    """Single auth code input"""
    auth_code: str
    influencer_name: Optional[str] = None
    creator_username: Optional[str] = None
    notes: Optional[str] = None


class BulkImportRequest(BaseModel):
    """Request for bulk import"""
    ad_account_id: int
    auth_codes: List[AuthCodeInput]
    batch_name: Optional[str] = None
    agency_name: Optional[str] = None
    auto_authorize: bool = True


class SingleAuthorizeRequest(BaseModel):
    """Request for single authorize (manual input)"""
    auth_code: str
    ad_account_id: int
    influencer_name: Optional[str] = None


class AuthCodeResponse(BaseModel):
    """Response for auth code"""
    id: int
    auth_code: str
    status: str
    item_id: Optional[str]
    content_id: Optional[int]
    influencer_name: Optional[str]
    creator_username: Optional[str]
    agency_name: Optional[str]
    batch_name: Optional[str]
    auth_end_time: Optional[str]
    days_until_expire: int
    is_usable: bool
    created_at: Optional[str]


# ============================================
# API Endpoints
# ============================================

@router.post("/bulk-import", summary="Bulk import auth codes")
async def bulk_import_auth_codes(
    request: BulkImportRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Bulk import auth codes จาก Influencers
    
    - รับ list ของ auth codes
    - Authorize กับ TikTok API ทันที (ถ้า auto_authorize=True)
    - Auto-bind กับ content ที่ตรงกัน
    """
    auth_codes = [code.model_dump() for code in request.auth_codes]
    
    result = SparkAuthService.bulk_import_auth_codes(
        auth_codes=auth_codes,
        ad_account_id=request.ad_account_id,
        batch_name=request.batch_name,
        agency_name=request.agency_name,
        imported_by=current_user.id,
        auto_authorize=request.auto_authorize,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    
    return result


@router.post("/authorize", summary="Authorize single auth code")
async def authorize_single(
    request: SingleAuthorizeRequest,
    current_user: User = Depends(get_current_active_user),
):
    """
    Authorize single auth code (สำหรับ manual input ตอนสร้าง ad)
    
    ใช้เมื่อ content ไม่มี auth code bound อยู่
    """
    result = SparkAuthService.authorize_single(
        auth_code=request.auth_code,
        ad_account_id=request.ad_account_id,
        influencer_name=request.influencer_name,
        imported_by=current_user.id,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message"))
    
    return result


@router.get("/check/{content_id}", summary="Check if content has valid auth")
async def check_content_auth(
    content_id: int,
    current_user: User = Depends(get_current_active_user),
):
    """
    ตรวจสอบว่า content มี auth code ที่ใช้ได้หรือไม่
    
    ใช้ตอนโหลดหน้า Create Ad เพื่อแสดง/ซ่อน manual input
    """
    return SparkAuthService.check_content_has_auth(content_id)


@router.get("/list", summary="List auth codes")
async def list_auth_codes(
    status: Optional[str] = Query(None, description="Filter by status"),
    ad_account_id: Optional[int] = Query(None, description="Filter by ad account"),
    batch_name: Optional[str] = Query(None, description="Filter by batch name"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_active_user),
):
    """
    List spark ad auths with filtering
    """
    status_enum = None
    if status:
        try:
            status_enum = SparkAuthStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    auths, total = SparkAuthService.list_auths(
        status=status_enum,
        ad_account_id=ad_account_id,
        batch_name=batch_name,
        limit=limit,
        offset=offset,
    )
    
    return {
        "items": auths,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/import-csv", summary="Import auth codes from CSV")
async def import_from_csv(
    file: UploadFile = File(...),
    ad_account_id: int = Query(..., description="Ad account ID"),
    batch_name: Optional[str] = Query(None),
    agency_name: Optional[str] = Query(None),
    current_user: User = Depends(get_current_active_user),
):
    """
    Import auth codes จาก CSV file
    
    CSV format:
    auth_code,influencer_name,creator_username,notes
    """
    import csv
    import io
    
    # Read CSV content
    content = await file.read()
    
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        decoded = content.decode("utf-8-sig")  # Try with BOM
    
    reader = csv.DictReader(io.StringIO(decoded))
    
    auth_codes = []
    for row in reader:
        auth_code = row.get("auth_code", "").strip()
        if auth_code:
            auth_codes.append({
                "auth_code": auth_code,
                "influencer_name": row.get("influencer_name", "").strip() or None,
                "creator_username": row.get("creator_username", "").strip() or None,
                "notes": row.get("notes", "").strip() or None,
            })
    
    if not auth_codes:
        raise HTTPException(status_code=400, detail="No valid auth codes found in CSV")
    
    result = SparkAuthService.bulk_import_auth_codes(
        auth_codes=auth_codes,
        ad_account_id=ad_account_id,
        batch_name=batch_name or file.filename,
        agency_name=agency_name,
        imported_by=current_user.id,
        auto_authorize=True,
    )
    
    return result


@router.post("/run-auto-bind", summary="Run auto-bind job")
async def run_auto_bind(
    current_user: User = Depends(get_current_active_user),
):
    """
    Manual trigger: Auto-bind unbound auth codes กับ content
    
    ใช้เมื่อ import auth codes ก่อน แล้ว content ถูก sync มาทีหลัง
    """
    result = SparkAuthService.run_auto_bind_job()
    return result


@router.post("/run-expire-check", summary="Run expire check job")
async def run_expire_check(
    current_user: User = Depends(get_current_active_user),
):
    """
    Manual trigger: Check และ update status ของ auth ที่หมดอายุ
    """
    result = SparkAuthService.run_expire_check_job()
    return result


@router.get("/stats", summary="Get auth codes statistics")
async def get_stats(
    ad_account_id: Optional[int] = Query(None),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Get statistics of auth codes
    """
    from app.models import SparkAdAuth
    from sqlalchemy import func
    
    query = db.query(
        SparkAdAuth.status,
        func.count(SparkAdAuth.id).label("count")
    ).filter(
        SparkAdAuth.deleted_at.is_(None)
    )
    
    if ad_account_id:
        query = query.filter(SparkAdAuth.ad_account_id == ad_account_id)
    
    query = query.group_by(SparkAdAuth.status)
    
    results = query.all()
    
    stats = {status.value: 0 for status in SparkAuthStatus}
    for status, count in results:
        stats[status.value] = count
    
    stats["total"] = sum(stats.values())
    
    return stats

