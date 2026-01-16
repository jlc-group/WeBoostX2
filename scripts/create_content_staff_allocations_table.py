"""
Migration script: สร้างตาราง content_staff_allocations

สำหรับเก็บข้อมูลการ allocate พนักงานทำคลิป พร้อม role และ percentage

Usage:
    python scripts/create_content_staff_allocations_table.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.core.database import SessionLocal, engine


def create_content_staff_allocations_table():
    """สร้างตาราง content_staff_allocations"""
    
    db = SessionLocal()
    try:
        print("🔄 กำลังสร้างตาราง content_staff_allocations...")
        
        # ตรวจสอบว่าตารางมีอยู่แล้วหรือยัง
        check_query = text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'content_staff_allocations'
            )
        """)
        result = db.execute(check_query).fetchone()
        
        if result[0]:
            print("✅ ตาราง content_staff_allocations มีอยู่แล้ว ไม่ต้องสร้าง")
            return
        
        # สร้าง enum type สำหรับ role (ถ้ายังไม่มี)
        create_enum_query = text("""
            DO $$ BEGIN
                CREATE TYPE contentstaffrole AS ENUM (
                    'actor', 'editor', 'creative', 'cameraman', 'director', 'producer', 'other'
                );
            EXCEPTION
                WHEN duplicate_object THEN null;
            END $$;
        """)
        db.execute(create_enum_query)
        db.commit()
        print("✅ สร้าง enum contentstaffrole สำเร็จ")
        
        # สร้างตาราง
        create_table_query = text("""
            CREATE TABLE content_staff_allocations (
                id SERIAL PRIMARY KEY,
                content_id INTEGER NOT NULL REFERENCES contents(id) ON DELETE CASCADE,
                employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                role contentstaffrole NOT NULL,
                percentage NUMERIC(5, 2) NOT NULL CHECK (percentage >= 0 AND percentage <= 100),
                notes TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP WITH TIME ZONE
            );
            
            CREATE INDEX idx_content_staff_allocations_content_id ON content_staff_allocations(content_id);
            CREATE INDEX idx_content_staff_allocations_employee_id ON content_staff_allocations(employee_id);
            CREATE INDEX idx_content_staff_allocations_deleted_at ON content_staff_allocations(deleted_at) WHERE deleted_at IS NULL;
        """)
        
        db.execute(create_table_query)
        db.commit()
        
        print("✅ สร้างตาราง content_staff_allocations สำเร็จ!")
        print("   - Columns: id, content_id, employee_id, role, percentage, notes")
        print("   - Constraints: percentage 0-100, foreign keys to contents and employees")
        print("   - Indexes: content_id, employee_id, deleted_at")
        
    except Exception as e:
        db.rollback()
        print(f"❌ เกิดข้อผิดพลาด: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_content_staff_allocations_table()

