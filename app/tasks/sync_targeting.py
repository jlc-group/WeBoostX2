"""
TikTok Targeting Data Sync Tasks

Sync TikTok targeting options to local database for faster access.
Run daily via cronjob.
"""
import logging
from datetime import datetime
from typing import Dict, List

from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal
from app.models.targeting_cache import (
    TikTokInterestCategory,
    TikTokActionCategory,
    TikTokRegion
)
from app.services.tiktok_targeting_service import TikTokTargetingService

logger = logging.getLogger(__name__)


def sync_tiktok_interests(language: str = "th") -> Dict:
    """
    Sync TikTok Interest Categories to database
    
    Returns:
        Dict with sync results
    """
    logger.info(f"[sync_tiktok_interests] Starting sync for language={language}")
    
    db = SessionLocal()
    
    try:
        # Fetch from TikTok API
        result = TikTokTargetingService.fetch_interest_categories(language=language)
        
        if "error" in result and not result.get("data"):
            logger.error(f"[sync_tiktok_interests] API error: {result.get('error')}")
            return {"success": False, "error": result.get("error")}
        
        categories = result.get("data", [])
        
        if not categories:
            logger.warning("[sync_tiktok_interests] No categories returned from API")
            return {"success": False, "error": "No data from API"}
        
        # Clear existing data for this language
        db.query(TikTokInterestCategory).filter(
            TikTokInterestCategory.language == language
        ).delete()
        
        # Insert new data
        inserted = 0
        for cat in categories:
            interest = TikTokInterestCategory(
                interest_category_id=str(cat.get("interest_category_id")),
                interest_category_name=cat.get("interest_category_name", ""),
                level=cat.get("level", 1),
                parent_id=str(cat.get("parent_id")) if cat.get("parent_id") else None,
                sub_category_ids=cat.get("sub_category_ids"),
                language=language,
                synced_at=datetime.utcnow()
            )
            db.add(interest)
            inserted += 1
        
        db.commit()
        
        logger.info(f"[sync_tiktok_interests] Synced {inserted} categories")
        return {"success": True, "inserted": inserted}
        
    except Exception as e:
        db.rollback()
        logger.error(f"[sync_tiktok_interests] Exception: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def sync_tiktok_actions(language: str = "th") -> Dict:
    """
    Sync TikTok Action Categories to database
    
    Returns:
        Dict with sync results
    """
    logger.info(f"[sync_tiktok_actions] Starting sync for language={language}")
    
    db = SessionLocal()
    
    try:
        # Fetch from TikTok API
        result = TikTokTargetingService.fetch_action_categories(language=language)
        
        if "error" in result and not result.get("data"):
            logger.error(f"[sync_tiktok_actions] API error: {result.get('error')}")
            return {"success": False, "error": result.get("error")}
        
        # Process both video_related and creator_related
        video_related = result.get("video_related", [])
        creator_related = result.get("creator_related", [])
        
        # Clear existing data for this language
        db.query(TikTokActionCategory).filter(
            TikTokActionCategory.language == language
        ).delete()
        
        inserted = 0
        
        # Insert video related
        for cat in video_related:
            action = TikTokActionCategory(
                action_category_id=str(cat.get("action_category_id")),
                name=cat.get("name", ""),
                description=cat.get("description"),
                action_scene="VIDEO_RELATED",
                level=cat.get("level", 1),
                parent_id=str(cat.get("parent_id")) if cat.get("parent_id") else None,
                sub_category_ids=cat.get("sub_category_ids"),
                language=language,
                synced_at=datetime.utcnow()
            )
            db.add(action)
            inserted += 1
        
        # Insert creator related
        for cat in creator_related:
            action = TikTokActionCategory(
                action_category_id=str(cat.get("action_category_id")),
                name=cat.get("name", ""),
                description=cat.get("description"),
                action_scene="CREATOR_RELATED",
                level=cat.get("level", 1),
                parent_id=str(cat.get("parent_id")) if cat.get("parent_id") else None,
                sub_category_ids=cat.get("sub_category_ids"),
                language=language,
                synced_at=datetime.utcnow()
            )
            db.add(action)
            inserted += 1
        
        db.commit()
        
        logger.info(f"[sync_tiktok_actions] Synced {inserted} categories")
        return {"success": True, "inserted": inserted}
        
    except Exception as e:
        db.rollback()
        logger.error(f"[sync_tiktok_actions] Exception: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def sync_tiktok_regions(language: str = "th") -> Dict:
    """
    Sync TikTok Regions to database
    
    Returns:
        Dict with sync results
    """
    logger.info(f"[sync_tiktok_regions] Starting sync for language={language}")
    
    db = SessionLocal()
    
    try:
        # Fetch from TikTok API
        result = TikTokTargetingService.fetch_regions(language=language)
        
        if "error" in result and not result.get("data"):
            logger.error(f"[sync_tiktok_regions] API error: {result.get('error')}")
            return {"success": False, "error": result.get("error")}
        
        regions = result.get("all_regions", result.get("data", []))
        
        if not regions:
            logger.warning("[sync_tiktok_regions] No regions returned from API")
            return {"success": False, "error": "No data from API"}
        
        # Clear existing data for this language
        db.query(TikTokRegion).filter(
            TikTokRegion.language == language
        ).delete()
        
        # Insert new data
        inserted = 0
        for region in regions:
            # level can be string like "COUNTRY", "PROVINCE" or integer
            level_val = region.get("level")
            if isinstance(level_val, int):
                level_val = str(level_val)
            
            r = TikTokRegion(
                location_id=str(region.get("location_id")),
                name=region.get("name", ""),
                region_code=region.get("region_code"),
                level=level_val,
                parent_id=str(region.get("parent_id")) if region.get("parent_id") else None,
                language=language,
                synced_at=datetime.utcnow()
            )
            db.add(r)
            inserted += 1
        
        db.commit()
        
        logger.info(f"[sync_tiktok_regions] Synced {inserted} regions")
        return {"success": True, "inserted": inserted}
        
    except Exception as e:
        db.rollback()
        logger.error(f"[sync_tiktok_regions] Exception: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


def sync_all_tiktok_targeting(language: str = "th") -> Dict:
    """
    Sync all TikTok targeting data (interests, actions, regions)
    
    Call this from cronjob daily.
    """
    logger.info("[sync_all_tiktok_targeting] Starting full targeting sync")
    
    results = {}
    
    # Sync interests
    results["interests"] = sync_tiktok_interests(language)
    
    # Sync actions
    results["actions"] = sync_tiktok_actions(language)
    
    # Sync regions
    results["regions"] = sync_tiktok_regions(language)
    
    success = all(r.get("success", False) for r in results.values())
    
    logger.info(f"[sync_all_tiktok_targeting] Complete: {results}")
    
    return {
        "success": success,
        "results": results
    }

