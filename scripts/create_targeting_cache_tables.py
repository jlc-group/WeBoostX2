"""
Create targeting cache tables

Run this script to create the TikTok targeting cache tables:
- tiktok_interest_categories
- tiktok_action_categories  
- tiktok_regions

Usage:
    python scripts/create_targeting_cache_tables.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from app.models.targeting_cache import (
    TikTokInterestCategory,
    TikTokActionCategory, 
    TikTokRegion
)
from app.models.base import Base


def create_tables():
    """Create targeting cache tables"""
    print("Creating targeting cache tables...")
    
    # Create only the targeting cache tables
    TikTokInterestCategory.__table__.create(engine, checkfirst=True)
    print("✓ Created tiktok_interest_categories table")
    
    TikTokActionCategory.__table__.create(engine, checkfirst=True)
    print("✓ Created tiktok_action_categories table")
    
    TikTokRegion.__table__.create(engine, checkfirst=True)
    print("✓ Created tiktok_regions table")
    
    print("\n✅ All targeting cache tables created successfully!")


def sync_initial_data():
    """Sync initial data from TikTok API"""
    print("\nSyncing initial data from TikTok API...")
    
    from app.tasks.sync_targeting import sync_all_tiktok_targeting
    
    result = sync_all_tiktok_targeting(language="th")
    
    if result.get("success"):
        print("\n✅ Initial data synced successfully!")
        print(f"   Interests: {result['results']['interests'].get('inserted', 0)} items")
        print(f"   Actions: {result['results']['actions'].get('inserted', 0)} items")
        print(f"   Regions: {result['results']['regions'].get('inserted', 0)} items")
    else:
        print(f"\n⚠️ Some syncs failed: {result}")


if __name__ == "__main__":
    create_tables()
    
    # Ask if user wants to sync initial data
    user_input = input("\nDo you want to sync initial data from TikTok API? (y/n): ")
    if user_input.lower() == 'y':
        sync_initial_data()
    else:
        print("\nSkipped initial data sync. You can sync later via:")
        print("  - API: POST /api/v1/targeting/cache/sync")
        print("  - Cronjob: runs daily at 3 AM")

