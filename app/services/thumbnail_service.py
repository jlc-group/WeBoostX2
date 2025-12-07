"""
Thumbnail Service - จัดการ thumbnail URLs ให้แสดงได้ถาวร

TikTok thumbnail URLs หมดอายุหลังจาก 24-48 ชั่วโมง
Service นี้จะ:
1. ตรวจสอบว่ามี local thumbnail หรือไม่
2. ถ้ามีให้ใช้ local path
3. ถ้าไม่มีให้ใช้ URL จาก platform (และ queue download ไว้ทำทีหลัง)
"""

import os
import httpx
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

# Thumbnail storage directory
THUMBNAIL_DIR = Path(__file__).parent.parent / "static" / "thumbnails"


def get_thumbnail_filename(platform: str, post_id: str) -> str:
    """Generate thumbnail filename from platform and post_id"""
    safe_post_id = "".join(c for c in str(post_id) if c.isalnum() or c in "-_")
    return f"{platform}_{safe_post_id}.jpg"


def get_local_thumbnail_path(platform: str, post_id: str) -> Path:
    """Get full path for thumbnail file"""
    filename = get_thumbnail_filename(platform, post_id)
    return THUMBNAIL_DIR / filename


def get_local_thumbnail_url(platform: str, post_id: str) -> Optional[str]:
    """
    Get local thumbnail URL if file exists
    Returns URL path like /static/thumbnails/tiktok_123456.jpg
    """
    local_path = get_local_thumbnail_path(platform, post_id)
    if local_path.exists():
        filename = get_thumbnail_filename(platform, post_id)
        return f"/static/thumbnails/{filename}"
    return None


def get_thumbnail_url(platform: str, post_id: str, remote_url: Optional[str] = None) -> str:
    """
    Get best available thumbnail URL
    Priority:
    1. Local thumbnail (never expires)
    2. Remote URL from platform (may expire)
    3. Placeholder
    """
    # Try local first
    local_url = get_local_thumbnail_url(platform, post_id)
    if local_url:
        return local_url
    
    # Fall back to remote URL
    if remote_url:
        return remote_url
    
    # Default placeholder
    return "/static/placeholder.svg"


def download_thumbnail(url: str, platform: str, post_id: str, force: bool = False) -> bool:
    """
    Download thumbnail from URL and save to local storage
    
    Returns:
        True if download successful or already exists
        False if failed
    """
    if not url:
        return False
    
    filepath = get_local_thumbnail_path(platform, post_id)
    
    # Skip if exists (unless force)
    if filepath.exists() and not force:
        return True
    
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(url)
            
            if response.status_code != 200:
                return False
            
            # Check if it's an image
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return False
            
            # Save to file
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_bytes(response.content)
            return True
            
    except Exception:
        return False


def download_thumbnail_async(url: str, platform: str, post_id: str):
    """
    Download thumbnail in background (fire and forget)
    Used during API responses to download missing thumbnails
    """
    if not url:
        return
    
    filepath = get_local_thumbnail_path(platform, post_id)
    if filepath.exists():
        return
    
    # Use thread pool for non-blocking download
    try:
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(download_thumbnail, url, platform, post_id, False)
    except Exception:
        pass


def process_content_thumbnail(content) -> str:
    """
    Process content object and return best thumbnail URL
    Also triggers async download if local not available
    """
    platform = content.platform.value if content.platform else "unknown"
    post_id = content.platform_post_id or str(content.id)
    remote_url = content.thumbnail_url
    
    # Get best URL
    thumb_url = get_thumbnail_url(platform, post_id, remote_url)
    
    # If using remote URL, trigger async download for next time
    if thumb_url == remote_url and remote_url:
        download_thumbnail_async(remote_url, platform, post_id)
    
    return thumb_url


def batch_process_thumbnails(contents: list) -> dict:
    """
    Process multiple contents and return mapping of content_id -> thumbnail_url
    """
    result = {}
    for content in contents:
        result[content.id] = process_content_thumbnail(content)
    return result

