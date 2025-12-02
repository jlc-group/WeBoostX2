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
        ads_without_item = result.get("ads_without_item_id", 0)
        item_ids_total = result.get("item_ids_total", 0)
        detail_failed = result.get("item_detail_failed", 0)
        unresolved = result.get("item_ids_unresolved", 0)

        msg = (
            f"Synced TikTok ads for {ad_accounts} ad_accounts, "
            f"ads={ads}, mapped_contents={mapped}, "
            f"ads_without_item_id={ads_without_item}, "
            f"item_ids_total={item_ids_total}, "
            f"item_detail_failed={detail_failed}, "
            f"item_ids_unresolved={unresolved}"
        )

        # processed = จำนวน Ads, success = จำนวน content ที่ถูก map อย่างน้อย 1 ad
        # failed โฟกัสที่ item detail failed + unresolved item_ids
        log_task_complete(
            task.id,
            True,
            msg,
            items_processed=ads,
            items_success=mapped,
            items_failed=detail_failed + unresolved,
        )

        return {
            "processed": ads,
            "success": mapped,
            "failed": detail_failed + unresolved,
            "ads_without_item_id": ads_without_item,
            "item_ids_total": item_ids_total,
            "item_detail_failed": detail_failed,
            "item_ids_unresolved": unresolved,
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


def sync_ads_spend_data():
    """
    Sync ads spend data from TikTok Report API (Lifetime spend)
    
    This task should run HOURLY to keep ad costs up-to-date.
    
    Flow:
    1. ดึง advertiser_ids จากฐานข้อมูล
    2. เรียก TikTok Report API เพื่อดึง lifetime spend ของทุก ad
    3. อัพเดท ad_total_cost ใน ads_details ของ Content
    4. คำนวณและอัพเดท ads_total_cost รวมของ Content
    """
    task = log_task_start("sync_ads_spend_data", "sync")
    
    db = SessionLocal()
    try:
        from app.models import AdAccount
        from app.services.tiktok_ads_service import TikTokAdsService
        import json
        
        # Get all active TikTok ad accounts
        accounts = db.query(AdAccount).filter(
            AdAccount.platform == PlatformEnum.TIKTOK,
            AdAccount.status == "active"
        ).all()
        
        if not accounts:
            log_task_complete(task.id, True, "No active TikTok ad accounts found", 0, 0, 0)
            return {"processed": 0, "success": 0, "failed": 0}
        
        # Fetch lifetime spend for all ads
        all_ad_spend = {}  # {ad_id: total_spend}
        
        for account in accounts:
            print(f"  Fetching spend data for account: {account.name} ({account.external_account_id})")
            try:
                spend_data = TikTokAdsService.fetch_lifetime_spend(account.external_account_id)
                for ad_id, spend in spend_data.items():
                    if ad_id not in all_ad_spend:
                        all_ad_spend[ad_id] = 0.0
                    all_ad_spend[ad_id] += spend
            except Exception as e:
                print(f"  Error fetching spend for {account.external_account_id}: {e}")
        
        print(f"  Total ads with spend data: {len(all_ad_spend)}")
        
        # Update ads_details in Content with ad_total_cost
        updated_contents = 0
        contents = db.query(Content).filter(
            Content.ads_details.isnot(None),
            Content.deleted_at.is_(None)
        ).all()
        
        for content in contents:
            try:
                ads_details = content.ads_details
                if not ads_details:
                    continue
                
                # Handle format: {'tiktok': [...]} or [...]
                ads_list = []
                if isinstance(ads_details, dict):
                    for platform, ads in ads_details.items():
                        if isinstance(ads, list):
                            ads_list = ads
                            break
                elif isinstance(ads_details, list):
                    ads_list = ads_details
                
                if not ads_list:
                    continue
                
                # Update ad_total_cost for each ad
                total_cost = 0.0
                changed = False
                
                for ad in ads_list:
                    if isinstance(ad, dict):
                        ad_id = ad.get('ad_id')
                        if ad_id and ad_id in all_ad_spend:
                            new_cost = all_ad_spend[ad_id]
                            old_cost = ad.get('ad_total_cost', 0)
                            if new_cost != old_cost:
                                ad['ad_total_cost'] = new_cost
                                changed = True
                            total_cost += new_cost
                        else:
                            total_cost += float(ad.get('ad_total_cost', 0) or 0)
                
                # Update Content - ALWAYS update to ensure ad_total_cost is saved
                # Re-pack ads_details with updated ad_total_cost
                if isinstance(content.ads_details, dict):
                    platform_key = list(content.ads_details.keys())[0] if content.ads_details else 'tiktok'
                    content.ads_details = {platform_key: ads_list}
                else:
                    content.ads_details = ads_list
                
                content.ads_total_cost = total_cost
                
                # Force SQLAlchemy to detect JSON change
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(content, 'ads_details')
                
                # Also update ace_details and abx_details with new spend data
                # ACE: ads created by our system with _ACE_ pattern
                # ABX: ads created by our system with _ABX_ pattern
                # General: ads created directly in TikTok Ads Manager (not counted)
                ace_ads = []
                abx_ads = []
                for ad in ads_list:
                    if isinstance(ad, dict):
                        ad_name = (ad.get('ad_name') or '').upper()
                        campaign_name = (ad.get('campaign_name') or '').upper()
                        adgroup_name = (ad.get('adgroup_name') or '').upper()
                        
                        if '_ABX_' in ad_name or '_ABX_' in campaign_name or '_ABX_' in adgroup_name:
                            ad['type'] = 'ABX'
                            abx_ads.append(ad)
                        elif '_ACE_' in ad_name or '_ACE_' in campaign_name or '_ACE_' in adgroup_name:
                            ad['type'] = 'ACE'
                            ace_ads.append(ad)
                        else:
                            ad['type'] = 'GENERAL'
                            # Don't add to ace_ads or abx_ads - these are General ads
                
                content.ace_ad_count = len(ace_ads)
                content.ace_details = ace_ads if ace_ads else None
                content.abx_ad_count = len(abx_ads)
                content.abx_details = abx_ads if abx_ads else None
                flag_modified(content, 'ace_details')
                flag_modified(content, 'abx_details')
                
                updated_contents += 1
                    
            except Exception as e:
                print(f"  Error updating content {content.id}: {e}")
        
        db.commit()
        
        msg = f"Updated spend data for {updated_contents} contents from {len(all_ad_spend)} ads"
        log_task_complete(task.id, True, msg, len(contents), updated_contents, 0)
        
        return {
            "processed": len(contents),
            "success": updated_contents,
            "failed": 0,
            "total_ads_with_spend": len(all_ad_spend)
        }
        
    except Exception as e:
        log_task_complete(task.id, False, str(e))
        raise
    finally:
        db.close()


def update_all_ads_total_cost():
    """
    อัพเดท ads_total_cost จาก ads_details ในฐานข้อมูล
    
    คำนวณ SUM(ad_total_cost) จาก ads_details และอัพเดท ads_total_cost ใน Content
    
    This can run after sync_ads_spend_data or independently
    """
    task = log_task_start("update_all_ads_total_cost", "calc")
    
    db = SessionLocal()
    try:
        from sqlalchemy import text
        
        # Update ads_total_cost by summing ad_total_cost from ads_details
        # Handle both {'tiktok': [...]} and [...] formats
        result = db.execute(text("""
            UPDATE contents
            SET ads_total_cost = COALESCE(subquery.total_cost, 0)
            FROM (
                SELECT 
                    id,
                    SUM(COALESCE((ad_detail->>'ad_total_cost')::numeric, 0)) AS total_cost
                FROM (
                    SELECT 
                        id,
                        -- Handle {'platform': [...]} format
                        CASE 
                            WHEN jsonb_typeof(ads_details) = 'object' THEN 
                                jsonb_array_elements(
                                    COALESCE(
                                        ads_details->'tiktok',
                                        ads_details->'facebook', 
                                        ads_details->'instagram',
                                        '[]'::jsonb
                                    )
                                )
                            -- Handle [...] format
                            WHEN jsonb_typeof(ads_details) = 'array' THEN
                                jsonb_array_elements(ads_details)
                            ELSE
                                NULL
                        END AS ad_detail
                    FROM contents
                    WHERE 
                        ads_details IS NOT NULL
                        AND ads_details != 'null'::jsonb
                        AND ads_details != '[]'::jsonb
                        AND ads_details != '{}'::jsonb
                        AND deleted_at IS NULL
                ) AS details
                WHERE ad_detail IS NOT NULL
                GROUP BY id
            ) AS subquery
            WHERE contents.id = subquery.id
        """))
        
        db.commit()
        
        # Get count of updated rows
        updated = result.rowcount if result else 0
        
        msg = f"Updated ads_total_cost for {updated} contents"
        log_task_complete(task.id, True, msg, updated, updated, 0)
        
        return {"processed": updated, "success": updated, "failed": 0}
        
    except Exception as e:
        db.rollback()
        log_task_complete(task.id, False, str(e))
        raise
    finally:
        db.close()


def update_ace_abx_details():
    """
    Update ace_ad_count, abx_ad_count, ace_details, abx_details from ads_details.
    
    Classifies ads as ACE or ABX based on naming pattern:
    - ACE: ad_name contains "_ACE_"
    - ABX: ad_name contains "_ABX_"
    
    Based on old system logic from hourly_tasks.py
    """
    task = log_task_start("update_ace_abx_details", "calc")
    
    db = SessionLocal()
    try:
        from sqlalchemy import text
        
        # Update ace_ad_count and ace_details for ads with _ACE_ in name
        db.execute(text("""
            WITH ace_data AS (
                SELECT 
                    c.id,
                    COALESCE(
                        jsonb_agg(ad_detail) FILTER (
                            WHERE UPPER(ad_detail->>'ad_name') LIKE '%_ACE_%'
                               OR UPPER(ad_detail->>'campaign_name') LIKE '%_ACE_%'
                               OR UPPER(ad_detail->>'adgroup_name') LIKE '%_ACE_%'
                        ),
                        '[]'::jsonb
                    ) AS ace_details,
                    COUNT(*) FILTER (
                        WHERE UPPER(ad_detail->>'ad_name') LIKE '%_ACE_%'
                           OR UPPER(ad_detail->>'campaign_name') LIKE '%_ACE_%'
                           OR UPPER(ad_detail->>'adgroup_name') LIKE '%_ACE_%'
                    ) AS ace_count
                FROM contents c
                CROSS JOIN LATERAL (
                    SELECT jsonb_array_elements(
                        CASE 
                            WHEN jsonb_typeof(c.ads_details) = 'object' THEN 
                                COALESCE(c.ads_details->'tiktok', c.ads_details->'facebook', '[]'::jsonb)
                            WHEN jsonb_typeof(c.ads_details) = 'array' THEN c.ads_details
                            ELSE '[]'::jsonb
                        END
                    ) AS ad_detail
                ) AS ads
                WHERE c.ads_details IS NOT NULL 
                  AND c.deleted_at IS NULL
                GROUP BY c.id
            )
            UPDATE contents
            SET 
                ace_ad_count = ace_data.ace_count,
                ace_details = CASE WHEN ace_data.ace_count > 0 THEN ace_data.ace_details ELSE NULL END
            FROM ace_data
            WHERE contents.id = ace_data.id
        """))
        
        # Update abx_ad_count and abx_details for ads with _ABX_ in name
        db.execute(text("""
            WITH abx_data AS (
                SELECT 
                    c.id,
                    COALESCE(
                        jsonb_agg(ad_detail) FILTER (
                            WHERE UPPER(ad_detail->>'ad_name') LIKE '%_ABX_%'
                               OR UPPER(ad_detail->>'campaign_name') LIKE '%_ABX_%'
                               OR UPPER(ad_detail->>'adgroup_name') LIKE '%_ABX_%'
                        ),
                        '[]'::jsonb
                    ) AS abx_details,
                    COUNT(*) FILTER (
                        WHERE UPPER(ad_detail->>'ad_name') LIKE '%_ABX_%'
                           OR UPPER(ad_detail->>'campaign_name') LIKE '%_ABX_%'
                           OR UPPER(ad_detail->>'adgroup_name') LIKE '%_ABX_%'
                    ) AS abx_count
                FROM contents c
                CROSS JOIN LATERAL (
                    SELECT jsonb_array_elements(
                        CASE 
                            WHEN jsonb_typeof(c.ads_details) = 'object' THEN 
                                COALESCE(c.ads_details->'tiktok', c.ads_details->'facebook', '[]'::jsonb)
                            WHEN jsonb_typeof(c.ads_details) = 'array' THEN c.ads_details
                            ELSE '[]'::jsonb
                        END
                    ) AS ad_detail
                ) AS ads
                WHERE c.ads_details IS NOT NULL 
                  AND c.deleted_at IS NULL
                GROUP BY c.id
            )
            UPDATE contents
            SET 
                abx_ad_count = abx_data.abx_count,
                abx_details = CASE WHEN abx_data.abx_count > 0 THEN abx_data.abx_details ELSE NULL END
            FROM abx_data
            WHERE contents.id = abx_data.id
        """))
        
        db.commit()
        
        # Count updated contents
        result = db.execute(text("""
            SELECT COUNT(*) FROM contents 
            WHERE ads_details IS NOT NULL AND deleted_at IS NULL
        """))
        count = result.scalar() or 0
        
        msg = f"Updated ACE/ABX details for {count} contents"
        log_task_complete(task.id, True, msg, count, count, 0)
        
        return {"processed": count, "success": count, "failed": 0}
        
    except Exception as e:
        db.rollback()
        log_task_complete(task.id, False, str(e))
        raise
    finally:
        db.close()