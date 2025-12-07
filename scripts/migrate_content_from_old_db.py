#!/usr/bin/env python
"""
Migration Script: Import contents จากฐานข้อมูลเก่า (starcontent) มายังฐานข้อมูลใหม่

สิ่งที่ script นี้ทำ:
1. เชื่อมต่อฐานข้อมูลเก่า (starcontent)
2. ดึงข้อมูลจากตาราง tiktok_posts
3. Transform/Map ข้อมูลให้เข้ากับโครงสร้างใหม่
4. เคลียร์ตาราง contents (optional)
5. Insert ข้อมูลเข้าตาราง contents
6. Download thumbnails (optional)

วิธีใช้:
    PowerShell:
        $env:PYTHONPATH = 'D:\GitHubCode\WeBoostX2'
        C:\Python382\python.exe scripts\migrate_content_from_old_db.py

    Options:
        --no-clear       : ไม่เคลียร์ตาราง contents ก่อน import (default: เคลียร์)
        --no-thumbnail   : ไม่ download thumbnails หลัง import
        --limit N        : จำกัดจำนวน rows (สำหรับทดสอบ)
        --dry-run        : แสดง preview ไม่ทำจริง
        --old-db-url URL : Database URL ของฐานข้อมูลเก่า

ตัวอย่าง:
    # ทดสอบก่อน (limit 10)
    python scripts/migrate_content_from_old_db.py --dry-run --limit 10

    # รันจริง
    python scripts/migrate_content_from_old_db.py
"""

import os
import sys
import argparse
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any

from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import text, create_engine

from app.core.database import SessionLocal, engine
from app.core.config import settings
from app.models import Content
from app.models.enums import Platform, ContentType, ContentSource, ContentStatus


# ============================================
# Configuration
# ============================================

# Load .env.old from old_ref/WeBoostX if exists
DEFAULT_OLD_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "old_ref",
    "WeBoostX",
    ".env.old",
)
if os.path.isfile(DEFAULT_OLD_ENV_PATH):
    load_dotenv(DEFAULT_OLD_ENV_PATH)

# Default old database URL (can override with --old-db-url)
OLD_DB_URL = (
    os.getenv("OLD_DATABASE_URL")
    or os.getenv("OLD_DB_URL")
    or "postgresql://postgres:password@localhost:5432/starcontent"
)


# ============================================
# Content Type Mapping
# ============================================

CONTENT_TYPE_MAP = {
    # Old content_type -> New ContentType enum
    'sale': ContentType.SALE,
    'SALE': ContentType.SALE,
    'review': ContentType.REVIEW,
    'REVIEW': ContentType.REVIEW,
    'branding': ContentType.BRANDING,
    'BRANDING': ContentType.BRANDING,
    'ecom': ContentType.ECOM,
    'ECOM': ContentType.ECOM,
    'e-commerce': ContentType.ECOM,
    'test': ContentType.OTHER,
    'TEST': ContentType.OTHER,
    'other': ContentType.OTHER,
    'OTHER': ContentType.OTHER,
    None: ContentType.OTHER,
    '': ContentType.OTHER,
}

CONTENT_STATUS_MAP = {
    # Old content_status -> New ContentStatus enum
    'ready': ContentStatus.READY,
    'READY': ContentStatus.READY,
    'active': ContentStatus.READY,
    'active_ad': ContentStatus.ACTIVE_AD,
    'ACTIVE_AD': ContentStatus.ACTIVE_AD,
    'test_ad': ContentStatus.TEST_AD,
    'TEST_AD': ContentStatus.TEST_AD,
    'paused': ContentStatus.PAUSED,
    'PAUSED': ContentStatus.PAUSED,
    'expired': ContentStatus.EXPIRED,
    'EXPIRED': ContentStatus.EXPIRED,
    'archived': ContentStatus.DELETED,  # Map archived to deleted
    'ARCHIVED': ContentStatus.DELETED,
    'deleted': ContentStatus.DELETED,
    'DELETED': ContentStatus.DELETED,
    None: ContentStatus.READY,
    '': ContentStatus.READY,
}

