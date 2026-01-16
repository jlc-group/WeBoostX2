"""
Create Spark Ad Auth tables for managing Influencer Auth Codes

Tables:
- spark_ad_auths: เก็บ auth codes จาก influencers
- spark_auth_import_logs: log การ import auth codes

Usage:
    python scripts/create_spark_auth_tables.py
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine, SessionLocal


def create_tables():
    """Create spark_ad_auths and spark_auth_import_logs tables"""
    
    db = SessionLocal()
    
    try:
        # Check if table already exists
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'spark_ad_auths'
            );
        """))
        exists = result.scalar()
        
        if exists:
            print("Table 'spark_ad_auths' already exists. Skipping creation.")
        else:
            # Create spark_ad_auths table
            db.execute(text("""
                CREATE TABLE spark_ad_auths (
                    id SERIAL PRIMARY KEY,
                    
                    -- Auth Code Info
                    auth_code VARCHAR(255) NOT NULL,
                    platform VARCHAR(50) DEFAULT 'tiktok' NOT NULL,
                    status VARCHAR(50) DEFAULT 'pending' NOT NULL,
                    error_message TEXT,
                    
                    -- Influencer Info
                    influencer_id INTEGER REFERENCES influencers(id),
                    influencer_name VARCHAR(255),
                    creator_username VARCHAR(255),
                    
                    -- Agency/Source info
                    agency_name VARCHAR(255),
                    batch_name VARCHAR(255),
                    notes TEXT,
                    
                    -- TikTok API Response
                    item_id VARCHAR(100),
                    identity_id VARCHAR(100),
                    identity_type VARCHAR(50),
                    auth_start_time TIMESTAMP WITH TIME ZONE,
                    auth_end_time TIMESTAMP WITH TIME ZONE,
                    ad_auth_status VARCHAR(50),
                    
                    -- Binding Info
                    content_id INTEGER REFERENCES contents(id),
                    ad_account_id INTEGER REFERENCES ad_accounts(id),
                    
                    -- Usage Tracking
                    authorized_at TIMESTAMP WITH TIME ZONE,
                    bound_at TIMESTAMP WITH TIME ZONE,
                    used_at TIMESTAMP WITH TIME ZONE,
                    used_in_ad_id INTEGER REFERENCES ads(id),
                    
                    -- Import info
                    imported_by INTEGER REFERENCES users(id),
                    imported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    
                    -- Standard fields
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TIMESTAMP WITH TIME ZONE
                );
                
                -- Indexes
                CREATE INDEX idx_spark_ad_auths_auth_code ON spark_ad_auths(auth_code);
                CREATE INDEX idx_spark_ad_auths_status ON spark_ad_auths(status);
                CREATE INDEX idx_spark_ad_auths_item_id ON spark_ad_auths(item_id);
                CREATE INDEX idx_spark_ad_auths_content_id ON spark_ad_auths(content_id);
                CREATE INDEX idx_spark_ad_auths_ad_account_id ON spark_ad_auths(ad_account_id);
                CREATE INDEX idx_spark_ad_auths_batch_name ON spark_ad_auths(batch_name);
            """))
            
            print("✅ Created table 'spark_ad_auths'")
        
        # Check if import_logs table exists
        result = db.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'spark_auth_import_logs'
            );
        """))
        exists = result.scalar()
        
        if exists:
            print("Table 'spark_auth_import_logs' already exists. Skipping creation.")
        else:
            # Create spark_auth_import_logs table
            db.execute(text("""
                CREATE TABLE spark_auth_import_logs (
                    id SERIAL PRIMARY KEY,
                    
                    -- Import info
                    batch_name VARCHAR(255),
                    agency_name VARCHAR(255),
                    source VARCHAR(50),
                    
                    -- Stats
                    total_codes INTEGER DEFAULT 0,
                    authorized_count INTEGER DEFAULT 0,
                    bound_count INTEGER DEFAULT 0,
                    failed_count INTEGER DEFAULT 0,
                    
                    -- Details
                    details JSONB,
                    
                    -- Who imported
                    imported_by INTEGER REFERENCES users(id),
                    
                    -- Standard fields
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """))
            
            print("✅ Created table 'spark_auth_import_logs'")
        
        db.commit()
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error: {e}")
        raise
    finally:
        db.close()


def check_tables():
    """Check if tables exist and show row counts"""
    db = SessionLocal()
    
    try:
        # Check spark_ad_auths
        result = db.execute(text("""
            SELECT COUNT(*) FROM spark_ad_auths WHERE deleted_at IS NULL
        """))
        count = result.scalar()
        print(f"📊 spark_ad_auths: {count} rows")
        
        # Check spark_auth_import_logs
        result = db.execute(text("""
            SELECT COUNT(*) FROM spark_auth_import_logs
        """))
        count = result.scalar()
        print(f"📊 spark_auth_import_logs: {count} rows")
        
    except Exception as e:
        print(f"Tables may not exist yet: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Create Spark Auth tables")
    parser.add_argument("--check", action="store_true", help="Check tables only")
    args = parser.parse_args()
    
    if args.check:
        check_tables()
    else:
        create_tables()
        print("\n--- Checking tables ---")
        check_tables()

