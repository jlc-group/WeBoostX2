"""
Migration script: เพิ่ม content_tags column ใน contents table

content_tags: JSON array สำหรับ classification อื่นๆ ที่ต้องการเพิ่มได้เรื่อยๆ
ไม่จำกัดจำนวน tags และสามารถเพิ่มใหม่ได้ตลอดเวลา

Usage:
    python scripts/add_content_tags_column.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.core.database import SessionLocal, engine


def add_content_tags_column():
    """เพิ่ม content_tags column ใน contents table"""
    
    db = SessionLocal()
    try:
        print("🔄 กำลังเพิ่ม content_tags column...")
        
        # ตรวจสอบว่า column มีอยู่แล้วหรือยัง
        check_query = text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'contents' 
            AND column_name = 'content_tags'
        """)
        result = db.execute(check_query).fetchone()
        
        if result:
            print("✅ content_tags column มีอยู่แล้ว ไม่ต้องเพิ่ม")
            return
        
        # เพิ่ม column
        alter_query = text("""
            ALTER TABLE contents 
            ADD COLUMN content_tags JSON DEFAULT '[]'::json
        """)
        
        db.execute(alter_query)
        db.commit()
        
        print("✅ เพิ่ม content_tags column สำเร็จ!")
        print("   - Type: JSON")
        print("   - Default: []")
        print("   - ใช้สำหรับ classification อื่นๆ ที่ต้องการเพิ่มได้เรื่อยๆ")
        
    except Exception as e:
        db.rollback()
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    add_content_tags_column()

