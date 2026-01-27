#!/usr/bin/env python3
"""
Export complete database schema with all tables, columns, types, and relationships
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Fix encoding for file output
if sys.platform.startswith('win'):
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'replace')

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    dbname=os.getenv("PG_DB"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD")
)

print("=" * 100)
print("DATABASE SCHEMA EXPORT - Facebook Backend Database")
print("=" * 100)

with conn.cursor() as cur:
    # Get all tables in public schema
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]
    
    print(f"\n📊 Total Tables: {len(tables)}\n")
    
    for table_name in tables:
        # Get row count
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            row_count = cur.fetchone()[0]
        except:
            row_count = "N/A"
        
        print(f"\n{'=' * 100}")
        print(f"TABLE: {table_name} ({row_count:,} rows)" if isinstance(row_count, int) else f"TABLE: {table_name}")
        print(f"{'=' * 100}")
        
        # Get columns with details
        cur.execute("""
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = %s
            ORDER BY ordinal_position
        """, (table_name,))
        
        columns = cur.fetchall()
        
        print(f"\n{'Column Name':<30} {'Type':<30} {'Nullable':<10} {'Default'}")
        print(f"{'-' * 30} {'-' * 30} {'-' * 10} {'-' * 30}")
        
        for col_name, data_type, max_length, nullable, default in columns:
            # Format data type
            if max_length and data_type in ('character varying', 'character'):
                type_str = f"{data_type}({max_length})"
            else:
                type_str = data_type
            
            # Format default
            default_str = str(default)[:30] if default else ""
            
            print(f"{col_name:<30} {type_str:<30} {nullable:<10} {default_str}")
        
        # Get primary key
        cur.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_schema = 'public'
            AND tc.table_name = %s
            ORDER BY kcu.ordinal_position
        """, (table_name,))
        
        pk_columns = [row[0] for row in cur.fetchall()]
        if pk_columns:
            print(f"\n🔑 Primary Key: {', '.join(pk_columns)}")
        
        # Get foreign keys
        cur.execute("""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = 'public'
            AND tc.table_name = %s
        """, (table_name,))
        
        fk_relations = cur.fetchall()
        if fk_relations:
            print(f"\n🔗 Foreign Keys:")
            for col, ref_table, ref_col in fk_relations:
                print(f"   {col} → {ref_table}.{ref_col}")
        
        # Get indexes
        try:
            cur.execute("""
                SELECT
                    indexname,
                    indexdef
                FROM pg_indexes
                WHERE schemaname = 'public'
                AND tablename = %s
                AND indexname NOT LIKE '%_pkey'
                ORDER BY indexname
            """, (table_name,))
            
            indexes = cur.fetchall()
            if indexes:
                print(f"\nIndexes:")
                for idx_name, idx_def in indexes:
                    print(f"   {idx_name}")
                    # Extract column names from index definition
                    if 'USING' in idx_def:
                        try:
                            cols_part = idx_def.split('(', 1)[1].rsplit(')', 1)[0]
                            print(f"      -> {cols_part}")
                        except:
                            pass
        except Exception as e:
            pass
        
        # Get unique constraints
        try:
            cur.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                WHERE tc.constraint_type = 'UNIQUE'
                AND tc.table_schema = 'public'
                AND tc.table_name = %s
                ORDER BY kcu.ordinal_position
            """, (table_name,))
            
            unique_cols = [row[0] for row in cur.fetchall()]
            if unique_cols:
                print(f"\nUnique Constraints: {', '.join(unique_cols)}")
        except Exception as e:
            pass

    # Summary
    print(f"\n\n{'=' * 100}")
    print("SUMMARY")
    print(f"{'=' * 100}\n")
    
    # Group tables by category
    facebook_tables = [t for t in tables if t.startswith('facebook_')]
    ad_tables = [t for t in facebook_tables if '_ad' in t]
    post_tables = [t for t in facebook_tables if '_post' in t or '_video' in t or '_reel' in t]
    insight_tables = [t for t in facebook_tables if '_insight' in t]
    campaign_tables = [t for t in facebook_tables if '_campaign' in t or '_adset' in t]
    
    other_tables = [t for t in tables if not t.startswith('facebook_')]
    
    print(f"📱 Facebook Posts/Videos: {len(post_tables)}")
    for t in sorted(post_tables):
        print(f"   - {t}")
    
    print(f"\n💰 Facebook Ads: {len(ad_tables)}")
    for t in sorted(ad_tables):
        print(f"   - {t}")
    
    print(f"\n📊 Insights: {len(insight_tables)}")
    for t in sorted(insight_tables):
        print(f"   - {t}")
    
    print(f"\n🎯 Campaigns/AdSets: {len(campaign_tables)}")
    for t in sorted(campaign_tables):
        print(f"   - {t}")
    
    print(f"\n🗂️  Other Tables: {len(other_tables)}")
    for t in sorted(other_tables):
        print(f"   - {t}")
    
    print(f"\n📦 Total: {len(tables)} tables")

conn.close()
print("\n✅ Schema export complete!")
