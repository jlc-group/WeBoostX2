"""
Script สำหรับ sync Campaigns และ AdGroups จาก TikTok API เข้า DB โดยตรง
(ไม่ต้องรอให้มี Ads ก่อน)

วิธีใช้:
    $env:PYTHONPATH = 'D:\GitHubCode\WeBoostX2'
    C:\Python382\python.exe scripts\sync_campaigns_adgroups.py
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.core.database import SessionLocal
from app.models import AdAccount, Campaign, AdGroup
from app.models.enums import Platform, AdAccountStatus, AdStatus
from app.services.tiktok_ads_service import TikTokAdsService

# ลดความลายตาของ SQL logs
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def _truncate(value: Optional[str], max_length: int = 255) -> Optional[str]:
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= max_length else s[:max_length]


def _map_status(operation_status: Optional[str]) -> AdStatus:
    """Map TikTok operation_status to internal AdStatus"""
    if operation_status == "ENABLE":
        return AdStatus.ACTIVE
    elif operation_status == "DISABLE":
        return AdStatus.PAUSED
    return AdStatus.ACTIVE


def sync_campaigns_for_account(db, ad_account: AdAccount) -> dict:
    """Sync campaigns จาก TikTok API เข้า DB"""
    print(f"\n[{ad_account.name}] Syncing campaigns...")
    
    campaigns_raw = TikTokAdsService.fetch_campaigns(ad_account.external_account_id)
    if not campaigns_raw:
        print(f"  No campaigns found")
        return {"created": 0, "updated": 0}
    
    created = 0
    updated = 0
    
    for camp_data in campaigns_raw:
        campaign_id = camp_data.get("campaign_id")
        if not campaign_id:
            continue
        
        campaign = (
            db.query(Campaign)
            .filter(
                Campaign.platform == Platform.TIKTOK,
                Campaign.ad_account_id == ad_account.id,
                Campaign.external_campaign_id == campaign_id,
            )
            .first()
        )
        
        if not campaign:
            campaign = Campaign(
                platform=Platform.TIKTOK,
                ad_account_id=ad_account.id,
                external_campaign_id=campaign_id,
                name=_truncate(camp_data.get("campaign_name") or f"Campaign {campaign_id}"),
            )
            db.add(campaign)
            created += 1
        else:
            # Update existing
            if camp_data.get("campaign_name"):
                campaign.name = _truncate(camp_data["campaign_name"])
            updated += 1
        
        # Update fields
        campaign.objective_raw = camp_data.get("objective_type")
        campaign.status = _map_status(camp_data.get("operation_status"))
        campaign.daily_budget = camp_data.get("budget")
        campaign.last_synced_at = datetime.now(timezone.utc)
    
    db.commit()
    print(f"  Campaigns: {created} created, {updated} updated (total: {len(campaigns_raw)})")
    return {"created": created, "updated": updated}


def sync_adgroups_for_account(db, ad_account: AdAccount) -> dict:
    """Sync adgroups จาก TikTok API เข้า DB"""
    print(f"\n[{ad_account.name}] Syncing adgroups...")
    
    adgroups_raw = TikTokAdsService.fetch_adgroups(ad_account.external_account_id)
    if not adgroups_raw:
        print(f"  No adgroups found")
        return {"created": 0, "updated": 0, "skipped": 0}
    
    # Pre-load campaigns for this account
    campaigns = (
        db.query(Campaign)
        .filter(
            Campaign.ad_account_id == ad_account.id,
            Campaign.platform == Platform.TIKTOK,
        )
        .all()
    )
    campaign_map = {c.external_campaign_id: c for c in campaigns}
    
    created = 0
    updated = 0
    skipped = 0
    
    for ag_data in adgroups_raw:
        adgroup_id = ag_data.get("adgroup_id")
        campaign_id = ag_data.get("campaign_id")
        
        if not adgroup_id or not campaign_id:
            continue
        
        # Find campaign
        campaign = campaign_map.get(campaign_id)
        if not campaign:
            skipped += 1
            continue
        
        adgroup = (
            db.query(AdGroup)
            .filter(
                AdGroup.platform == Platform.TIKTOK,
                AdGroup.campaign_id == campaign.id,
                AdGroup.external_adgroup_id == adgroup_id,
            )
            .first()
        )
        
        if not adgroup:
            adgroup = AdGroup(
                platform=Platform.TIKTOK,
                ad_account_id=ad_account.id,
                campaign_id=campaign.id,
                external_adgroup_id=adgroup_id,
                name=_truncate(ag_data.get("adgroup_name") or f"AdGroup {adgroup_id}"),
            )
            db.add(adgroup)
            created += 1
        else:
            # Update existing
            if ag_data.get("adgroup_name"):
                adgroup.name = _truncate(ag_data["adgroup_name"])
            updated += 1
        
        # Update fields
        adgroup.optimization_goal_raw = ag_data.get("optimization_goal")
        adgroup.status = _map_status(ag_data.get("operation_status"))
        adgroup.daily_budget = ag_data.get("budget")
        adgroup.last_synced_at = datetime.now(timezone.utc)
    
    db.commit()
    print(f"  AdGroups: {created} created, {updated} updated, {skipped} skipped (total: {len(adgroups_raw)})")
    return {"created": created, "updated": updated, "skipped": skipped}


def main():
    print("=== Sync Campaigns & AdGroups from TikTok API ===")
    
    db = SessionLocal()
    
    try:
        # Get all active TikTok ad accounts
        ad_accounts = (
            db.query(AdAccount)
            .filter(
                AdAccount.platform == Platform.TIKTOK,
                AdAccount.status == AdAccountStatus.ACTIVE,
            )
            .all()
        )
        
        print(f"Found {len(ad_accounts)} active TikTok ad accounts")
        
        total_campaigns = {"created": 0, "updated": 0}
        total_adgroups = {"created": 0, "updated": 0, "skipped": 0}
        
        for ad_account in ad_accounts:
            # Sync campaigns first
            camp_result = sync_campaigns_for_account(db, ad_account)
            total_campaigns["created"] += camp_result["created"]
            total_campaigns["updated"] += camp_result["updated"]
            
            # Then sync adgroups
            ag_result = sync_adgroups_for_account(db, ad_account)
            total_adgroups["created"] += ag_result["created"]
            total_adgroups["updated"] += ag_result["updated"]
            total_adgroups["skipped"] += ag_result["skipped"]
        
        print("\n=== SUMMARY ===")
        print(f"Campaigns: {total_campaigns['created']} created, {total_campaigns['updated']} updated")
        print(f"AdGroups: {total_adgroups['created']} created, {total_adgroups['updated']} updated, {total_adgroups['skipped']} skipped")
        
        # Verify
        camp_count = db.query(Campaign).count()
        ag_count = db.query(AdGroup).count()
        abx_count = db.query(AdGroup).filter(AdGroup.name.contains("_ABX_")).count()
        
        print(f"\nDB now has:")
        print(f"  - {camp_count} campaigns")
        print(f"  - {ag_count} adgroups (ABX: {abx_count})")
        
    finally:
        db.close()


if __name__ == "__main__":
    main()

