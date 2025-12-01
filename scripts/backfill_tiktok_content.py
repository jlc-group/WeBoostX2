"""
One-off script สำหรับดึง TikTok Content "ทั้งหมด" (เท่าที่ API อนุญาต) เข้าฐานข้อมูลในครั้งแรก

วิธีใช้ (จาก Project root):

    PowerShell:
        $env:PYTHONPATH = 'D:\GitHubCode\WeBoostX2'
        C:\Python382\python.exe scripts\backfill_tiktok_content.py

สคริปต์นี้จะ:
    - ใช้ TikTokService เพื่อดึง access_token + business_id จาก DB/.env
    - เรียก TikTok Business API แบบ fetch_type="all" (ไล่หลายหน้า)
    - sync ลงตาราง content ผ่าน TikTokService.sync_videos_to_db (upsert)
    - เขียน log ลงตาราง task_logs ด้วยชื่อ task ว่า "backfill_tiktok_content"
      เพื่อให้เห็นในหน้า Jobs ได้เหมือน job อื่น ๆ
"""

import logging
from pprint import pprint

from app.services.tiktok_service import TikTokService
from app.tasks.sync_tasks import log_task_start, log_task_complete

# ลดความลายตาของ log: ซ่อน SQL query รายบรรทัด เหลือเฉพาะ print ของเราเอง
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def mask(value: str, keep: int = 4) -> str:
    """Mask secret values สำหรับแสดงบนหน้าจอแบบปลอดภัย"""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep * 2) + value[-keep:]


def main() -> None:
    print("=== Backfill TikTok Content (FULL) ===")

    access_token = TikTokService.get_access_token()
    business_id = TikTokService.get_business_id()

    print("\n[Effective TikTok settings]")
    print(f"- access_token obtained: {bool(access_token)}")
    print(f"- business_id: {business_id!r}")

    if not access_token or not business_id:
        print("\n!! ขาด access_token หรือ business_id")
        print("   กรุณาเช็คหน้า Settings (TikTok API Config) หรือ .env ให้ครบก่อน")
        return

    print("\nAccess token (masked):", mask(access_token))
    print("Business ID:", business_id)

    # สร้าง task log เพื่อให้เห็นในหน้า Jobs
    task = log_task_start("backfill_tiktok_content", "sync")

    try:
        print("\n=== เริ่มดึง TikTok videos แบบ FULL (fetch_type='all') ===")
        result = TikTokService.fetch_and_sync_all_videos(
            access_token=access_token,
            business_id=business_id,
            fetch_type="all",  # ไล่หลายหน้า มากกว่าปุ่ม Sync ปกติ
        )

        total_fetched = int(result.get("total_fetched", 0) or 0)
        total_synced = int(result.get("total_synced", 0) or 0)
        total_failed = max(total_fetched - total_synced, 0)

        print(
            f"\nProgress summary: fetched={total_fetched}, "
            f"synced={total_synced}, failed={total_failed}"
        )

        success = bool(result.get("success"))
        message = (
            f"Backfill TikTok content completed. "
            f"fetched={total_fetched}, synced={total_synced}, failed={total_failed}"
            if success
            else f"Backfill TikTok content FAILED: {result.get('error') or 'unknown error'}"
        )

        log_task_complete(
            task_id=task.id,
            success=success,
            message=message,
            items_processed=total_fetched,
            items_success=total_synced,
            items_failed=total_failed,
        )

        print("\n=== SUMMARY ===")
        print(message)

    except Exception as e:
        # ถ้ามี exception ระหว่างทาง ให้ mark task เป็น failed
        log_task_complete(
            task_id=task.id,
            success=False,
            message=str(e),
            items_processed=0,
            items_success=0,
            items_failed=0,
        )
        print("\n!!! ERROR ระหว่าง backfill")
        print(e)
        raise


if __name__ == "__main__":
    main()


