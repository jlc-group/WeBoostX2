#!/usr/bin/env python
"""
Script: Download TikTok thumbnails เก็บไว้ใน local storage

TikTok thumbnail URLs หมดอายุหลังจาก 24-48 ชั่วโมง
Script นี้จะ download thumbnails มาเก็บไว้ใน static/thumbnails/
เพื่อให้แสดงรูปได้ตลอด

วิธีใช้:
    PowerShell:
        $env:PYTHONPATH = 'D:\GitHubCode\WeBoostX2'
        C:\Python382\python.exe scripts\download_thumbnails.py

    Options:
        --limit N     : จำกัดจำนวน (default: ไม่จำกัด)
        --force       : Download ทับไฟล์เดิม
        --platform X  : เฉพาะ platform (tiktok, facebook, instagram)
"""

import os
import sys
import argparse
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.models import Content
from app.models.enums import Platform


# Thumbnail storage directory
THUMBNAIL_DIR = Path(__file__).parent.parent / "app" / "static" / "thumbnails"


def get_thumbnail_filename(platform: str, post_id: str) -> str:
    """
    Generate thumbnail filename from platform and post_id
    Format: {platform}_{post_id}.jpg
    """
    # Sanitize post_id for filename (remove any special chars)
    safe_post_id = "".join(c for c in post_id if c.isalnum() or c in "-_")
    return f"{platform}_{safe_post_id}.jpg"


def get_thumbnail_path(platform: str, post_id: str) -> Path:
    """Get full path for thumbnail file"""
    filename = get_thumbnail_filename(platform, post_id)
    return THUMBNAIL_DIR / filename


def thumbnail_exists(platform: str, post_id: str) -> bool:
    """Check if thumbnail already downloaded"""
    return get_thumbnail_path(platform, post_id).exists()


def download_thumbnail(url: str, platform: str, post_id: str, force: bool = False) -> bool:
    """
    Download thumbnail from URL and save to local storage
    
    Returns:
        True if download successful or already exists
        False if failed
    """
    if not url:
        return False
    
    filepath = get_thumbnail_path(platform, post_id)
    
    # Skip if exists (unless force)
    if filepath.exists() and not force:
        return True
    
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            
            if response.status_code != 200:
                print(f"  [FAIL] HTTP {response.status_code} for {post_id}")
                return False
            
            # Check if it's an image
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                print(f"  [FAIL] Not an image ({content_type}) for {post_id}")
                return False
            
            # Save to file
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(response.content)
            return True
            
    except Exception as e:
        print(f"  [ERROR] {post_id}: {e}")
        return False


def download_thumbnail_worker(args):
    """Worker function for parallel download"""
    content_id, url, platform, post_id, force = args
    success = download_thumbnail(url, platform, post_id, force)
    return content_id, success


def download_all_thumbnails(
    platform: Optional[str] = None,
    limit: Optional[int] = None,
    force: bool = False,
    workers: int = 10
) -> dict:
    """
    Download thumbnails for all contents
    
    Args:
        platform: Filter by platform (tiktok, facebook, instagram) or None for all
        limit: Limit number of contents
        force: Force re-download existing thumbnails
        workers: Number of parallel workers
    
    Returns:
        Dict with statistics
    """
    db = SessionLocal()
    
    try:
        print(f"[{datetime.now()}] Starting thumbnail download...")
        print(f"  Platform: {platform or 'all'}")
        print(f"  Force: {force}")
        print(f"  Workers: {workers}")
        
        # Build query
        query = db.query(Content).filter(
            Content.deleted_at.is_(None),
            Content.thumbnail_url.isnot(None),
            Content.thumbnail_url != ""
        )
        
        if platform:
            platform_enum = Platform(platform.lower())
            query = query.filter(Content.platform == platform_enum)
        
        # Order by most recent first
        query = query.order_by(Content.platform_created_at.desc().nullslast())
        
        if limit:
            query = query.limit(limit)
        
        contents = query.all()
        
        print(f"  Found {len(contents)} contents with thumbnail URLs")
        
        if not contents:
            return {"total": 0, "downloaded": 0, "skipped": 0, "failed": 0}
        
        # Prepare download tasks
        tasks = []
        skipped = 0
        
        for content in contents:
            platform_str = content.platform.value if content.platform else "unknown"
            post_id = content.platform_post_id or str(content.id)
            
            # Skip if already exists (unless force)
            if not force and thumbnail_exists(platform_str, post_id):
                skipped += 1
                continue
            
            tasks.append((
                content.id,
                content.thumbnail_url,
                platform_str,
                post_id,
                force
            ))
        
        print(f"  Skipped (already exists): {skipped}")
        print(f"  To download: {len(tasks)}")
        
        if not tasks:
            return {"total": len(contents), "downloaded": 0, "skipped": skipped, "failed": 0}
        
        # Download in parallel
        downloaded = 0
        failed = 0
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(download_thumbnail_worker, task): task for task in tasks}
            
            for i, future in enumerate(as_completed(futures), 1):
                content_id, success = future.result()
                
                if success:
                    downloaded += 1
                else:
                    failed += 1
                
                # Progress update every 100
                if i % 100 == 0:
                    print(f"  Progress: {i}/{len(tasks)} (downloaded={downloaded}, failed={failed})")
        
        stats = {
            "total": len(contents),
            "downloaded": downloaded,
            "skipped": skipped,
            "failed": failed
        }
        
        print(f"\n[{datetime.now()}] Completed!")
        print(f"  Total: {stats['total']}")
        print(f"  Downloaded: {stats['downloaded']}")
        print(f"  Skipped: {stats['skipped']}")
        print(f"  Failed: {stats['failed']}")
        
        return stats
        
    except Exception as e:
        print(f"[ERROR] {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description='Download TikTok thumbnails to local storage')
    parser.add_argument('--platform', type=str, choices=['tiktok', 'facebook', 'instagram'],
                        help='Filter by platform')
    parser.add_argument('--limit', type=int, help='Limit number of contents')
    parser.add_argument('--force', action='store_true', help='Force re-download existing')
    parser.add_argument('--workers', type=int, default=10, help='Number of parallel workers')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Download Thumbnails to Local Storage")
    print("=" * 60)
    
    # Ensure directory exists
    THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
    
    stats = download_all_thumbnails(
        platform=args.platform,
        limit=args.limit,
        force=args.force,
        workers=args.workers
    )
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total processed: {stats['total']}")
    print(f"  Downloaded: {stats['downloaded']}")
    print(f"  Skipped (existed): {stats['skipped']}")
    print(f"  Failed: {stats['failed']}")
    print("=" * 60)


if __name__ == "__main__":
    main()

