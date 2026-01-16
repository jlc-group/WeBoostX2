"""
Test TikTok lifetime spend fetch (report/integrated/get with filtering) using ad_ids from DB.

Goal:
- Pull a TikTok advertiser (AdAccount) + some external_ad_id values from local DB
- Call TikTokAdsService.fetch_spend_for_ads(advertiser_id, ad_ids)
- Print summary (requested/returned + sample)

Usage:
  python scripts/test_fetch_spend_for_ads_db.py
  python scripts/test_fetch_spend_for_ads_db.py --limit 50
  python scripts/test_fetch_spend_for_ads_db.py --advertiser_id 7221065902056292354 --limit 100
"""

import argparse
import os
import sys
from decimal import Decimal
from typing import Optional

from sqlalchemy import desc

# Ensure project root is on PYTHONPATH (so `import app...` works when running from /scripts)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.core.database import SessionLocal
from app.models import Ad, AdAccount
from app.models.enums import AdAccountStatus
from app.models.enums import Platform as PlatformEnum
from app.services.tiktok_ads_service import TikTokAdsService


def _to_float(v):
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except Exception:
        return 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--advertiser_id", type=str, default=None)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        # 1) pick advertiser
        advertiser_id = args.advertiser_id
        ad_account = None
        if advertiser_id:
            ad_account = (
                db.query(AdAccount)
                .filter(
                    AdAccount.platform == PlatformEnum.TIKTOK,
                    AdAccount.external_account_id == advertiser_id,
                )
                .first()
            )
        else:
            ad_account = (
                db.query(AdAccount)
                .filter(
                    AdAccount.platform == PlatformEnum.TIKTOK,
                    AdAccount.status == AdAccountStatus.ACTIVE,
                )
                .order_by(desc(AdAccount.id))
                .first()
            )
            advertiser_id = ad_account.external_account_id if ad_account else None

        if not advertiser_id:
            print("No TikTok AdAccount found. Please create/activate an ad account first.")
            return

        # 2) pull ad_ids from ads table
        def _fetch_ad_ids_for_account(account_id: Optional[int]):
            q = (
                db.query(Ad.external_ad_id)
                .filter(Ad.platform == PlatformEnum.TIKTOK)
                .order_by(desc(Ad.last_synced_at), desc(Ad.id))
            )
            if account_id:
                q = q.filter(Ad.ad_account_id == account_id)
            return [row[0] for row in q.limit(max(1, args.limit)).all() if row and row[0]]

        ad_ids = _fetch_ad_ids_for_account(ad_account.id if ad_account else None)
        ad_ids = [str(x) for x in ad_ids]

        # If the newest active ad_account has no ads yet, fallback to any TikTok ad_account that has ads
        if not ad_ids:
            any_acc = (
                db.query(AdAccount)
                .filter(
                    AdAccount.platform == PlatformEnum.TIKTOK,
                    AdAccount.status == AdAccountStatus.ACTIVE,
                )
                .order_by(desc(AdAccount.id))
                .all()
            )
            for acc in any_acc:
                ids = _fetch_ad_ids_for_account(acc.id)
                if ids:
                    ad_account = acc
                    advertiser_id = acc.external_account_id
                    ad_ids = [str(x) for x in ids]
                    break

        if not ad_ids:
            print("No TikTok ads found in DB at all. Please run Sync Ads first.")
            return

        print("=== Test fetch_spend_for_ads (DB ad_ids) ===")
        print(f"advertiser_id: {advertiser_id}")
        if ad_account:
            print(f"ad_account: id={ad_account.id}, name={ad_account.name}, status={ad_account.status}")
        print(f"ad_ids requested: {len(ad_ids)} (limit={args.limit})")
        print(f"sample ad_ids: {ad_ids[:5]}")

        spend_map = TikTokAdsService.fetch_spend_for_ads(advertiser_id, ad_ids)

        print("\n=== Result ===")
        print(f"returned: {len(spend_map)}")
        if spend_map:
            # preserve requested order for sample
            sample = []
            for aid in ad_ids:
                if aid in spend_map:
                    sample.append((aid, spend_map[aid]))
                if len(sample) >= 10:
                    break
            total = sum(_to_float(v) for v in spend_map.values())
            nonzero = sum(1 for v in spend_map.values() if _to_float(v) > 0)
            print(f"nonzero: {nonzero}")
            print(f"total spend (sum of returned): {total:,.2f}")
            print("sample (first 10 hits):")
            for aid, v in sample:
                print(f"  ad_id={aid}, spend={_to_float(v):,.2f}")
        else:
            print("spend_map is empty. Check API response logs printed by TikTokAdsService.")

    finally:
        db.close()


if __name__ == "__main__":
    main()


