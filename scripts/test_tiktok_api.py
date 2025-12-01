"""
Quick script to test TikTok config + API connectivity.

วิธีใช้:
    python scripts/test_tiktok_api.py

จะ:
    - อ่านค่า config จาก .env
    - แสดง access token/business id (แบบ mask)
    - ยิง TikTok Business API /business/video/list/ 1 หน้า
    - แสดงจำนวนวิดีโอที่ดึงได้ หรือแสดง error จาก API
"""

from pprint import pprint

from app.core.config import settings
from app.services.tiktok_service import TikTokService


def mask(value: str, keep: int = 4) -> str:
    """Mask secret values for safe printing."""
    if not value:
        return ""
    if len(value) <= keep * 2:
        return "*" * len(value)
    return value[:keep] + "*" * (len(value) - keep * 2) + value[-keep:]


def main() -> None:
    print("=== TikTok Config Test ===")
    print(f"ENVIRONMENT: {settings.ENVIRONMENT}")

    # Effective values used by the app
    access_token = TikTokService.get_access_token()
    business_id = TikTokService.get_business_id()

    print("\n[Effective settings]")
    print(f"- access_token obtained: {bool(access_token)}")
    print(f"- tiktok_business_id: {business_id!r}")

    # Also show raw env-backed fields for debugging
    print("\n[Raw env fields]")
    print(f"TIKTOK_ACCESS_TOKEN set: {bool(settings.TIKTOK_ACCESS_TOKEN)}")
    print(f"TIKTOK_MAIN_ACCESS_TOKEN set: {bool(settings.TIKTOK_MAIN_ACCESS_TOKEN)}")
    print(f"TIKTOK_AD_TOKEN set: {bool(settings.TIKTOK_AD_TOKEN)}")
    print(f"TIKTOK_CLIENT_ID set: {bool(settings.TIKTOK_CLIENT_ID)}")
    print(f"TIKTOK_CLIENT_SECRET set: {bool(settings.TIKTOK_CLIENT_SECRET)}")
    print(f"TIKTOK_REFRESH_TOKEN set: {bool(settings.TIKTOK_REFRESH_TOKEN)}")
    print(f"TIKTOK_BUSINESS_ID: {settings.TIKTOK_BUSINESS_ID!r}")
    print(f"BUSINESS_ID: {settings.BUSINESS_ID!r}")

    if not access_token or not business_id:
        print("\n!! Missing access_token or business_id – กรุณาเช็คค่าใน .env อีกครั้ง")
        return

    print("\nAccess token (masked):", mask(access_token))
    print("Business ID:", business_id)

    print("\n=== Calling TikTok /business/video/list/ ===")
    resp = TikTokService.get_videos_list(access_token, business_id)

    if resp is None:
        print("API call FAILED: got None (อาจเป็นเรื่อง network หรือ token ผิด)")
        return

    print("\nRaw response (trimmed keys):")
    if isinstance(resp, dict):
        pprint({k: resp[k] for k in list(resp.keys())[:10]})

    # Try to inspect standard TikTok response structure
    data = resp.get("data") if isinstance(resp, dict) else None
    if data:
        videos = data.get("videos") or []
        has_more = data.get("has_more")
        cursor = data.get("cursor")
        print(f"\nVideos fetched: {len(videos)}")
        print(f"has_more: {has_more}, cursor: {cursor}")
        if videos:
            print("ตัวอย่าง video แรก (fields หลัก ๆ):")
            v0 = videos[0]
            summary = {
                "item_id": v0.get("item_id"),
                "create_time": v0.get("create_time"),
                "caption": (v0.get("caption") or "")[:60],
                "video_views": v0.get("video_views"),
                "likes": v0.get("likes"),
                "comments": v0.get("comments"),
                "shares": v0.get("shares"),
            }
            pprint(summary)
    else:
        print("\nNo 'data' field in response, full response:")
        pprint(resp)


if __name__ == "__main__":
    main()


