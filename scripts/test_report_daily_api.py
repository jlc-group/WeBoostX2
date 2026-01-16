"""
Test TikTok Report API (daily) using dimensions ["ad_id","stat_time_day"].

Usage:
  python scripts/test_report_daily_api.py --days 7
  python scripts/test_report_daily_api.py --start 2025-11-01 --end 2025-11-30
"""

import argparse
import json
import os
import time
from datetime import date, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("TIKTOK_AD_TOKEN") or os.getenv("TIKTOK_ACCESS_TOKEN")
ADVERTISER_ID = os.getenv("ADVERTISER_ID_IDAC_MAIN")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--start", type=str, default=None)
    ap.add_argument("--end", type=str, default=None)
    args = ap.parse_args()

    if not ACCESS_TOKEN or not ADVERTISER_ID:
        print("Missing env: TIKTOK_AD_TOKEN/TIKTOK_ACCESS_TOKEN or ADVERTISER_ID_IDAC_MAIN")
        return

    if args.start and args.end:
        start_str, end_str = args.start, args.end
    else:
        end_d = date.today() - timedelta(days=1)
        start_d = end_d - timedelta(days=max(1, args.days) - 1)
        start_str, end_str = start_d.isoformat(), end_d.isoformat()

    url = "https://business-api.tiktok.com/open_api/v1.3/report/integrated/get/"
    params = {
        "advertiser_id": ADVERTISER_ID,
        "report_type": "BASIC",
        "data_level": "AUCTION_AD",
        "dimensions": json.dumps(["ad_id", "stat_time_day"]),
        "metrics": json.dumps(["spend", "impressions", "clicks", "reach", "conversion"]),
        "start_date": start_str,
        "end_date": end_str,
        "page_size": 1000,
        "page": 1,
    }
    headers = {"Access-Token": ACCESS_TOKEN}

    print("=== TikTok Report Daily API Test ===")
    print("advertiser_id:", ADVERTISER_ID)
    print("range:", start_str, "->", end_str)
    t0 = time.time()
    resp = requests.get(url, headers=headers, params=params, timeout=60)
    elapsed = time.time() - t0
    print("status:", resp.status_code, "time:", f"{elapsed:.2f}s")
    try:
        data = resp.json()
    except Exception:
        print("non-json response head:", resp.text[:300])
        return

    print("code:", data.get("code"), "message:", data.get("message"))
    rows = data.get("data", {}).get("list", []) or []
    print("rows:", len(rows))
    if rows:
        print("sample (first 3):")
        for r in rows[:3]:
            print("  dims:", r.get("dimensions"))
            print("  metrics:", r.get("metrics"))


if __name__ == "__main__":
    main()


