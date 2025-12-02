"""
One-off script สำหรับ backfill TikTok Ads (ทุก advertiser) และ map กลับไปหา Content

ใช้ครั้งแรกเพื่อดึง Ads ทั้งประวัติ (หรือเท่าที่ API ยอมให้ดึงได้) เข้าระบบ
หลังจากนั้นให้ใช้ปุ่ม Sync All Ads ในหน้า Jobs สำหรับรันประจำ (ช่วง 30 วันล่าสุด)

วิธีใช้ (จาก Project root):

    PowerShell:
        $env:PYTHONPATH = 'D:\GitHubCode\WeBoostX2'
        C:\Python382\python.exe scripts\backfill_tiktok_ads.py

สคริปต์นี้จะ:
    - ใช้ TikTokAdsService.sync_all_tiktok_ads(days=-1)
      (days <= 0 แปลว่าไม่จำกัดช่วงวัน ดึงให้มากที่สุดเท่าที่ API ให้)
    - สร้าง/อัปเดต Campaign, AdGroup, Ad
    - map Ads กลับไปหา Content (รวมถึงสร้าง Content ใหม่ให้ item_id ที่ยังไม่มี)
    - เขียน log ลงตาราง task_logs ด้วยชื่อ task ว่า "backfill_tiktok_ads"
"""

import logging

from app.services.tiktok_ads_service import TikTokAdsService
from app.tasks.sync_tasks import log_task_start, log_task_complete


# ลดความลายตาของ log: ซ่อน SQL query รายบรรทัด เหลือเฉพาะ print ของเราเอง
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def main() -> None:
    print("=== Backfill TikTok Ads (FULL HISTORY) ===")
    print("คำเตือน: การดึง Ads ทั้งประวัติอาจใช้เวลานาน ขึ้นกับจำนวนบัญชีและโฆษณา")

    task = log_task_start("backfill_tiktok_ads", "sync")

    try:
        print("\n=== เริ่มดึง TikTok Ads แบบ FULL (days=-1) สำหรับทุก Ad Account (TikTok) ===")
        result = TikTokAdsService.sync_all_tiktok_ads(days=-1)

        ads = int(result.get("ads", 0) or 0)
        mapped = int(result.get("mapped_contents", 0) or 0)
        ad_accounts = int(result.get("ad_accounts", 0) or 0)
        ads_without_item = int(result.get("ads_without_item_id", 0) or 0)
        item_ids_total = int(result.get("item_ids_total", 0) or 0)
        detail_failed = int(result.get("item_detail_failed", 0) or 0)
        unresolved = int(result.get("item_ids_unresolved", 0) or 0)
        failed = detail_failed + unresolved

        print(
            f"\nProgress summary: ad_accounts={ad_accounts}, "
            f"ads={ads}, mapped_contents={mapped}, "
            f"ads_without_item_id={ads_without_item}, "
            f"item_ids_total={item_ids_total}, "
            f"item_detail_failed={detail_failed}, "
            f"item_ids_unresolved={unresolved}, "
            f"failed={failed}"
        )

        message = (
            f"Backfill TikTok ads completed. "
            f"ad_accounts={ad_accounts}, ads={ads}, mapped_contents={mapped}, "
            f"ads_without_item_id={ads_without_item}, "
            f"item_ids_total={item_ids_total}, "
            f"item_detail_failed={detail_failed}, "
            f"item_ids_unresolved={unresolved}, "
            f"failed={failed}"
        )

        log_task_complete(
            task_id=task.id,
            success=True,
            message=message,
            items_processed=ads,
            items_success=mapped,
            items_failed=failed,
        )

        print("\n=== SUMMARY ===")
        print(message)

    except Exception as e:
        log_task_complete(
            task_id=task.id,
            success=False,
            message=str(e),
            items_processed=0,
            items_success=0,
            items_failed=0,
        )
        print("\n!!! ERROR ระหว่าง backfill TikTok Ads")
        print(e)
        raise


if __name__ == "__main__":
    main()


