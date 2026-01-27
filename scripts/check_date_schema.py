#!/usr/bin/env python3
"""ตรวจสอบ schema ของวันที่ในตาราง Facebook"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(
    host=os.getenv("PG_HOST"),
    port=os.getenv("PG_PORT"),
    dbname=os.getenv("PG_DB"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD")
)

with conn.cursor() as cur:
    # ตรวจสอบ facebook_posts
    print("=== facebook_posts ===")
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'facebook_posts' 
        AND column_name IN ('created_time', 'updated_time', 'date', 'post_created_time')
        ORDER BY ordinal_position
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    # ตรวจสอบ facebook_ads
    print("\n=== facebook_ads ===")
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'facebook_ads' 
        AND column_name IN ('created_time', 'updated_time', 'date_start', 'date_stop')
        ORDER BY ordinal_position
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    # ตรวจสอบ sales_out
    print("\n=== sales_out ===")
    cur.execute("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'sales_out' 
        AND column_name IN ('sale_date', 'date', 'transaction_date', 'created_at', 'updated_at')
        ORDER BY ordinal_position
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")
    
    # ตัวอย่างข้อมูลจริง
    print("\n=== Sample Data ===")
    cur.execute("SELECT created_time FROM facebook_posts LIMIT 1")
    sample = cur.fetchone()
    if sample:
        print(f"facebook_posts.created_time sample: {sample[0]} (type: {type(sample[0])})")

conn.close()
