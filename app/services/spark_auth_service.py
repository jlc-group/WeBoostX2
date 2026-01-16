"""
Spark Ad Authorization Service

จัดการ Auth Codes จาก Influencers สำหรับ Spark Ads:
1. Bulk import auth codes
2. Authorize กับ TikTok API
3. Auto-match กับ content
4. Manual binding
"""
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import (
    SparkAdAuth, SparkAuthImportLog, SparkAuthStatus,
    Content, AdAccount, Influencer,
    Platform,
)
from app.models.enums import AdAccountStatus, ContentSource, Platform as PlatformEnum


class SparkAuthService:
    """Service สำหรับจัดการ Spark Ad Authorization"""
    
    BASE_URL = settings.TIKTOK_API_BASE_URL
    
    @classmethod
    def _get_access_token(cls) -> str:
        """ดึง access token สำหรับ TikTok Ads API"""
        if settings.TIKTOK_AD_TOKEN:
            return settings.TIKTOK_AD_TOKEN
        
        from app.services.tiktok_service import TikTokService
        token = TikTokService.get_access_token()
        if token:
            return token
        
        return settings.tiktok_content_access_token or ""
    
    @classmethod
    def _get_client(cls) -> httpx.Client:
        return httpx.Client(timeout=30.0)
    
    # ============================================
    # Bulk Import
    # ============================================
    
    @classmethod
    def bulk_import_auth_codes(
        cls,
        auth_codes: List[Dict],
        ad_account_id: int,
        batch_name: Optional[str] = None,
        agency_name: Optional[str] = None,
        imported_by: Optional[int] = None,
        auto_authorize: bool = True,
    ) -> Dict:
        """
        Bulk import auth codes และ authorize ทันที
        
        Args:
            auth_codes: List of dicts with keys:
                - auth_code: required
                - influencer_name: optional
                - creator_username: optional
                - notes: optional
            ad_account_id: Internal ad account ID
            batch_name: ชื่อ batch สำหรับ tracking
            agency_name: ชื่อ agency ที่ส่งมา
            imported_by: User ID ที่ import
            auto_authorize: ถ้า True จะ authorize กับ TikTok ทันที
            
        Returns:
            Dict with stats and details
        """
        db = SessionLocal()
        
        try:
            # Get ad account
            ad_account = db.query(AdAccount).filter(
                AdAccount.id == ad_account_id
            ).first()
            
            if not ad_account:
                return {"success": False, "message": "Ad account not found"}
            
            results = {
                "total": len(auth_codes),
                "imported": 0,
                "authorized": 0,
                "bound": 0,
                "failed": 0,
                "details": [],
            }
            
            for code_data in auth_codes:
                auth_code = code_data.get("auth_code", "").strip()
                
                if not auth_code:
                    results["failed"] += 1
                    results["details"].append({
                        "auth_code": auth_code,
                        "status": "failed",
                        "error": "Empty auth code",
                    })
                    continue
                
                # Check if already exists
                existing = db.query(SparkAdAuth).filter(
                    SparkAdAuth.auth_code == auth_code,
                    SparkAdAuth.deleted_at.is_(None),
                ).first()
                
                if existing:
                    results["details"].append({
                        "auth_code": auth_code[:20] + "...",
                        "status": "skipped",
                        "error": "Already exists",
                        "id": existing.id,
                    })
                    continue
                
                # Create new SparkAdAuth
                spark_auth = SparkAdAuth(
                    auth_code=auth_code,
                    platform=Platform.TIKTOK,
                    status=SparkAuthStatus.PENDING,
                    influencer_name=code_data.get("influencer_name"),
                    creator_username=code_data.get("creator_username"),
                    agency_name=agency_name,
                    batch_name=batch_name,
                    notes=code_data.get("notes"),
                    ad_account_id=ad_account_id,
                    imported_by=imported_by,
                    imported_at=datetime.now(timezone.utc),
                )
                db.add(spark_auth)
                db.flush()  # Get ID
                
                results["imported"] += 1
                
                # Auto authorize if enabled
                if auto_authorize:
                    auth_result = cls._authorize_with_tiktok(
                        db, spark_auth, ad_account.external_account_id
                    )
                    
                    if auth_result["success"]:
                        results["authorized"] += 1
                        
                        # Try to auto-bind with content
                        if spark_auth.item_id:
                            bind_result = cls._auto_bind_content(db, spark_auth)
                            if bind_result:
                                results["bound"] += 1
                    else:
                        results["failed"] += 1
                    
                    results["details"].append({
                        "auth_code": auth_code[:20] + "...",
                        "status": spark_auth.status.value,
                        "item_id": spark_auth.item_id,
                        "content_id": spark_auth.content_id,
                        "error": spark_auth.error_message,
                    })
            
            db.commit()
            
            # Create import log
            import_log = SparkAuthImportLog(
                batch_name=batch_name,
                agency_name=agency_name,
                source="bulk_import",
                total_codes=results["total"],
                authorized_count=results["authorized"],
                bound_count=results["bound"],
                failed_count=results["failed"],
                details=results["details"],
                imported_by=imported_by,
            )
            db.add(import_log)
            db.commit()
            
            results["success"] = True
            results["import_log_id"] = import_log.id
            
            return results
            
        except Exception as e:
            db.rollback()
            return {"success": False, "message": str(e)}
        finally:
            db.close()
    
    @classmethod
    def _authorize_with_tiktok(
        cls,
        db: Session,
        spark_auth: SparkAdAuth,
        advertiser_id: str,
    ) -> Dict:
        """
        Authorize auth code กับ TikTok API
        
        เรียก POST /tt_video/authorize/
        """
        token = cls._get_access_token()
        if not token:
            spark_auth.status = SparkAuthStatus.FAILED
            spark_auth.error_message = "Missing access token"
            return {"success": False, "error": "Missing access token"}
        
        url = f"{cls.BASE_URL}/tt_video/authorize/"
        
        payload = {
            "advertiser_id": advertiser_id,
            "auth_code": spark_auth.auth_code,
        }
        
        with cls._get_client() as client:
            try:
                resp = client.post(
                    url,
                    headers={
                        "Access-Token": token,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                
                data = resp.json()
                
                if resp.status_code == 200 and data.get("code") == 0:
                    # Success - extract item info
                    result_data = data.get("data", {})
                    
                    spark_auth.item_id = result_data.get("item_id")
                    spark_auth.identity_id = result_data.get("identity_id")
                    spark_auth.identity_type = "AUTH_CODE"
                    spark_auth.status = SparkAuthStatus.AUTHORIZED
                    spark_auth.authorized_at = datetime.now(timezone.utc)
                    
                    # Fetch additional info from tt_video/list
                    cls._fetch_auth_details(db, spark_auth, advertiser_id)
                    
                    print(f"[SparkAuthService] Authorized: {spark_auth.auth_code[:20]}... -> item_id={spark_auth.item_id}")
                    return {"success": True, "item_id": spark_auth.item_id}
                else:
                    error_msg = data.get("message", "Unknown error")
                    spark_auth.status = SparkAuthStatus.FAILED
                    spark_auth.error_message = error_msg
                    print(f"[SparkAuthService] Failed to authorize: {error_msg}")
                    return {"success": False, "error": error_msg}
                    
            except Exception as e:
                spark_auth.status = SparkAuthStatus.FAILED
                spark_auth.error_message = str(e)
                print(f"[SparkAuthService] Exception authorizing: {e}")
                return {"success": False, "error": str(e)}
    
    @classmethod
    def _fetch_auth_details(
        cls,
        db: Session,
        spark_auth: SparkAdAuth,
        advertiser_id: str,
    ):
        """
        Fetch auth_end_time และข้อมูลอื่นจาก tt_video/list
        """
        from app.services.tiktok_ads_service import TikTokAdsService
        
        posts = TikTokAdsService.fetch_spark_ad_posts(advertiser_id)
        
        for post in posts:
            if post.get("item_id") == spark_auth.item_id:
                # Parse auth times
                auth_end = post.get("auth_end_time")
                if auth_end:
                    try:
                        if isinstance(auth_end, str):
                            spark_auth.auth_end_time = datetime.strptime(
                                auth_end, "%Y-%m-%d %H:%M:%S"
                            ).replace(tzinfo=timezone.utc)
                        elif isinstance(auth_end, (int, float)):
                            spark_auth.auth_end_time = datetime.fromtimestamp(
                                auth_end, tz=timezone.utc
                            )
                    except Exception:
                        pass
                
                auth_start = post.get("auth_start_time")
                if auth_start:
                    try:
                        if isinstance(auth_start, str):
                            spark_auth.auth_start_time = datetime.strptime(
                                auth_start, "%Y-%m-%d %H:%M:%S"
                            ).replace(tzinfo=timezone.utc)
                    except Exception:
                        pass
                
                spark_auth.ad_auth_status = post.get("ad_auth_status")
                break
    
    @classmethod
    def _auto_bind_content(cls, db: Session, spark_auth: SparkAdAuth) -> bool:
        """
        Auto-bind spark auth กับ content ที่ตรงกับ item_id
        """
        if not spark_auth.item_id:
            return False
        
        # Find matching content
        content = db.query(Content).filter(
            Content.platform == PlatformEnum.TIKTOK,
            Content.platform_post_id == spark_auth.item_id,
            Content.deleted_at.is_(None),
        ).first()
        
        if content:
            spark_auth.content_id = content.id
            spark_auth.status = SparkAuthStatus.BOUND
            spark_auth.bound_at = datetime.now(timezone.utc)
            
            # Update content source to INFLUENCER if not set
            if not content.content_source:
                content.content_source = ContentSource.INFLUENCER
            
            # Update content expire_date from auth_end_time
            if spark_auth.auth_end_time and not content.expire_date:
                content.expire_date = spark_auth.auth_end_time.date()
            
            print(f"[SparkAuthService] Bound: item_id={spark_auth.item_id} -> content_id={content.id}")
            return True
        
        return False
    
    # ============================================
    # Manual Operations
    # ============================================
    
    @classmethod
    def authorize_single(
        cls,
        auth_code: str,
        ad_account_id: int,
        influencer_name: Optional[str] = None,
        imported_by: Optional[int] = None,
    ) -> Dict:
        """
        Authorize single auth code (manual input ตอนสร้าง ad)
        """
        return cls.bulk_import_auth_codes(
            auth_codes=[{
                "auth_code": auth_code,
                "influencer_name": influencer_name,
            }],
            ad_account_id=ad_account_id,
            imported_by=imported_by,
            auto_authorize=True,
        )
    
    @classmethod
    def get_auth_for_content(cls, content_id: int) -> Optional[SparkAdAuth]:
        """
        ดึง SparkAdAuth ที่ bound กับ content นี้
        """
        db = SessionLocal()
        try:
            return db.query(SparkAdAuth).filter(
                SparkAdAuth.content_id == content_id,
                SparkAdAuth.status.in_([
                    SparkAuthStatus.AUTHORIZED,
                    SparkAuthStatus.BOUND,
                ]),
                SparkAdAuth.deleted_at.is_(None),
            ).first()
        finally:
            db.close()
    
    @classmethod
    def check_content_has_auth(cls, content_id: int) -> Dict:
        """
        ตรวจสอบว่า content มี auth code ที่ใช้ได้หรือไม่
        
        Returns:
            {
                "has_auth": bool,
                "auth_id": int or None,
                "identity_id": str or None,
                "auth_end_time": datetime or None,
                "days_until_expire": int,
            }
        """
        db = SessionLocal()
        try:
            auth = db.query(SparkAdAuth).filter(
                SparkAdAuth.content_id == content_id,
                SparkAdAuth.status.in_([
                    SparkAuthStatus.AUTHORIZED,
                    SparkAuthStatus.BOUND,
                ]),
                SparkAdAuth.deleted_at.is_(None),
            ).first()
            
            if auth and auth.is_usable:
                return {
                    "has_auth": True,
                    "auth_id": auth.id,
                    "identity_id": auth.identity_id,
                    "auth_end_time": auth.auth_end_time.isoformat() if auth.auth_end_time else None,
                    "days_until_expire": auth.days_until_expire,
                }
            
            return {
                "has_auth": False,
                "auth_id": None,
                "identity_id": None,
                "auth_end_time": None,
                "days_until_expire": 0,
            }
        finally:
            db.close()
    
    @classmethod
    def mark_as_used(cls, auth_id: int, ad_id: int) -> bool:
        """
        Mark auth code as used (หลังสร้าง ad สำเร็จ)
        """
        db = SessionLocal()
        try:
            auth = db.query(SparkAdAuth).filter(
                SparkAdAuth.id == auth_id
            ).first()
            
            if auth:
                auth.status = SparkAuthStatus.USED
                auth.used_at = datetime.now(timezone.utc)
                auth.used_in_ad_id = ad_id
                db.commit()
                return True
            
            return False
        finally:
            db.close()
    
    # ============================================
    # Background Job: Auto-bind unbound auths
    # ============================================
    
    @classmethod
    def run_auto_bind_job(cls) -> Dict:
        """
        Background job: ลองจับคู่ AUTHORIZED auths ที่ยังไม่มี content
        
        สำหรับกรณีที่ import auth code ก่อน แล้ว content ถูก sync มาทีหลัง
        """
        db = SessionLocal()
        
        try:
            # Get authorized but not bound
            unbound = db.query(SparkAdAuth).filter(
                SparkAdAuth.status == SparkAuthStatus.AUTHORIZED,
                SparkAdAuth.content_id.is_(None),
                SparkAdAuth.item_id.isnot(None),
                SparkAdAuth.deleted_at.is_(None),
            ).all()
            
            bound_count = 0
            
            for auth in unbound:
                if cls._auto_bind_content(db, auth):
                    bound_count += 1
            
            db.commit()
            
            print(f"[SparkAuthService] Auto-bind job: {bound_count}/{len(unbound)} bound")
            
            return {
                "processed": len(unbound),
                "bound": bound_count,
            }
            
        finally:
            db.close()
    
    @classmethod
    def run_expire_check_job(cls) -> Dict:
        """
        Background job: Check และ update status ของ auth ที่หมดอายุ
        """
        db = SessionLocal()
        
        try:
            now = datetime.now(timezone.utc)
            
            # Find expired auths
            expired = db.query(SparkAdAuth).filter(
                SparkAdAuth.status.in_([
                    SparkAuthStatus.AUTHORIZED,
                    SparkAuthStatus.BOUND,
                ]),
                SparkAdAuth.auth_end_time < now,
                SparkAdAuth.deleted_at.is_(None),
            ).all()
            
            for auth in expired:
                auth.status = SparkAuthStatus.EXPIRED
            
            db.commit()
            
            print(f"[SparkAuthService] Expire check job: {len(expired)} marked as expired")
            
            return {"expired_count": len(expired)}
            
        finally:
            db.close()
    
    # ============================================
    # Query Methods
    # ============================================
    
    @classmethod
    def list_auths(
        cls,
        status: Optional[SparkAuthStatus] = None,
        ad_account_id: Optional[int] = None,
        batch_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict], int]:
        """
        List spark ad auths with filtering
        """
        db = SessionLocal()
        
        try:
            query = db.query(SparkAdAuth).filter(
                SparkAdAuth.deleted_at.is_(None)
            )
            
            if status:
                query = query.filter(SparkAdAuth.status == status)
            
            if ad_account_id:
                query = query.filter(SparkAdAuth.ad_account_id == ad_account_id)
            
            if batch_name:
                query = query.filter(SparkAdAuth.batch_name == batch_name)
            
            total = query.count()
            
            auths = query.order_by(
                SparkAdAuth.created_at.desc()
            ).offset(offset).limit(limit).all()
            
            results = []
            for auth in auths:
                results.append({
                    "id": auth.id,
                    "auth_code": auth.auth_code[:20] + "..." if len(auth.auth_code) > 20 else auth.auth_code,
                    "status": auth.status.value,
                    "item_id": auth.item_id,
                    "content_id": auth.content_id,
                    "influencer_name": auth.influencer_name,
                    "creator_username": auth.creator_username,
                    "agency_name": auth.agency_name,
                    "batch_name": auth.batch_name,
                    "auth_end_time": auth.auth_end_time.isoformat() if auth.auth_end_time else None,
                    "days_until_expire": auth.days_until_expire,
                    "is_usable": auth.is_usable,
                    "created_at": auth.created_at.isoformat() if auth.created_at else None,
                })
            
            return results, total
            
        finally:
            db.close()

