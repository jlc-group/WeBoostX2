"""
Migration script: เปลี่ยน column role จาก enum เป็น varchar

Usage:
    python scripts/fix_role_column.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.core.database import SessionLocal


def fix_role_column():
    """เปลี่ยน column role จาก enum เป็น varchar"""
    
    db = SessionLocal()
    try:
        print("🔄 กำลังเปลี่ยน column role จาก enum เป็น varchar...")
        
        # แก้ไข column type
        alter_query = text("""
            ALTER TABLE content_staff_allocations 
            ALTER COLUMN role TYPE VARCHAR(50) USING role::text;
        """)
        
        db.execute(alter_query)
        db.commit()
        
        print("✅ เปลี่ยน column role เป็น VARCHAR(50) สำเร็จ!")
        
    except Exception as e:
        db.rollback()
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_role_column()

