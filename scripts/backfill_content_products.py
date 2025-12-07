#!/usr/bin/env python
"""
Backfill Content Products from Old System

สคริปต์นี้ใช้สำหรับ map ข้อมูล products จากตาราง tiktok_posts ในฐานข้อมูลเก่า
มาใส่ในฟิลด์ product_codes ของตาราง contents ในฐานข้อมูลใหม่
โดย match ตาม item_id (เก่า) = platform_post_id (ใหม่)

Usage:
    python scripts/backfill_content_products.py
    python scripts/backfill_content_products.py --dry-run    # แสดงผลโดยไม่บันทึก
    python scripts/backfill_content_products.py --limit 100  # จำกัดจำนวน
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import Content
from app.models.enums import Platform

# --------------------------------------------------
# Old database connection
# --------------------------------------------------

DEFAULT_OLD_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "old_ref",
    "WeBoostX",
    ".env.old",
)
if os.path.isfile(DEFAULT_OLD_ENV_PATH):
    load_dotenv(DEFAULT_OLD_ENV_PATH)

OLD_DB_URL = (
    os.getenv("OLD_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql://user:password@localhost:5432/starcontent"
)


def get_old_db_connection():
    """Create connection to old database"""
    try:
        engine = create_engine(OLD_DB_URL)
        return engine.connect()
    except Exception as e:
        print(f"Error connecting to old database: {e}")
        print("Please set OLD_DATABASE_URL environment variable")
        return None


def clean_product_code(code: str) -> Optional[str]:
    """ทำความสะอาด product code - ลบ brackets และ whitespace"""
    if not code:
        return None
    # ลบ [ ] " ' และ whitespace
    cleaned = re.sub(r'[\[\]"\'\s]', '', code)
    return cleaned if cleaned else None


def parse_products_string(products_str: str) -> List[str]:
    """
    Parse products string จากฐานข้อมูลเก่าให้เป็น list of product codes
    
    รองรับหลายรูปแบบ:
    - "S1" -> ["S1"]
    - "S1,S2" -> ["S1", "S2"]
    - "S1, S2" -> ["S1", "S2"]
    - "S1 S2" -> ["S1", "S2"]
    - "["S1", "S2"]" (JSON string) -> ["S1", "S2"]
    - "[S2]" -> ["S2"]  (malformed)
    """
    if not products_str:
        return []
    
    products_str = products_str.strip()
    
    # ลองแปลงจาก JSON ก่อน
    if products_str.startswith('['):
        try:
            parsed = json.loads(products_str)
            if isinstance(parsed, list):
                codes = [clean_product_code(str(p)) for p in parsed if p]
                return [c for c in codes if c]
        except json.JSONDecodeError:
            # ถ้า JSON parse ไม่ได้ ให้ลบ brackets แล้ว parse ปกติ
            products_str = re.sub(r'[\[\]]', '', products_str)
    
    # แยกด้วย comma หรือ space
    products = re.split(r'[,\s]+', products_str)
    codes = [clean_product_code(p) for p in products]
    return [c for c in codes if c]


def parse_products_json(products_json) -> List[str]:
    """
    Parse products_json จากฐานข้อมูลเก่า (jsonb field)
    
    อาจเป็น:
    - list of strings: ["S1", "S2"]
    - list of dicts: [{"code": "S1"}, {"code": "S2"}]
    - already parsed: ["S1", "S2"]
    """
    if not products_json:
        return []
    
    # ถ้าเป็น string ต้อง parse ก่อน
    if isinstance(products_json, str):
        try:
            products_json = json.loads(products_json)
        except json.JSONDecodeError:
            return []
    
    if not isinstance(products_json, list):
        return []
    
    result = []
    for item in products_json:
        if isinstance(item, str):
            result.append(item.strip())
        elif isinstance(item, dict):
            # ดึง code หรือ product_code
            code = item.get('code') or item.get('product_code') or item.get('sku')
            if code:
                result.append(str(code).strip())
    
    return result


def backfill_content_products(
    db: Session,
    old_conn,
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> Dict:
    """
    Map products จาก tiktok_posts เก่า ไปยัง contents ใหม่
    """
    print("\n" + "=" * 70)
    print("Backfill Content Products from tiktok_posts")
    print("=" * 70)
    
    stats = {
        "total_old_posts": 0,
        "total_new_contents": 0,
        "matched": 0,
        "updated": 0,
        "skipped_no_products": 0,
        "skipped_already_has_products": 0,
        "not_found": 0,
        "errors": 0,
    }
    
    # --------------------------------------------------
    # Step 1: Fetch products data from old tiktok_posts
    # --------------------------------------------------
    print("\n[1] Fetching products data from old tiktok_posts...")
    
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    result = old_conn.execute(text(f"""
        SELECT 
            item_id,
            products,
            products_json
        FROM tiktok_posts
        WHERE item_id IS NOT NULL
        ORDER BY item_id
        {limit_clause}
    """))
    
    old_posts = result.fetchall()
    stats["total_old_posts"] = len(old_posts)
    print(f"   Found {stats['total_old_posts']} posts in old database")
    
    # --------------------------------------------------
    # Step 2: Build mapping dict: item_id -> product_codes
    # --------------------------------------------------
    print("\n[2] Parsing products data...")
    
    item_products_map: Dict[str, List[str]] = {}
    
    for row in old_posts:
        item_id = row[0]
        products_str = row[1]  # varchar field
        products_json = row[2]  # jsonb field
        
        # รวม products จากทั้งสอง field
        product_codes = set()
        
        # จาก products (varchar)
        parsed_str = parse_products_string(products_str)
        product_codes.update(parsed_str)
        
        # จาก products_json (jsonb)
        parsed_json = parse_products_json(products_json)
        product_codes.update(parsed_json)
        
        if product_codes:
            item_products_map[item_id] = sorted(list(product_codes))
    
    print(f"   Parsed {len(item_products_map)} posts with valid products")
    
    # --------------------------------------------------
    # Step 3: Get existing TikTok contents in new database
    # --------------------------------------------------
    print("\n[3] Fetching TikTok contents from new database...")
    
    contents = db.query(Content).filter(
        Content.platform == Platform.TIKTOK,
        Content.deleted_at.is_(None),
    ).all()
    
    stats["total_new_contents"] = len(contents)
    print(f"   Found {stats['total_new_contents']} TikTok contents in new database")
    
    # --------------------------------------------------
    # Step 4: Update product_codes for matched contents
    # --------------------------------------------------
    print("\n[4] Mapping products to contents...")
    
    for content in contents:
        item_id = content.platform_post_id
        
        if item_id not in item_products_map:
            stats["not_found"] += 1
            continue
        
        stats["matched"] += 1
        product_codes = item_products_map[item_id]
        
        # ตรวจสอบว่ามี product_codes อยู่แล้วหรือไม่
        if content.product_codes and len(content.product_codes) > 0:
            # ถ้ามีอยู่แล้ว ให้ merge เข้าด้วยกัน
            existing = set(content.product_codes)
            new_codes = set(product_codes)
            merged = sorted(list(existing | new_codes))
            
            if existing == set(merged):
                stats["skipped_already_has_products"] += 1
                continue
            
            product_codes = merged
        
        if dry_run:
            print(f"   [DRY-RUN] Would update {item_id}: {product_codes}")
        else:
            content.product_codes = product_codes
        
        stats["updated"] += 1
    
    # --------------------------------------------------
    # Step 5: Commit changes
    # --------------------------------------------------
    if not dry_run:
        print("\n[5] Committing changes...")
        try:
            db.commit()
            print("   Changes committed successfully!")
        except Exception as e:
            db.rollback()
            stats["errors"] += 1
            print(f"   Error committing: {e}")
    else:
        print("\n[5] DRY-RUN mode - no changes saved")
    
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='Backfill product_codes in contents from old tiktok_posts'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='แสดงผลลัพธ์โดยไม่บันทึกลงฐานข้อมูล'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='จำกัดจำนวน records ที่ประมวลผล'
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print(f"Content Products Migration - {datetime.now()}")
    print("=" * 70)
    print(f"New DB: {settings.DATABASE_URL[:60]}...")
    print(f"Old DB: {OLD_DB_URL[:60]}...")
    if args.dry_run:
        print("\n*** DRY-RUN MODE - ไม่มีการบันทึกข้อมูลจริง ***")
    if args.limit:
        print(f"*** LIMIT: {args.limit} records ***")
    
    # Connect to old database
    old_conn = get_old_db_connection()
    if not old_conn:
        print("\nFailed to connect to old database. Exiting.")
        return
    
    # Connect to new database
    db = SessionLocal()
    
    try:
        stats = backfill_content_products(
            db=db,
            old_conn=old_conn,
            dry_run=args.dry_run,
            limit=args.limit,
        )
        
        # Print summary
        print("\n" + "=" * 70)
        print("Migration Summary")
        print("=" * 70)
        print(f"  Old database posts:             {stats['total_old_posts']:,}")
        print(f"  New database contents:          {stats['total_new_contents']:,}")
        print(f"  Matched (found in both):        {stats['matched']:,}")
        print(f"  Updated:                        {stats['updated']:,}")
        print(f"  Skipped (already has products): {stats['skipped_already_has_products']:,}")
        print(f"  Not found in old DB:            {stats['not_found']:,}")
        print(f"  Errors:                         {stats['errors']:,}")
        
    except Exception as e:
        print(f"\nError during migration: {e}")
        raise
    finally:
        db.close()
        old_conn.close()


if __name__ == "__main__":
    main()