CONTENT_SOURCE_MAP = {
    # channel_type (integer) -> ContentSource enum
    1: ContentSource.PAGE,      # Page/Brand account
    2: ContentSource.INFLUENCER,  # Influencer
    3: ContentSource.STAFF,     # Staff/Employee
    None: None,
}


# ============================================
# Helper Functions
# ============================================

def parse_products_json(products_json: Any, products_str: str = None) -> List[str]:
    """
    Parse products from JSON or string format to list of product codes
    
    Old format examples:
    - products_json: ["S1", "D1"] or {"codes": ["S1", "D1"]}
    - products: "S1,D1" or "S1, D1" or "[]"
    """
    result = []
    
    if products_json:
        if isinstance(products_json, list):
            result = [str(p).strip().upper() for p in products_json if p and str(p).strip()]
        elif isinstance(products_json, dict):
            codes = products_json.get('codes') or products_json.get('products') or []
            result = [str(p).strip().upper() for p in codes if p and str(p).strip()]
    
    if not result and products_str:
        # Clean up string format
        clean_str = products_str.strip()
        # Skip if it's empty array notation
        if clean_str in ('[]', '{}', '', 'null', 'None'):
            return []
        # Parse comma-separated string
        result = [p.strip().upper() for p in clean_str.split(',') if p.strip() and p.strip() not in ('[]', '{}')]
    
    # Filter out invalid entries
    result = [p for p in result if p and p not in ('[]', '{}', 'NULL', 'NONE', '')]
    
    return result


def parse_targeting_ids(targeting_details: Any, targeting2_details: Any = None) -> List[int]:
    """
    Extract targeting template IDs from old targeting_details JSON
    
    Old format example:
    - targeting_details: {"id": "MF_SUN_MASS_18_54", ...}
    - targeting2_details: {"id": "M_BKK_25_44", ...}
    """
    ids = []
    
    # ในระบบเก่า targeting_details เก็บเป็น string ID
    # ต้อง lookup จากตาราง targeting_templates ในระบบใหม่
    # สำหรับตอนนี้จะ skip และให้ user map เองทีหลัง
    
    return ids


def map_content_type(old_type: str) -> ContentType:
    """Map old content_type string to new ContentType enum"""
    return CONTENT_TYPE_MAP.get(old_type, ContentType.OTHER)


def map_content_status(old_status: str) -> ContentStatus:
    """Map old content_status string to new ContentStatus enum"""
    return CONTENT_STATUS_MAP.get(old_status, ContentStatus.READY)


def map_content_source(channel_type: int, creator_details: dict = None) -> Optional[ContentSource]:
    """
    Determine content source from channel_type or creator_details
    
    Logic:
    - If creator_details has 'is_influencer': True -> INFLUENCER
    - If creator_details has 'is_staff': True -> STAFF
    - Otherwise use channel_type mapping
    """
    if creator_details:
        if creator_details.get('is_influencer'):
            return ContentSource.INFLUENCER
        if creator_details.get('is_staff') or creator_details.get('is_employee'):
            return ContentSource.STAFF
        if creator_details.get('is_page') or creator_details.get('type') == 'page':
            return ContentSource.PAGE
    
    return CONTENT_SOURCE_MAP.get(channel_type)


