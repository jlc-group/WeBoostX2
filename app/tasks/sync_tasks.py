"""
Content and Ad sync tasks
"""
from datetime import datetime, timedelta
from typing import List

from app.core.database import SessionLocal
from app.models import TaskLog, TaskStatus, Platform, Content, AppSetting
from app.models.enums import Platform as PlatformEnum
from app.services.tiktok_service import TikTokService
from app.services.tiktok_ads_service import TikTokAdsService


def log_task_start(task_name: str, task_type: str = "sync") -> TaskLog:
    """Create task log entry"""
    db = SessionLocal()
    try:
        task = TaskLog(
            task_name=task_name,
            task_type=task_type,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(),
            triggered_by="scheduler"
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        return task
    finally:
        db.close()


def log_task_complete(task_id: int, success: bool, message: str = None, 
                      items_processed: int = 0, items_success: int = 0, items_failed: int = 0):
    """Update task log on completion"""
    db = SessionLocal()
    try:
        task = db.query(TaskLog).filter(TaskLog.id == task_id).first()
        if task:
            task.status = TaskStatus.COMPLETED if success else TaskStatus.FAILED
            task.completed_at = datetime.now()
            # คำนวณ duration แบบระมัดระวัง timezone: ถ้ามีข้อมูลครบและไม่ error ค่อยคำนวณ
            try:
                if task.started_at and task.completed_at:
                    start = task.started_at
                    end = task.completed_at
                    # ถ้า timezone ไม่ตรงกัน ให้ตัด tzinfo ทิ้งทั้งคู่แล้วคำนวณแบบ naive
                    if (start.tzinfo is None) != (end.tzinfo is None):
                        start = start.replace(tzinfo=None)
                        end = end.replace(tzinfo=None)
                    task.duration_seconds = int((end - start).total_seconds())
            except Exception:
                # ถ้าคำนวณไม่ได้ไม่ต้องเซ็ต duration ปล่อยผ่านไป
                pass
            task.message = message
            task.items_processed = items_processed
            task.items_success = items_success
            task.items_failed = items_failed
            db.commit()
    finally:
        db.close()


def sync_all_content():
    """
    Sync content from all platforms
    - TikTok posts
    - Facebook posts
    - Instagram media
    """
    task = log_task_start("sync_all_content", "sync")
    
    total_processed = 0
    total_success = 0
    total_failed = 0
    
    try:
        # Sync TikTok content
        print(f"  Syncing TikTok content...")
        tiktok_result = sync_tiktok_content()
        total_processed += tiktok_result.get("processed", 0)
        total_success += tiktok_result.get("success", 0)
        total_failed += tiktok_result.get("failed", 0)
        
        # Sync Facebook content
        print(f"  Syncing Facebook content...")
        fb_result = sync_facebook_content()
        total_processed += fb_result.get("processed", 0)
        total_success += fb_result.get("success", 0)
        total_failed += fb_result.get("failed", 0)
        
        # Sync Instagram content
        print(f"  Syncing Instagram content...")
        ig_result = sync_instagram_content()
        total_processed += ig_result.get("processed", 0)
        total_success += ig_result.get("success", 0)
        total_failed += ig_result.get("failed", 0)
        
        log_task_complete(
            task.id, True, 
            f"Synced content from all platforms",
            total_processed, total_success, total_failed
        )
        
    except Exception as e:
        log_task_complete(task.id, False, str(e))
        raise


def sync_tiktok_content() -> dict:
    """Sync TikTok posts (latest pages only, for testing/MVP)."""
    access_token = TikTokService.get_access_token()
    business_id = TikTokService.get_business_id()

    if not access_token or not business_id:
        print("TikTok content sync skipped: missing access_token or business_id")
        return {"processed": 0, "success": 0, "failed": 0}

    result = TikTokService.fetch_and_sync_all_videos(
        access_token,
        business_id,
        fetch_type="latest",  # limit to a few pages for test
    )

    return {
        "processed": result.get("total_fetched", 0),
        "success": result.get("total_synced", 0),
        "failed": max(result.get("total_fetched", 0) - result.get("total_synced", 0), 0),
    }


def _load_content_sync_config(db: SessionLocal) -> dict:
    """
    Load content/organic refresh config จาก AppSetting (category='content_sync').
    ถ้าไม่มีค่าจะใช้ default:
      - organic_refresh_max_days = 7
      - max_content_per_job = 100
    """
    rows = (
        db.query(AppSetting)
        .filter(AppSetting.category == "content_sync")
        .all()
    )
    mapping = {row.key: row.value for row in rows if row.value is not None}

    def iv(key: str, default: int) -> int:
        try:
            return int(mapping.get(key, default))
        except (TypeError, ValueError):
            return default

    return {
        "organic_refresh_max_days": iv("organic_refresh_max_days", 7),
        "max_content_per_job": iv("max_content_per_job", 100),
    }


def refresh_tiktok_organic() -> dict:
    """
    Organic refresh job สำหรับ TikTok:
    - เลือก content จากตาราง contents (platform = TIKTOK)
      ที่อายุโพสต์ไม่เกิน organic_refresh_max_days ล่าสุด
      และจำกัดจำนวนตาม max_content_per_job
    - เรียก external API เพื่อดึง item details (รวม bookmarks)
    - อัปเดต metrics + PFM ผ่าน TikTokService.update_content_details
    """
    task = log_task_start("refresh_tiktok_organic", "sync")
    db = SessionLocal()

    try:
        cfg = _load_content_sync_config(db)
        max_days = cfg["organic_refresh_max_days"]
        max_items = cfg["max_content_per_job"]

        now = datetime.utcnow()
        min_created_at = now - timedelta(days=max_days)

        # เลือกเฉพาะ TikTok content ที่ยังไม่ถูกลบ และอยู่ในช่วงวันที่กำหนด
        query = (
            db.query(Content)
            .filter(
                Content.platform == PlatformEnum.TIKTOK,
                Content.deleted_at.is_(None),
                Content.platform_created_at != None,  # noqa: E711
                Content.platform_created_at >= min_created_at,
            )
            .order_by(Content.platform_created_at.desc())
        )

        contents: List[Content] = query.limit(max_items).all()
        item_ids = [c.platform_post_id for c in contents if c.platform_post_id]

        if not item_ids:
            msg = "No TikTok contents selected for organic refresh"
            log_task_complete(task.id, True, msg, 0, 0, 0)
            return {"processed": 0, "success": 0, "failed": 0, "message": msg}

        print(
            f"Refreshing TikTok organic metrics for {len(item_ids)} items "
            f"(max_days={max_days}, max_items={max_items})..."
        )

        # ดึงรายละเอียด item ทั้งหมด (รวม bookmarks)
        item_details, failed_ids = TikTokService.get_item_details_concurrently(
            item_ids, max_workers=10
        )

        # อัปเดต content ใน DB ด้วยรายละเอียดที่ได้มา
        updated_count = 0
        if item_details:
            updated_count = TikTokService.update_content_details(item_details, db)

        failed_count = len(failed_ids) + max(len(item_ids) - updated_count, 0)

        log_task_complete(
            task.id,
            True,
            f"Organic refresh completed: processed={len(item_ids)}, "
            f"updated={updated_count}, failed={failed_count}",
            items_processed=len(item_ids),
            items_success=updated_count,
            items_failed=failed_count,
        )

        return {
            "processed": len(item_ids),
            "success": updated_count,
            "failed": failed_count,
        }

    except Exception as e:
        log_task_complete(task.id, False, str(e))
        raise
    finally:
        db.close()


def sync_facebook_content() -> dict:
    """Sync Facebook posts"""
    # TODO: Implement Facebook content sync
    # This will use Facebook Graph API to fetch posts
    return {"processed": 0, "success": 0, "failed": 0}


def sync_instagram_content() -> dict:
    """Sync Instagram media"""
    # TODO: Implement Instagram content sync
    # This will use Facebook Graph API (IG endpoint) to fetch media
    return {"processed": 0, "success": 0, "failed": 0}


def sync_all_ads():
    """
    Sync ads from all platforms
    - TikTok campaigns/adgroups/ads
    - Facebook campaigns/adsets/ads
    """
    task = log_task_start("sync_all_ads", "sync")
    
    total_processed = 0
    total_success = 0
    total_failed = 0
    
    try:
        # Sync TikTok ads
        print(f"  Syncing TikTok ads...")
        tiktok_result = sync_tiktok_ads()
        total_processed += tiktok_result.get("processed", 0)
        total_success += tiktok_result.get("success", 0)
        total_failed += tiktok_result.get("failed", 0)
        
        # Sync Facebook ads
        print(f"  Syncing Facebook ads...")
        fb_result = sync_facebook_ads()
        total_processed += fb_result.get("processed", 0)
        total_success += fb_result.get("success", 0)
        total_failed += fb_result.get("failed", 0)
        
        log_task_complete(
            task.id, True,
            f"Synced ads from all platforms",
            total_processed, total_success, total_failed
        )
        
    except Exception as e:
        log_task_complete(task.id, False, str(e))
        raise


def sync_tiktok_ads() -> dict:
    """Sync TikTok campaigns, adgroups, and ads"""
    task = log_task_start("sync_tiktok_ads", "sync")

    try:
        result = TikTokAdsService.sync_all_tiktok_ads(days=31)
        ads = result.get("ads", 0)
        mapped = result.get("mapped_contents", 0)
        ad_accounts = result.get("ad_accounts", 0)

        msg = (
            f"Synced TikTok ads for {ad_accounts} ad_accounts, "
            f"ads={ads}, mapped_contents={mapped}"
        )

        # processed = จำนวน Ads, success = จำนวน content ที่ถูก map อย่างน้อย 1 ad
        log_task_complete(
            task.id,
            True,
            msg,
            items_processed=ads,
            items_success=mapped,
            items_failed=max(ads - mapped, 0),
        )

        return {
            "processed": ads,
            "success": mapped,
            "failed": max(ads - mapped, 0),
        }

    except Exception as e:
        log_task_complete(task.id, False, str(e))
        raise


def sync_facebook_ads() -> dict:
    """Sync Facebook campaigns, adsets, and ads"""
    # TODO: Implement Facebook ads sync
    # This will:
    # 1. Fetch campaigns from Graph API
    # 2. Fetch adsets
    # 3. Fetch ads
    # 4. Fetch insights
    # 5. Map ads to content (via object_story_id)
    # 6. Update local database
    return {"processed": 0, "success": 0, "failed": 0}

