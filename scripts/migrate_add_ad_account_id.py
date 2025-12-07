#!/usr/bin/env python
"""
Migration script: เพิ่ม ad_account_id ในตาราง ad_groups, ads, ad_performance_history

สิ่งที่ script นี้ทำ:
1. เพิ่ม column ad_account_id ในตาราง:
   - ad_groups
   - ads
   - ad_performance_history
2. Backfill ad_account_id จากข้อมูลที่มีอยู่ผ่าน Campaign

วิธีใช้:
    PowerShell:
        $env:PYTHONPATH = 'D:\GitHubCode\WeBoostX2'
        C:\Python382\python.exe scripts\migrate_add_ad_account_id.py

    หรือ:
        python scripts/migrate_add_ad_account_id.py --dry-run  # ดู preview ก่อน
        python scripts/migrate_add_ad_account_id.py            # รันจริง
"""

import os
import sys
import argparse

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, inspect
from app.core.database import SessionLocal, engine


def check_column_exists(table_name: str, column_name: str) -> bool:
    """ตรวจสอบว่า column มีอยู่ในตารางแล้วหรือยัง"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


def add_column_if_not_exists(db, table_name: str, column_name: str, column_type: str, dry_run: bool):
    """เพิ่ม column ถ้ายังไม่มี"""
    if check_column_exists(table_name, column_name):
        print(f"  ✓ Column {column_name} already exists in {table_name}")
        return False
    
    sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
    if dry_run:
        print(f"  [DRY RUN] Would execute: {sql}")
        return True
    
    print(f"  Adding column {column_name} to {table_name}...")
    db.execute(text(sql))
    db.commit()
    print(f"  ✓ Added column {column_name} to {table_name}")
    return True


def create_index_if_not_exists(db, table_name: str, column_name: str, dry_run: bool):
    """สร้าง index ถ้ายังไม่มี"""
    index_name = f"ix_{table_name}_{column_name}"
    
    # Check if index exists
    check_sql = f"""
        SELECT 1 FROM pg_indexes 
        WHERE tablename = '{table_name}' AND indexname = '{index_name}'
    """
    result = db.execute(text(check_sql)).fetchone()
    
    if result:
        print(f"  ✓ Index {index_name} already exists")
        return False
    
    sql = f"CREATE INDEX {index_name} ON {table_name} ({column_name})"
    if dry_run:
        print(f"  [DRY RUN] Would execute: {sql}")
        return True
    
    print(f"  Creating index {index_name}...")
    db.execute(text(sql))
    db.commit()
    print(f"  ✓ Created index {index_name}")
    return True


def backfill_ad_groups(db, dry_run: bool) -> int:
    """
    Backfill ad_account_id ในตาราง ad_groups จาก campaigns
    
    ad_groups -> campaign_id -> campaigns.ad_account_id
    """
    # ตรวจสอบว่า column มีอยู่หรือไม่ก่อน query
    if not check_column_exists('ad_groups', 'ad_account_id'):
        if dry_run:
            # ใน dry-run, ประมาณจำนวนจากจำนวน ad_groups ทั้งหมด
            total_sql = "SELECT COUNT(*) FROM ad_groups"
            count = db.execute(text(total_sql)).scalar()
            print(f"  [DRY RUN] Would update up to {count} ad_groups with ad_account_id (column not created yet)")
            return count
        else:
            print(f"  ✗ Column ad_account_id does not exist in ad_groups - run step 1 first")
            return 0
    
    # ดึงจำนวนแถวที่ต้อง update
    count_sql = """
        SELECT COUNT(*) FROM ad_groups ag
        JOIN campaigns c ON ag.campaign_id = c.id
        WHERE ag.ad_account_id IS NULL AND c.ad_account_id IS NOT NULL
    """
    count = db.execute(text(count_sql)).scalar()
    
    if count == 0:
        print(f"  ✓ No ad_groups need ad_account_id backfill")
        return 0
    
    if dry_run:
        print(f"  [DRY RUN] Would update {count} ad_groups with ad_account_id")
        return count
    
    print(f"  Updating {count} ad_groups with ad_account_id...")
    
    update_sql = """
        UPDATE ad_groups ag
        SET ad_account_id = c.ad_account_id
        FROM campaigns c
        WHERE ag.campaign_id = c.id
          AND ag.ad_account_id IS NULL
          AND c.ad_account_id IS NOT NULL
    """
    result = db.execute(text(update_sql))
    db.commit()
    
    updated = result.rowcount
    print(f"  ✓ Updated {updated} ad_groups")
    return updated


def backfill_ads(db, dry_run: bool) -> int:
    """
    Backfill ad_account_id ในตาราง ads จาก ad_groups หรือ campaigns
    
    ads -> ad_group_id -> ad_groups.ad_account_id
    หรือ ads -> ad_group_id -> ad_groups.campaign_id -> campaigns.ad_account_id
    """
    # ตรวจสอบว่า column มีอยู่หรือไม่ก่อน query
    if not check_column_exists('ads', 'ad_account_id'):
        if dry_run:
            # ใน dry-run, ประมาณจำนวนจากจำนวน ads ทั้งหมด
            total_sql = "SELECT COUNT(*) FROM ads"
            count = db.execute(text(total_sql)).scalar()
            print(f"  [DRY RUN] Would update up to {count} ads with ad_account_id (column not created yet)")
            return count
        else:
            print(f"  ✗ Column ad_account_id does not exist in ads - run step 1 first")
            return 0
    
    # ดึงจำนวนแถวที่ต้อง update
    count_sql = """
        SELECT COUNT(*) FROM ads a
        JOIN ad_groups ag ON a.ad_group_id = ag.id
        JOIN campaigns c ON ag.campaign_id = c.id
        WHERE a.ad_account_id IS NULL AND c.ad_account_id IS NOT NULL
    """
    count = db.execute(text(count_sql)).scalar()
    
    if count == 0:
        print(f"  ✓ No ads need ad_account_id backfill")
        return 0
    
    if dry_run:
        print(f"  [DRY RUN] Would update {count} ads with ad_account_id")
        return count
    
    print(f"  Updating {count} ads with ad_account_id...")
    
    # ใช้ ad_groups.ad_account_id ก่อน, ถ้าไม่มีก็ใช้ campaigns.ad_account_id
    update_sql = """
        UPDATE ads a
        SET ad_account_id = COALESCE(ag.ad_account_id, c.ad_account_id)
        FROM ad_groups ag
        JOIN campaigns c ON ag.campaign_id = c.id
        WHERE a.ad_group_id = ag.id
          AND a.ad_account_id IS NULL
          AND (ag.ad_account_id IS NOT NULL OR c.ad_account_id IS NOT NULL)
    """
    result = db.execute(text(update_sql))
    db.commit()
    
    updated = result.rowcount
    print(f"  ✓ Updated {updated} ads")
    return updated


def backfill_ad_performance_history(db, dry_run: bool) -> int:
    """
    Backfill ad_account_id ในตาราง ad_performance_history จาก ads
    
    ad_performance_history -> ad_id -> ads.ad_account_id
    """
    # ตรวจสอบว่าตาราง ad_performance_history มีอยู่หรือไม่
    inspector = inspect(engine)
    if 'ad_performance_history' not in inspector.get_table_names():
        print(f"  ✓ Table ad_performance_history does not exist yet, skipping")
        return 0
    
    # ตรวจสอบว่า column มีอยู่หรือไม่ก่อน query
    if not check_column_exists('ad_performance_history', 'ad_account_id'):
        if dry_run:
            # ใน dry-run, ประมาณจำนวนจากจำนวน ad_performance_history ทั้งหมด
            total_sql = "SELECT COUNT(*) FROM ad_performance_history"
            count = db.execute(text(total_sql)).scalar()
            print(f"  [DRY RUN] Would update up to {count} ad_performance_history with ad_account_id (column not created yet)")
            return count
        else:
            print(f"  ✗ Column ad_account_id does not exist in ad_performance_history - run step 1 first")
            return 0
    
    # ดึงจำนวนแถวที่ต้อง update
    count_sql = """
        SELECT COUNT(*) FROM ad_performance_history aph
        JOIN ads a ON aph.ad_id = a.id
        WHERE aph.ad_account_id IS NULL AND a.ad_account_id IS NOT NULL
    """
    count = db.execute(text(count_sql)).scalar()
    
    if count == 0:
        print(f"  ✓ No ad_performance_history need ad_account_id backfill")
        return 0
    
    if dry_run:
        print(f"  [DRY RUN] Would update {count} ad_performance_history with ad_account_id")
        return count
    
    print(f"  Updating {count} ad_performance_history with ad_account_id...")
    
    update_sql = """
        UPDATE ad_performance_history aph
        SET ad_account_id = a.ad_account_id
        FROM ads a
        WHERE aph.ad_id = a.id
          AND aph.ad_account_id IS NULL
          AND a.ad_account_id IS NOT NULL
    """
    result = db.execute(text(update_sql))
    db.commit()
    
    updated = result.rowcount
    print(f"  ✓ Updated {updated} ad_performance_history")
    return updated


def show_stats(db):
    """แสดงสถิติของข้อมูลในตาราง"""
    print("\n=== Current Statistics ===")
    
    # ad_groups stats
    ag_total = db.execute(text("SELECT COUNT(*) FROM ad_groups")).scalar()
    ag_with_account = db.execute(text("SELECT COUNT(*) FROM ad_groups WHERE ad_account_id IS NOT NULL")).scalar()
    print(f"  ad_groups: {ag_with_account}/{ag_total} have ad_account_id")
    
    # ads stats
    ads_total = db.execute(text("SELECT COUNT(*) FROM ads")).scalar()
    ads_with_account = db.execute(text("SELECT COUNT(*) FROM ads WHERE ad_account_id IS NOT NULL")).scalar()
    print(f"  ads: {ads_with_account}/{ads_total} have ad_account_id")
    
    # ad_performance_history stats (if exists)
    inspector = inspect(engine)
    if 'ad_performance_history' in inspector.get_table_names():
        aph_total = db.execute(text("SELECT COUNT(*) FROM ad_performance_history")).scalar()
        aph_with_account = db.execute(text("SELECT COUNT(*) FROM ad_performance_history WHERE ad_account_id IS NOT NULL")).scalar()
        print(f"  ad_performance_history: {aph_with_account}/{aph_total} have ad_account_id")
    else:
        print(f"  ad_performance_history: table not created yet")


def main():
    parser = argparse.ArgumentParser(description='Add ad_account_id columns and backfill data')
    parser.add_argument('--dry-run', action='store_true', help='Preview changes without applying')
    args = parser.parse_args()
    
    dry_run = args.dry_run
    
    print("=" * 60)
    print("Migration: Add ad_account_id to ad_groups, ads, ad_performance_history")
    if dry_run:
        print("[DRY RUN MODE - No changes will be made]")
    print("=" * 60)
    
    db = SessionLocal()
    
    try:
        # Step 1: Add columns
        print("\n--- Step 1: Add ad_account_id columns ---")
        
        add_column_if_not_exists(db, 'ad_groups', 'ad_account_id', 'INTEGER REFERENCES ad_accounts(id)', dry_run)
        add_column_if_not_exists(db, 'ads', 'ad_account_id', 'INTEGER REFERENCES ad_accounts(id)', dry_run)
        add_column_if_not_exists(db, 'ad_performance_history', 'ad_account_id', 'INTEGER REFERENCES ad_accounts(id)', dry_run)
        
        # Step 2: Create indexes
        print("\n--- Step 2: Create indexes ---")
        
        create_index_if_not_exists(db, 'ad_groups', 'ad_account_id', dry_run)
        create_index_if_not_exists(db, 'ads', 'ad_account_id', dry_run)
        create_index_if_not_exists(db, 'ad_performance_history', 'ad_account_id', dry_run)
        
        # Step 3: Backfill data
        print("\n--- Step 3: Backfill ad_account_id ---")
        
        # Backfill ad_groups first (they depend on campaigns)
        ag_updated = backfill_ad_groups(db, dry_run)
        
        # Then backfill ads (they depend on ad_groups)
        ads_updated = backfill_ads(db, dry_run)
        
        # Finally backfill ad_performance_history (they depend on ads)
        aph_updated = backfill_ad_performance_history(db, dry_run)
        
        # Show stats
        if not dry_run:
            show_stats(db)
        
        # Summary
        print("\n" + "=" * 60)
        print("Summary:")
        if dry_run:
            print("  [DRY RUN] No changes were made")
            print(f"  Would update: {ag_updated} ad_groups, {ads_updated} ads, {aph_updated} ad_performance_history")
        else:
            print(f"  Updated: {ag_updated} ad_groups, {ads_updated} ads, {aph_updated} ad_performance_history")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n!!! ERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

