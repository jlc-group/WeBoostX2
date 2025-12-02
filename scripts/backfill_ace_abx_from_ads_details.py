#!/usr/bin/env python
"""
Script to update ace_ad_count, abx_ad_count, ace_details, abx_details
from ads_details in contents table.

This script analyzes each ad in ads_details and classifies them as ACE or ABX
based on the naming pattern:
- ACE: ad_name contains "_ACE_"
- ABX: ad_name contains "_ABX_"

Based on old system logic from:
- old_ref/contentPFMProjectBackend/util_update_ace_abx_from_ads_details.py
- old_ref/WeBoostX/services/utils_service.py

Can be run:
- Manually: python scripts/backfill_ace_abx_from_ads_details.py
- As part of cronjob (hourly)
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import text
from app.core.database import SessionLocal, engine
from app.models import Content
from app.models.enums import Platform


def classify_ad_type(ad: Dict) -> str:
    """
    Classify ad as ACE, ABX, or GENERAL based on name pattern.
    
    Pattern from our system:
    - ACE: [ProductGroup]_ACE_<targeting>_SALE#01 | item_id (created by our system, 1 adgroup = 1 content)
    - ABX: [ProductGroup]_ABX_(targeting)_SALE#03 | item_id (created by our system, 1 adgroup = N contents)
    - GENERAL: no pattern (created directly in TikTok Ads Manager)
    """
    ad_name = (ad.get('ad_name') or '').upper()
    campaign_name = (ad.get('campaign_name') or '').upper()
    adgroup_name = (ad.get('adgroup_name') or '').upper()
    
    if '_ABX_' in ad_name or '_ABX_' in campaign_name or '_ABX_' in adgroup_name:
        return 'ABX'
    elif '_ACE_' in ad_name or '_ACE_' in campaign_name or '_ACE_' in adgroup_name:
        return 'ACE'
    else:
        # GENERAL: ads created directly in TikTok Ads Manager (not through our system)
        return 'GENERAL'


def extract_targeting_id(ad_name: str, ad_type: str) -> Optional[str]:
    """
    Extract targeting_id from ad_name.
    
    ACE format: [L10]_ACE_<MF_SUN_MASS_18_54>_SALE#01 → targeting_id = MF_SUN_MASS_18_54
    ABX format: [L10]_ABX_(MF_SUN_MASS_18_54)_SALE#03 → targeting_id = MF_SUN_MASS_18_54
    """
    import re
    
    if ad_type == 'ACE':
        # Pattern: _ACE_<targeting_id>_
        match = re.search(r'_ACE_<([^>]+)>_', ad_name)
        if match:
            return match.group(1)
    elif ad_type == 'ABX':
        # Pattern: _ABX_(targeting_id)_
        match = re.search(r'_ABX_\(([^\)]+)\)_', ad_name)
        if match:
            return match.group(1)
    
    return None


def update_content_ace_abx(content: Content, db) -> bool:
    """
    Update ace/abx counts and details for a single content.
    Returns True if updated, False if no changes.
    """
    if not content.ads_details:
        return False
    
    # Get ads list from ads_details
    ads_list = []
    if isinstance(content.ads_details, dict):
        for platform, ads in content.ads_details.items():
            if isinstance(ads, list):
                ads_list.extend(ads)
    elif isinstance(content.ads_details, list):
        ads_list = content.ads_details
    
    if not ads_list:
        return False
    
    # Classify each ad
    ace_ads = []
    abx_ads = []
    
    for ad in ads_list:
        if not isinstance(ad, dict):
            continue
            
        ad_type = classify_ad_type(ad)
        ad_name = ad.get('ad_name', '')
        
        # Build ad detail with targeting_id
        ad_detail = {
            'ad_id': ad.get('ad_id'),
            'adgroup_id': ad.get('adgroup_id'),
            'campaign_id': ad.get('campaign_id'),
            'advertiser_id': ad.get('advertiser_id'),
            'ad_name': ad_name,
            'targeting_id': extract_targeting_id(ad_name, ad_type),
            'ad_total_cost': ad.get('ad_total_cost') or ad.get('spend') or 0,
            'type': ad_type
        }
        
        if ad_type == 'ABX':
            abx_ads.append(ad_detail)
        elif ad_type == 'ACE':
            ace_ads.append(ad_detail)
        # GENERAL ads are not added to ace_ads or abx_ads
        
        # Update type in original ad
        ad['type'] = ad_type
    
    # Check if anything changed
    old_ace_count = content.ace_ad_count or 0
    old_abx_count = content.abx_ad_count or 0
    
    if old_ace_count == len(ace_ads) and old_abx_count == len(abx_ads):
        # No change in counts, check if details need update
        if content.ace_details and content.abx_details:
            return False
    
    # Update content
    content.ace_ad_count = len(ace_ads)
    content.abx_ad_count = len(abx_ads)
    content.ace_details = ace_ads if ace_ads else None
    content.abx_details = abx_ads if abx_ads else None
    
    return True


def backfill_ace_abx_all_contents(platform: Optional[str] = None, limit: Optional[int] = None) -> Dict:
    """
    Update ace/abx details for all contents with ads_details.
    
    Args:
        platform: Filter by platform (tiktok, facebook) or None for all
        limit: Limit number of contents to process (for testing)
    
    Returns:
        Dict with statistics
    """
    db = SessionLocal()
    
    try:
        print(f"[{datetime.now()}] Starting backfill_ace_abx_all_contents...")
        
        # Build query
        query = db.query(Content).filter(
            Content.deleted_at.is_(None),
            Content.ads_details.isnot(None)
        )
        
        if platform:
            # Platform enum uses lowercase values: "tiktok", "facebook", "instagram"
            platform_enum = Platform(platform.lower())
            query = query.filter(Content.platform == platform_enum)
        
        if limit:
            query = query.limit(limit)
        
        contents = query.all()
        
        print(f"  Found {len(contents)} contents with ads_details")
        
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        for content in contents:
            try:
                if update_content_ace_abx(content, db):
                    updated_count += 1
                    print(f"  Updated content {content.id}: ACE={content.ace_ad_count}, ABX={content.abx_ad_count}")
                else:
                    skipped_count += 1
            except Exception as e:
                error_count += 1
                print(f"  Error updating content {content.id}: {e}")
        
        db.commit()
        
        stats = {
            'total': len(contents),
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': error_count
        }
        
        print(f"[{datetime.now()}] Finished backfill_ace_abx_all_contents:")
        print(f"  Total: {stats['total']}, Updated: {stats['updated']}, Skipped: {stats['skipped']}, Errors: {stats['errors']}")
        
        return stats
        
    except Exception as e:
        print(f"[{datetime.now()}] Error in backfill_ace_abx_all_contents: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def update_ace_abx_for_tiktok():
    """Shortcut function to update only TikTok contents (for cronjob)"""
    return backfill_ace_abx_all_contents(platform='tiktok')


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill ACE/ABX details from ads_details')
    parser.add_argument('--platform', type=str, choices=['tiktok', 'facebook'], 
                        help='Filter by platform')
    parser.add_argument('--limit', type=int, help='Limit number of contents to process')
    parser.add_argument('--test', action='store_true', help='Test mode (limit=10)')
    
    args = parser.parse_args()
    
    if args.test:
        args.limit = 10
    
    print("=" * 60)
    print("Backfill ACE/ABX from ads_details")
    print("=" * 60)
    
    stats = backfill_ace_abx_all_contents(
        platform=args.platform,
        limit=args.limit
    )
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"  Total processed: {stats['total']}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Skipped (no change): {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")
    print("=" * 60)


if __name__ == "__main__":
    main()

