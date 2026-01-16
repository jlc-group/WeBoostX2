#!/usr/bin/env python
"""
Backfill TikTok ad daily performance into `ad_performance_daily` incrementally (no duplicates).

Mechanism:
- For each active TikTok AdAccount:
  - Read cursor from ad_accounts.config["tiktok_daily_cursor"] (YYYY-MM-DD)
  - If missing: start from ad_account.start_date (or --default_start_days ago)
  - Process in chunks (e.g., 2-7 days per run)
  - After SUCCESS, advance cursor to end_date (even if no rows returned)

This guarantees:
- No duplicate fetching of the same day range
- Days with no spend are still marked processed

Usage:
  $env:PYTHONPATH='D:\\GitHubCode\\WeBoostX2'
  python scripts/backfill_tiktok_ad_daily.py --chunk_days 2
  python scripts/backfill_tiktok_ad_daily.py --chunk_days 7 --max_accounts 1
"""

import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models import AdAccount
from app.models.enums import AdAccountStatus
from app.models.enums import Platform as PlatformEnum
from app.services.tiktok_ads_service import TikTokAdsService


def _get_cursor(cfg: dict) -> str:
    if not isinstance(cfg, dict):
        return ""
    v = cfg.get("tiktok_daily_cursor")
    return str(v) if v else ""


def _set_cursor(db, acc: AdAccount, cursor: str):
    cfg = acc.config if isinstance(acc.config, dict) else {}
    cfg = dict(cfg)  # copy for SQLAlchemy change detection
    cfg["tiktok_daily_cursor"] = cursor
    acc.config = cfg
    db.add(acc)
    db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk_days", type=int, default=2)
    ap.add_argument("--default_start_days", type=int, default=30)
    ap.add_argument("--max_accounts", type=int, default=0)
    args = ap.parse_args()

    chunk_days = max(1, min(31, args.chunk_days))
    default_start_days = max(1, min(3650, args.default_start_days))

    db = SessionLocal()
    try:
        accounts = (
            db.query(AdAccount)
            .filter(
                AdAccount.platform == PlatformEnum.TIKTOK,
                AdAccount.status == AdAccountStatus.ACTIVE,
            )
            .order_by(AdAccount.id.asc())
            .all()
        )
        if args.max_accounts and args.max_accounts > 0:
            accounts = accounts[: args.max_accounts]

        if not accounts:
            print("No active TikTok ad accounts.")
            return

        today = date.today()
        # We backfill up to yesterday only (avoid partial today)
        max_end = today - timedelta(days=1)

        for acc in accounts:
            cfg = acc.config if isinstance(acc.config, dict) else {}
            cursor = _get_cursor(cfg)

            if cursor:
                start = date.fromisoformat(cursor) + timedelta(days=1)
            else:
                # prefer account.start_date; fallback to default_start_days ago
                start = acc.start_date or (today - timedelta(days=default_start_days))

            if start > max_end:
                print(f"[SKIP] {acc.name} ({acc.external_account_id}) cursor={cursor} already up-to-date")
                continue

            end = min(start + timedelta(days=chunk_days - 1), max_end)
            start_str = start.isoformat()
            end_str = end.isoformat()

            print(f"[RUN] {acc.name} ({acc.external_account_id}) {start_str} -> {end_str}")
            try:
                result = TikTokAdsService.upsert_tiktok_ad_performance_daily(
                    db=db, ad_account=acc, start_date=start_str, end_date=end_str
                )
                print(f"  rows_fetched={result.get('rows_fetched')} upserted={result.get('inserted_or_updated')}")

                # advance cursor only when API call succeeded (even if 0 rows)
                _set_cursor(db, acc, end_str)
                print(f"  cursor -> {end_str}")
            except Exception as e:
                print(f"  [ERROR] {acc.name} ({acc.external_account_id}) {start_str}->{end_str}: {e}")
                print("  cursor not advanced")
                continue

    finally:
        db.close()


if __name__ == "__main__":
    main()