def transform_row(row: Dict) -> Dict:
    """
    Transform a row from old tiktok_posts to new contents format
    """
    # Parse products
    product_codes = parse_products_json(
        row.get('products_json'),
        row.get('products')
    )
    
    # Parse creator details
    creator_details = row.get('creator_details') or {}
    if isinstance(creator_details, str):
        import json
        try:
            creator_details = json.loads(creator_details)
        except:
            creator_details = {}
    
    # Calculate completion rate (old is decimal 0-1, new is percentage 0-100)
    completion_rate = row.get('full_video_watched_rate')
    if completion_rate is not None:
        completion_rate = Decimal(str(completion_rate * 100))
    
    # Build new content dict
    return {
        'platform': Platform.TIKTOK,
        'platform_post_id': row['item_id'],
        'url': row.get('url'),
        'caption': row.get('caption'),
        'thumbnail_url': row.get('thumbnail_url'),
        'platform_created_at': row.get('create_time'),
        'platform_updated_at': row.get('update_time'),
        
        # Classification
        'content_type': map_content_type(row.get('content_type')),
        'content_source': map_content_source(row.get('channel_type'), creator_details),
        'status': map_content_status(row.get('content_status')),
        
        # Products
        'product_codes': product_codes if product_codes else None,
        
        # Creator
        'creator_id': row.get('channel_acc_id'),
        'creator_name': row.get('channel_acc_id'),
        'creator_details': creator_details if creator_details else None,
        
        # Metrics
        'video_duration': Decimal(str(row.get('video_duration') or 0)),
        'views': row.get('video_views') or 0,
        'reach': row.get('reach') or 0,
        'likes': row.get('likes') or 0,
        'comments': row.get('comments') or 0,
        'shares': row.get('shares') or 0,
        'saves': row.get('bookmarks') or 0,  # bookmarks -> saves
        'total_watch_time': Decimal(str(row.get('total_time_watched') or 0)),
        'avg_watch_time': Decimal(str(row.get('average_time_watched') or 0)),
        'completion_rate': completion_rate,
        
        # Platform-specific metrics
        'platform_metrics': {
            'impression_sources': row.get('impression_sources'),
            'full_video_watched_rate': row.get('full_video_watched_rate'),
        } if row.get('impression_sources') else None,
        
        # Ad performance
        'ads_total_cost': Decimal(str(row.get('ads_total_media_cost') or 0)),
        'ads_details': row.get('ads_details'),
        'ace_ad_count': row.get('ace_ad_count') or 0,
        'ace_details': row.get('ace_details'),
        'abx_ad_count': row.get('abx_ad_count') or 0,
        'abx_details': row.get('abx_details'),
        
        # Calculate ads_count from ace + abx
        'ads_count': (row.get('ace_ad_count') or 0) + (row.get('abx_ad_count') or 0),
        
        # Scores
        'pfm_score': Decimal(str(row.get('pfm_score') or 0)) if row.get('pfm_score') else None,
        
        # Expiration
        'expire_date': row.get('content_expire_date').date() if row.get('content_expire_date') else None,
        
        # Targeting (will need manual mapping later)
        'preferred_targeting_ids': parse_targeting_ids(
            row.get('targeting_details'),
            row.get('targeting2_details')
        ) or None,
    }


# ============================================
# Main Functions
# ============================================

def fetch_from_old_db(db_url: str, limit: Optional[int] = None) -> List[Dict]:
    """
    Fetch rows from old tiktok_posts table
    """
    print(f"Connecting to old database...")
    
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    query = """
        SELECT 
            item_id,
            create_time,
            update_time,
            channel_acc_id,
            channel_type,
            url,
            caption,
            thumbnail_url,
            video_duration,
            total_time_watched,
            average_time_watched,
            full_video_watched_rate,
            impression_sources,
            reach,
            video_views,
            likes,
            bookmarks,
            comments,
            shares,
            pfm_score,
            products,
            products_json,
            ads_details,
            ads_total_media_cost,
            content_type,
            content_status,
            creator_details,
            abx_ad_count,
            abx_details,
            ace_ad_count,
            ace_details,
            targeting_details,
            targeting2_details,
            content_expire_date
        FROM tiktok_posts
        ORDER BY create_time DESC
    """
    
    if limit:
        query += f" LIMIT {limit}"
    
    cursor.execute(query)
    rows = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    print(f"  Fetched {len(rows)} rows from tiktok_posts")
    return rows


def clear_contents_table(db, dry_run: bool = False) -> int:
    """
    Clear contents table (hard delete for clean import)
    Also clears related tables that have foreign key to contents
    """
    from app.models import Ad, AdGroup, Campaign
    
    if dry_run:
        count = db.query(Content).count()
        print(f"  [DRY RUN] Would delete {count} existing contents")
        return count
    
    # Clear related tables first (foreign key constraints)
    print("  Clearing related tables first...")
    
    # 1. Clear ads (references contents)
    ads_count = db.execute(text("DELETE FROM ads")).rowcount
    print(f"    Deleted {ads_count} ads")
    
    # 2. Clear ad_groups (references campaigns)
    adgroups_count = db.execute(text("DELETE FROM ad_groups")).rowcount
    print(f"    Deleted {adgroups_count} ad_groups")
    
    # 3. Clear campaigns
    campaigns_count = db.execute(text("DELETE FROM campaigns")).rowcount
    print(f"    Deleted {campaigns_count} campaigns")
    
    # 4. Clear content_score_history if exists
    try:
        score_count = db.execute(text("DELETE FROM content_score_history")).rowcount
        print(f"    Deleted {score_count} content_score_history")
    except:
        pass
    
    db.commit()
    
    # Now delete contents
    count = db.query(Content).delete()
    db.commit()
    print(f"  Deleted {count} existing contents")
    return count


