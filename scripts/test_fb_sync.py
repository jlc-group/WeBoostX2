"""
Test Facebook Sync - ทดสอบ sync ข้อมูลจาก Facebook
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.services.facebook.fb_api import FacebookAPI
from app.services.facebook.fb_sync import FacebookSyncService


async def test_api_connection():
    """ทดสอบ connection กับ Facebook API"""
    print("=" * 60)
    print("Testing Facebook API Connection")
    print("=" * 60)

    api = FacebookAPI()

    # Check tokens
    print(f"\nPage Access Token: {'SET' if api.page_access_token else 'NOT SET'}")
    print(f"User Access Token: {'SET' if api.user_access_token else 'NOT SET'}")

    # Get page IDs from env
    page_ids = FacebookAPI.get_page_ids()
    print(f"Page IDs from env: {page_ids}")

    ad_account_ids = FacebookAPI.get_ad_account_ids()
    print(f"Ad Account IDs from env: {ad_account_ids}")

    if not api.page_access_token:
        print("\n[ERROR] No FB_PAGE_ACCESS_TOKEN or FB_PAGE_ACCESS_TOKENS set!")
        return False

    if not page_ids:
        print("\n[ERROR] No FB_PAGE_IDS set!")
        return False

    # Test fetch posts from first page
    page_id = page_ids[0]
    print(f"\n[INFO] Testing fetch posts from page: {page_id}")

    try:
        posts = await api.fetch_posts(page_id=page_id, days_back=30, limit=5)
        print(f"[OK] Fetched {len(posts)} posts")

        if posts:
            print("\nSample post:")
            post = posts[0]
            print(f"  - ID: {post.get('id')}")
            # Handle unicode safely
            msg = (post.get('message') or 'No message')[:50]
            msg_safe = msg.encode('ascii', 'replace').decode('ascii')
            print(f"  - Message: {msg_safe}...")
            print(f"  - Created: {post.get('created_time')}")
    except Exception as e:
        print(f"[ERROR] Error fetching posts: {e}")
        return False
    finally:
        await api.close()

    return True


async def test_sync_posts():
    """ทดสอบ sync posts to database"""
    print("\n" + "=" * 60)
    print("Testing Facebook Posts Sync to Database")
    print("=" * 60)

    page_ids = FacebookAPI.get_page_ids()
    if not page_ids:
        print("[ERROR] No page IDs configured")
        return

    db = SessionLocal()

    try:
        for page_id in page_ids:
            print(f"\n[SYNC] Syncing posts from page: {page_id}")

            sync_service = FacebookSyncService(db=db)

            try:
                stats = await sync_service.sync_posts(
                    page_id=page_id,
                    days_back=90,  # Last 90 days
                )

                print(f"[OK] Sync complete:")
                print(f"   - Created: {stats.get('created', 0)}")
                print(f"   - Updated: {stats.get('updated', 0)}")
                print(f"   - Skipped: {stats.get('skipped', 0)}")
                print(f"   - Errors: {stats.get('errors', 0)}")

            except Exception as e:
                print(f"[ERROR] Error syncing page {page_id}: {e}")
            finally:
                await sync_service.close()

    finally:
        db.close()


async def test_sync_videos():
    """ทดสอบ sync videos to database"""
    print("\n" + "=" * 60)
    print("Testing Facebook Videos Sync to Database")
    print("=" * 60)

    page_ids = FacebookAPI.get_page_ids()
    if not page_ids:
        print("[ERROR] No page IDs configured")
        return

    db = SessionLocal()

    try:
        for page_id in page_ids:
            print(f"\n[SYNC] Syncing videos from page: {page_id}")

            sync_service = FacebookSyncService(db=db)

            try:
                stats = await sync_service.sync_video_posts(
                    page_id=page_id,
                    days_back=365,  # Last year
                )

                print(f"[OK] Video sync complete:")
                print(f"   - Created: {stats.get('created', 0)}")
                print(f"   - Updated: {stats.get('updated', 0)}")
                print(f"   - Errors: {stats.get('errors', 0)}")

            except Exception as e:
                print(f"[ERROR] Error syncing videos from {page_id}: {e}")
            finally:
                await sync_service.close()

    finally:
        db.close()


async def main():
    """Main test function"""
    print("\n[START] Facebook Sync Test Script")
    print("=" * 60)

    # Test API connection first
    if not await test_api_connection():
        print("\n[FAILED] API connection test failed. Please check your tokens.")
        return

    # Sync posts
    await test_sync_posts()

    # Sync videos
    await test_sync_videos()

    print("\n" + "=" * 60)
    print("[DONE] All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
