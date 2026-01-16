#!/usr/bin/env python
"""
Migration script: create `ad_performance_daily` table (no Alembic).

Why:
- Store daily ad performance snapshots for analytics/backfill without re-calling APIs.

Usage (PowerShell):
  $env:PYTHONPATH = 'D:\GitHubCode\WeBoostX2'
  python scripts/create_ad_performance_daily_table.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text

from app.core.database import SessionLocal, engine


def main():
    inspector = inspect(engine)
    db = SessionLocal()
    try:
        if "ad_performance_daily" in inspector.get_table_names():
            print("OK: Table ad_performance_daily already exists")
            return

        print("Creating table ad_performance_daily...")
        db.execute(
            text(
                """
                CREATE TABLE ad_performance_daily (
                    id SERIAL PRIMARY KEY,
                    platform VARCHAR(50) NOT NULL,
                    ad_account_id INTEGER NOT NULL REFERENCES ad_accounts(id),
                    external_ad_id VARCHAR(100) NOT NULL,
                    date DATE NOT NULL,
                    spend NUMERIC(15,2) DEFAULT 0,
                    impressions INTEGER DEFAULT 0,
                    clicks INTEGER DEFAULT 0,
                    reach INTEGER DEFAULT 0,
                    conversions INTEGER DEFAULT 0,
                    purchases INTEGER DEFAULT 0,
                    purchase_value NUMERIC(15,2) DEFAULT 0,
                    metrics JSONB,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        db.execute(text("CREATE INDEX ix_ad_perf_daily_platform ON ad_performance_daily (platform);"))
        db.execute(text("CREATE INDEX ix_ad_perf_daily_account ON ad_performance_daily (ad_account_id);"))
        db.execute(text("CREATE INDEX ix_ad_perf_daily_external_ad ON ad_performance_daily (external_ad_id);"))
        db.execute(text("CREATE INDEX ix_ad_perf_daily_date ON ad_performance_daily (date);"))
        db.execute(
            text(
                """
                CREATE UNIQUE INDEX uq_ad_perf_daily_platform_account_ad_date
                ON ad_performance_daily (platform, ad_account_id, external_ad_id, date);
                """
            )
        )
        db.commit()
        print("OK: Created ad_performance_daily")
    finally:
        db.close()


if __name__ == "__main__":
    main()