def import_contents(
    rows: List[Dict],
    db,
    dry_run: bool = False,
    download_thumbnails: bool = True
) -> Dict:
    """
    Import transformed rows into contents table
    """
    from app.services.thumbnail_service import download_thumbnail_async
    
    stats = {
        'total': len(rows),
        'imported': 0,
        'skipped': 0,
        'errors': 0,
        'error_items': []
    }
    
    for i, row in enumerate(rows, 1):
        try:
            # Transform row
            data = transform_row(row)
            
            if dry_run:
                if i <= 5:  # Show first 5 only
                    print(f"\n  [Preview #{i}] item_id={row['item_id']}")
                    print(f"    products: {data['product_codes']}")
                    print(f"    content_type: {data['content_type']}")
                    print(f"    views: {data['views']}, pfm: {data['pfm_score']}")
                stats['imported'] += 1
                continue
            
            # Create content
            content = Content(**data)
            db.add(content)
            
            # Download thumbnail if URL exists
            if download_thumbnails and data.get('thumbnail_url'):
                download_thumbnail_async(
                    data['thumbnail_url'],
                    'tiktok',
                    data['platform_post_id']
                )
            
            stats['imported'] += 1
            
            # Progress update
            if i % 500 == 0:
                db.commit()
                print(f"  Progress: {i}/{len(rows)} imported...")
                
        except Exception as e:
            stats['errors'] += 1
            stats['error_items'].append({
                'item_id': row.get('item_id'),
                'error': str(e)
            })
            if stats['errors'] <= 5:
                print(f"  [ERROR] item_id={row.get('item_id')}: {e}")
    
    if not dry_run:
        db.commit()
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='Migrate contents from old database')
    parser.add_argument('--no-clear', action='store_true', 
                        help='Do not clear contents table before import')
    parser.add_argument('--no-thumbnail', action='store_true',
                        help='Skip thumbnail download')
    parser.add_argument('--limit', type=int, help='Limit number of rows')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    parser.add_argument('--old-db-url', type=str, default=OLD_DB_URL,
                        help=f'Old database URL (default: {OLD_DB_URL})')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Migration: Import Contents from Old Database")
    if args.dry_run:
        print("[DRY RUN MODE - No changes will be made]")
    print("=" * 60)
    
    print(f"\nOld DB URL: {args.old_db_url[:50]}...")
    print(f"Clear table: {not args.no_clear}")
    print(f"Download thumbnails: {not args.no_thumbnail}")
    if args.limit:
        print(f"Limit: {args.limit} rows")
    
    db = SessionLocal()
    
    try:
        # Step 1: Fetch from old database
        print(f"\n--- Step 1: Fetch from old database ---")
        rows = fetch_from_old_db(args.old_db_url, args.limit)
        
        if not rows:
            print("No rows to import!")
            return
        
        # Step 2: Clear table (optional)
        if not args.no_clear:
            print(f"\n--- Step 2: Clear contents table ---")
            clear_contents_table(db, args.dry_run)
        
        # Step 3: Import
        print(f"\n--- Step 3: Import contents ---")
        stats = import_contents(
            rows,
            db,
            dry_run=args.dry_run,
            download_thumbnails=not args.no_thumbnail
        )
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  Total rows: {stats['total']}")
        print(f"  Imported: {stats['imported']}")
        print(f"  Errors: {stats['errors']}")
        
        if stats['error_items']:
            print(f"\nFirst 5 errors:")
            for err in stats['error_items'][:5]:
                print(f"  - {err['item_id']}: {err['error']}")
        
        print("=" * 60)
        
    except Exception as e:
        print(f"\n!!! ERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

