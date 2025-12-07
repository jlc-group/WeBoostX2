#!/usr/bin/env python
"""
Backfill Content Targeting from Old System

This script maps targeting_details from the old tiktok_posts table
to preferred_targeting_ids in the new contents table.

Usage:
    python scripts/backfill_content_targeting.py --dry-run
    python scripts/backfill_content_targeting.py
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Optional, Set

from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from psycopg2.extras import RealDictCursor
from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.content import Content
from app.models.platform import TargetingTemplate
from app.models.enums import Platform

# Load .env.old from old_ref/WeBoostX if exists
DEFAULT_OLD_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "old_ref",
    "WeBoostX",
    ".env.old",
)
if os.path.isfile(DEFAULT_OLD_ENV_PATH):
    load_dotenv(DEFAULT_OLD_ENV_PATH)

# Default old database URL
OLD_DB_URL = (
    os.getenv("OLD_DATABASE_URL")
    or os.getenv("OLD_DB_URL")
    or "postgresql://postgres:password@localhost:5432/starcontent"
)


def build_targeting_map(db) -> Dict[str, int]:
    """Build a map from targeting code/name to template ID"""
    templates = db.query(TargetingTemplate).all()
    
    # Map by name (e.g., 'F_MAKEUP_18_54' -> 7)
    name_map = {}
    for t in templates:
        if t.name and t.name != 'NOT_USE':
            # Normalize name (remove special chars, lowercase)
            normalized = t.name.strip().upper().replace('-', '_')
            name_map[normalized] = t.id
            name_map[t.name] = t.id  # Also keep original
        
        # Also map by targeting_code if exists
        if hasattr(t, 'targeting_code') and t.targeting_code:
            name_map[t.targeting_code] = t.id
    
    return name_map


def parse_targeting_from_old(targeting_details, targeting2_details) -> Set[str]:
    """Extract targeting IDs from old format"""
    targeting_ids = set()
    
    for details in [targeting_details, targeting2_details]:
        if not details:
            continue
        
        # Handle string JSON
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except:
                continue
        
        # Handle list format: [{'id': 'F_MAKEUP_18_54', 'percent': 100}]
        if isinstance(details, list):
            for item in details:
                if isinstance(item, dict) and 'id' in item:
                    targeting_ids.add(item['id'])
        
        # Handle dict format: {'id': 'F_MAKEUP_18_54', ...}
        elif isinstance(details, dict) and 'id' in details:
            targeting_ids.add(details['id'])
    
    return targeting_ids


def fetch_targeting_from_old_db(old_db_url: str) -> Dict[str, Set[str]]:
    """Fetch targeting data from old database"""
    print(f"Connecting to old database...")
    
    conn = psycopg2.connect(old_db_url)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Fetch all records with targeting
    cur.execute("""
        SELECT item_id, targeting_details, targeting2_details
        FROM tiktok_posts
        WHERE targeting_details IS NOT NULL
        AND targeting_details::text NOT IN ('null', '[]', '{}', '')
    """)
    
    rows = cur.fetchall()
    print(f"  Fetched {len(rows)} rows with targeting data")
    
    # Build map: item_id -> set of targeting IDs
    result = {}
    for row in rows:
        item_id = row['item_id']
        targeting_ids = parse_targeting_from_old(
            row['targeting_details'],
            row.get('targeting2_details')
        )
        if targeting_ids:
            result[item_id] = targeting_ids
    
    conn.close()
    return result


def backfill_targeting(db, old_targeting_map: Dict[str, Set[str]], 
                       template_map: Dict[str, int], dry_run: bool = False) -> Dict:
    """Update contents with preferred_targeting_ids"""
    
    stats = {
        'total': 0,
        'updated': 0,
        'skipped_no_match': 0,
        'skipped_not_found': 0,
        'errors': 0,
        'unmatched_targeting': set()
    }
    
    # Get all TikTok contents
    contents = db.query(Content).filter(
        Content.platform == Platform.TIKTOK
    ).all()
    
    print(f"Processing {len(contents)} TikTok contents...")
    
    for content in contents:
        stats['total'] += 1
        
        item_id = content.platform_post_id
        if item_id not in old_targeting_map:
            stats['skipped_not_found'] += 1
            continue
        
        # Get targeting IDs from old system
        old_targeting_ids = old_targeting_map[item_id]
        
        # Map to new template IDs
        new_template_ids = []
        for old_id in old_targeting_ids:
            # Try exact match
            normalized = old_id.strip().upper().replace('-', '_')
            
            if normalized in template_map:
                new_template_ids.append(template_map[normalized])
            elif old_id in template_map:
                new_template_ids.append(template_map[old_id])
            else:
                stats['unmatched_targeting'].add(old_id)
        
        if not new_template_ids:
            stats['skipped_no_match'] += 1
            continue
        
        # Update content
        if not dry_run:
            content.preferred_targeting_ids = new_template_ids
        
        stats['updated'] += 1
        
        if stats['total'] % 1000 == 0:
            print(f"  Progress: {stats['total']}/{len(contents)}")
    
    if not dry_run:
        db.commit()
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='Backfill content targeting')
    parser.add_argument('--dry-run', action='store_true', 
                        help='Preview changes without executing')
    parser.add_argument('--old-db-url', type=str, default=OLD_DB_URL,
                        help='Old database connection URL')
    args = parser.parse_args()
    
    print("=" * 60)
    print("Backfill Content Targeting")
    if args.dry_run:
        print("[DRY RUN MODE - No changes will be made]")
    print("=" * 60)
    
    # Connect to new database
    db = SessionLocal()
    
    try:
        # 1. Build targeting template map
        print("\n--- Step 1: Build targeting template map ---")
        template_map = build_targeting_map(db)
        print(f"  Found {len(template_map)} targeting mappings")
        
        # 2. Fetch targeting from old database
        print("\n--- Step 2: Fetch targeting from old database ---")
        old_targeting_map = fetch_targeting_from_old_db(args.old_db_url)
        print(f"  {len(old_targeting_map)} contents have targeting data")
        
        # 3. Backfill targeting
        print("\n--- Step 3: Backfill targeting ---")
        stats = backfill_targeting(db, old_targeting_map, template_map, args.dry_run)
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary:")
        print(f"  Total contents processed: {stats['total']}")
        print(f"  Updated: {stats['updated']}")
        print(f"  Skipped (no targeting in old): {stats['skipped_not_found']}")
        print(f"  Skipped (no match found): {stats['skipped_no_match']}")
        print(f"  Errors: {stats['errors']}")
        
        if stats['unmatched_targeting']:
            print(f"\n  Unmatched targeting IDs from old system:")
            for tid in sorted(stats['unmatched_targeting']):
                print(f"    - {tid}")
        
        print("=" * 60)
        
    finally:
        db.close()


if __name__ == "__main__":
    main()

