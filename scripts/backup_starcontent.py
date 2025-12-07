#!/usr/bin/env python
"""
Backup Starcontent (old system) database to a local dump file,
using connection info from the old system's .env file.

Usage examples (run from project root):

    # 1) ใช้ .env ของระบบเก่า (ค่า default: old_ref/WeBoostX/.env)
    python scripts/backup_starcontent.py

    # 2) ระบุ path .env เอง และชื่อไฟล์ dump เอง
    python scripts/backup_starcontent.py --env-path "D:/old/WeBoostX/.env" --output starcontent_backup.sql

หมายเหตุ:
- สคริปต์นี้ต้องมีคำสั่ง `pg_dump` อยู่ใน PATH (ติดมากับ PostgreSQL client)
- จะอ่านค่า DATABASE_URL / SQLALCHEMY_DATABASE_URI / OLD_DATABASE_URL จาก .env
"""

import argparse
import datetime
import os
import subprocess
import sys
from typing import Optional

from dotenv import load_dotenv


def resolve_db_url() -> Optional[str]:
    """
    หา connection string ของฐานข้อมูลเก่า จากตัวแปรใน .env
    ลองตามลำดับ:
    - DATABASE_URL
    - SQLALCHEMY_DATABASE_URI
    - OLD_DATABASE_URL
    - หรือประกอบจาก POSTGRES_* / DB_* ถ้ามี
    """
    candidates = [
        "DATABASE_URL",
        "SQLALCHEMY_DATABASE_URI",
        "OLD_DATABASE_URL",
    ]

    for key in candidates:
        val = os.getenv(key)
        if val:
            return val

    # ลองประกอบจากตัวแปรย่อย
    host = (
        os.getenv("POSTGRES_HOST")
        or os.getenv("DB_HOST")
        or os.getenv("PGHOST")
        or "localhost"
    )
    port = os.getenv("POSTGRES_PORT") or os.getenv("DB_PORT") or os.getenv("PGPORT") or "5432"
    name = os.getenv("POSTGRES_DB") or os.getenv("DB_NAME") or "starcontent"
    user = os.getenv("POSTGRES_USER") or os.getenv("DB_USER") or os.getenv("PGUSER") or "postgres"
    password = os.getenv("POSTGRES_PASSWORD") or os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD") or ""

    if password:
        return f"postgresql://{user}:{password}@{host}:{port}/{name}"

    # ไม่มี password ก็ยังลองสร้าง URI ได้ แต่อาจต้องใช้ .pgpass
    return f"postgresql://{user}@{host}:{port}/{name}"


def run_pg_dump(db_url: str, output_path: str) -> None:
    """
    รัน pg_dump เพื่อ backup ฐานข้อมูลไปเป็นไฟล์ .dump หรือ .sql
    ใช้รูปแบบ:
        pg_dump <db_url> -Fc -f <output_path>
    """
    cmd = ["pg_dump", db_url, "-Fc", "-f", output_path]
    print(f"[backup_starcontent] Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("ERROR: ไม่พบคำสั่ง 'pg_dump' ใน PATH")
        print("กรุณาติดตั้ง PostgreSQL client และเพิ่มโฟลเดอร์ bin ของมันเข้า PATH ก่อน")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: pg_dump ล้มเหลว (exit code {e.returncode})")
        sys.exit(e.returncode)


def main():
    parser = argparse.ArgumentParser(description="Backup old Starcontent DB using .env from old system")
    default_env_path = os.path.join("old_ref", "WeBoostX", ".env")

    parser.add_argument(
        "--env-path",
        type=str,
        default=default_env_path,
        help=f"Path ไปยัง .env ของระบบเก่า (default: {default_env_path})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="ชื่อไฟล์ backup (default: starcontent_backup_YYYYMMDD.dump)",
    )

    args = parser.parse_args()

    # โหลด .env ของระบบเก่า
    env_path = args.env_path
    if os.path.isfile(env_path):
        print(f"[backup_starcontent] Loading env from: {env_path}")
        load_dotenv(env_path)
    else:
        print(f"WARNING: ไม่พบไฟล์ .env ที่ {env_path} จะลองอ่านค่าจาก environment ปัจจุบันแทน")

    db_url = resolve_db_url()
    if not db_url:
        print("ERROR: หา connection string ของฐานข้อมูลเก่าไม่เจอ")
        print("กรุณาเช็คตัวแปรใน .env ว่ามี DATABASE_URL / SQLALCHEMY_DATABASE_URI หรือ OLD_DATABASE_URL หรือ POSTGRES_*")
        sys.exit(1)

    # ตั้งชื่อไฟล์ output
    if args.output:
        output_path = args.output
    else:
        today = datetime.datetime.now().strftime("%Y%m%d")
        output_path = f"starcontent_backup_{today}.dump"

    print(f"[backup_starcontent] Remote DB URL: {db_url}")
    print(f"[backup_starcontent] Output file: {output_path}")

    run_pg_dump(db_url, output_path)

    print("\n✅ Backup เสร็จเรียบร้อย")
    print("ไฟล์ backup อยู่ที่:", os.path.abspath(output_path))
    print("ถ้าต้องการ restore เข้า localhost starcontent ตัวอย่างคำสั่ง:")
    print("  pg_restore -c -d postgresql://postgres:password@localhost:5432/starcontent", output_path)


if __name__ == "__main__":
    main()


