#!/usr/bin/env python
"""
Backfill Master Data from Old System

This script migrates master data from the old system to the new WeBoostX2 system.

Data to migrate:
- Products: from products table
- ProductGroups: from product_groups table  
- TikTokTargeting: from tiktok_targeting table

Usage:
    python scripts/backfill_master_data.py --all
    python scripts/backfill_master_data.py --products
    python scripts/backfill_master_data.py --product-groups
    python scripts/backfill_master_data.py --targeting
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal

# --------------------------------------------------
# Old database connection (from OLD_DATABASE_URL / DATABASE_URL / .env.old)
# --------------------------------------------------

# พยายามโหลด .env ของระบบเก่าอัตโนมัติ (ถ้ามี) เพื่อดึง DATABASE_URL
DEFAULT_OLD_ENV_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "old_ref",
    "WeBoostX",
    ".env.old",
)
if os.path.isfile(DEFAULT_OLD_ENV_PATH):
    load_dotenv(DEFAULT_OLD_ENV_PATH)

OLD_DB_URL = (
    os.getenv("OLD_DATABASE_URL")
    or os.getenv("DATABASE_URL")
    or "postgresql://user:password@localhost:5432/starcontent"
)


def get_old_db_connection():
    """Create connection to old database"""
    try:
        engine = create_engine(OLD_DB_URL)
        return engine.connect()
    except Exception as e:
        print(f"Error connecting to old database: {e}")
        print("Please set OLD_DATABASE_URL environment variable")
        return None


def backfill_products(db: Session, old_conn) -> Dict:
    """Migrate products from old system"""
    from app.models import Product
    
    print("\n" + "=" * 60)
    print("Migrating Products...")
    print("=" * 60)
    
    stats = {"total": 0, "created": 0, "updated": 0, "errors": 0}
    
    # Fetch products from old database
    result = old_conn.execute(text("""
        SELECT 
            code,
            productname,
            status,
            allocate_status
        FROM products
        ORDER BY code
    """))
    
    products = result.fetchall()
    stats["total"] = len(products)
    
    for row in products:
        try:
            code = row[0]
            name = row[1] or code
            status = row[2]
            allocate_status = row[3] if row[3] is not None else True
            
            # Check if product already exists
            existing = db.query(Product).filter(Product.code == code).first()
            
            if existing:
                # Update existing
                existing.name = name
                existing.is_active = status == 'active' if status else True
                existing.can_allocate_budget = allocate_status
                stats["updated"] += 1
                print(f"  Updated: {code} - {name}")
            else:
                # Create new
                product = Product(
                    code=code,
                    name=name,
                    is_active=status == 'active' if status else True,
                    can_allocate_budget=allocate_status
                )
                db.add(product)
                stats["created"] += 1
                print(f"  Created: {code} - {name}")
                
        except Exception as e:
            stats["errors"] += 1
            print(f"  Error with product {row[0]}: {e}")
    
    db.commit()
    
    print(f"\nProducts Summary:")
    print(f"  Total: {stats['total']}, Created: {stats['created']}, Updated: {stats['updated']}, Errors: {stats['errors']}")
    
    return stats


def backfill_product_groups(db: Session, old_conn) -> Dict:
    """Migrate product groups from old system"""
    import json

    from app.models import ProductGroup
    
    print("\n" + "=" * 60)
    print("Migrating Product Groups...")
    print("=" * 60)
    
    stats = {"total": 0, "created": 0, "updated": 0, "errors": 0}
    
    # Fetch product groups from old database
    result = old_conn.execute(text("""
        SELECT 
            id,
            name,
            products,
            is_active,
            created_at,
            updated_at
        FROM product_groups
        ORDER BY id
    """))
    
    groups = result.fetchall()
    stats["total"] = len(groups)
    
    for row in groups:
        try:
            old_id = row[0]
            name = row[1]
            products_json = row[2]
            is_active = row[3] if row[3] is not None else True
            
            # Parse products JSON
            if isinstance(products_json, str):
                product_codes = json.loads(products_json)
            elif isinstance(products_json, list):
                product_codes = products_json
            else:
                product_codes = []
            
            # Check if group with same name exists
            existing = db.query(ProductGroup).filter(ProductGroup.name == name).first()
            
            if existing:
                # Update existing
                existing.product_codes = product_codes
                existing.is_active = is_active
                stats["updated"] += 1
                print(f"  Updated: {name} ({len(product_codes)} products)")
            else:
                # Create new
                group = ProductGroup(
                    name=name,
                    product_codes=product_codes,
                    is_active=is_active
                )
                db.add(group)
                stats["created"] += 1
                print(f"  Created: {name} ({len(product_codes)} products)")
                
        except Exception as e:
            stats["errors"] += 1
            print(f"  Error with group {row[1]}: {e}")
    
    db.commit()
    
    print(f"\nProduct Groups Summary:")
    print(f"  Total: {stats['total']}, Created: {stats['created']}, Updated: {stats['updated']}, Errors: {stats['errors']}")
    
    return stats


def backfill_targeting(db: Session, old_conn) -> Dict:
    """Migrate TikTok targeting from old system"""
    import json

    from app.models import TargetingTemplate
    from app.models.enums import Platform
    
    print("\n" + "=" * 60)
    print("Migrating TikTok Targeting...")
    print("=" * 60)
    
    stats = {"total": 0, "created": 0, "updated": 0, "errors": 0}
    
    # Fetch targeting from old database
    result = old_conn.execute(text("""
        SELECT 
            id,
            name,
            age,
            gender,
            location,
            language,
            interest_categories,
            action_categories,
            device_types,
            network_types,
            create_user,
            create_time,
            is_approve,
            audience_lower,
            audience_upper,
            status,
            hashtags
        FROM tiktok_targeting
        ORDER BY id
    """))
    
    targetings = result.fetchall()
    stats["total"] = len(targetings)
    
    for row in targetings:
        try:
            targeting_code = str(row[0])  # Old ID becomes targeting_code
            name = row[1] or targeting_code
            age = row[2]
            gender = row[3]
            location = row[4]
            language = row[5]
            interests = row[6]
            behaviors = row[7]
            device_types = row[8]
            network_types = row[9]
            create_user = row[10]
            create_time = row[11]
            is_approved = row[12] if row[12] is not None else False
            audience_lower = row[13]
            audience_upper = row[14]
            is_active = row[15] if row[15] is not None else True
            hashtags = row[16] if len(row) > 16 else None
            
            # Parse JSON fields
            def parse_json(val):
                if val is None:
                    return None
                if isinstance(val, str):
                    try:
                        return json.loads(val)
                    except:
                        return None
                return val
            
            age_range = parse_json(age)
            locations = parse_json(location)
            languages = parse_json(language)
            interests_data = parse_json(interests)
            behaviors_data = parse_json(behaviors)
            device_types_data = parse_json(device_types)
            network_types_data = parse_json(network_types)
            hashtags_data = parse_json(hashtags)
            
            # Check if targeting with same code exists
            existing = db.query(TargetingTemplate).filter(
                TargetingTemplate.targeting_code == targeting_code
            ).first()
            
            if existing:
                # Update existing
                existing.name = name
                existing.gender = gender
                existing.age_range = age_range
                existing.locations = locations
                existing.languages = languages
                existing.interests = interests_data
                existing.behaviors = behaviors_data
                existing.device_types = device_types_data
                existing.network_types = network_types_data
                existing.hashtags = hashtags_data
                existing.audience_size_lower = audience_lower
                existing.audience_size_upper = audience_upper
                existing.is_approved = is_approved
                existing.is_active = is_active
                stats["updated"] += 1
                print(f"  Updated: {targeting_code} - {name}")
            else:
                # Create new
                targeting = TargetingTemplate(
                    targeting_code=targeting_code,
                    name=name,
                    platform=Platform.TIKTOK,
                    gender=gender,
                    age_range=age_range,
                    locations=locations,
                    languages=languages,
                    interests=interests_data,
                    behaviors=behaviors_data,
                    device_types=device_types_data,
                    network_types=network_types_data,
                    hashtags=hashtags_data,
                    audience_size_lower=audience_lower,
                    audience_size_upper=audience_upper,
                    is_approved=is_approved,
                    is_active=is_active
                )
                db.add(targeting)
                stats["created"] += 1
                print(f"  Created: {targeting_code} - {name}")
                
        except Exception as e:
            stats["errors"] += 1
            print(f"  Error with targeting {row[0]}: {e}")
    
    db.commit()
    
    print(f"\nTikTok Targeting Summary:")
    print(f"  Total: {stats['total']}, Created: {stats['created']}, Updated: {stats['updated']}, Errors: {stats['errors']}")
    
    return stats


def main():
    parser = argparse.ArgumentParser(description='Backfill master data from old system')
    parser.add_argument('--all', action='store_true', help='Migrate all master data')
    parser.add_argument('--products', action='store_true', help='Migrate products only')
    parser.add_argument('--product-groups', action='store_true', help='Migrate product groups only')
    parser.add_argument('--targeting', action='store_true', help='Migrate targeting only')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be migrated without making changes')
    
    args = parser.parse_args()
    
    # If no specific option, show help
    if not any([args.all, args.products, args.product_groups, args.targeting]):
        parser.print_help()
        return
    
    print("=" * 60)
    print(f"Master Data Migration - {datetime.now()}")
    print("=" * 60)
    print(f"New DB: {settings.DATABASE_URL[:50]}...")
    print(f"Old DB: {OLD_DB_URL[:50]}...")
    
    # Connect to old database
    old_conn = get_old_db_connection()
    if not old_conn:
        print("\nFailed to connect to old database. Exiting.")
        return
    
    # Connect to new database
    db = SessionLocal()
    
    try:
        results = {}
        
        if args.all or args.products:
            results["products"] = backfill_products(db, old_conn)
        
        if args.all or args.product_groups:
            results["product_groups"] = backfill_product_groups(db, old_conn)
        
        if args.all or args.targeting:
            results["targeting"] = backfill_targeting(db, old_conn)
        
        # Print final summary
        print("\n" + "=" * 60)
        print("Migration Complete!")
        print("=" * 60)
        
        for key, stats in results.items():
            print(f"\n{key}:")
            print(f"  Total: {stats['total']}")
            print(f"  Created: {stats['created']}")
            print(f"  Updated: {stats['updated']}")
            print(f"  Errors: {stats['errors']}")
        
    except Exception as e:
        print(f"\nError during migration: {e}")
        raise
    finally:
        db.close()
        old_conn.close()


if __name__ == "__main__":
    main()

