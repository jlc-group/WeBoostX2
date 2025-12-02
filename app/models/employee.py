"""
Employee and Influencer models for content creator tracking
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, Text, Date, DateTime, JSON, Numeric
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, SoftDeleteMixin


class Employee(BaseModel, SoftDeleteMixin):
    """
    พนักงานที่ทำ Content สำหรับ Official Page
    ใช้สำหรับประเมิน performance ของพนักงานแต่ละคน
    """
    
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ข้อมูลพนักงาน
    employee_code = Column(String(50), unique=True, nullable=False, index=True)  # รหัสพนักงาน
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    nickname = Column(String(50), nullable=True)
    
    # แผนก/ตำแหน่ง
    department = Column(String(100), nullable=True)  # เช่น Content Team, Marketing
    position = Column(String(100), nullable=True)
    
    # ข้อมูลติดต่อ
    email = Column(String(255), nullable=True)
    phone = Column(String(20), nullable=True)
    
    # สถานะ
    is_active = Column(Boolean, default=True)
    
    # วันที่เริ่มงาน
    start_date = Column(Date, nullable=True)
    
    # TikTok Account (ถ้ามี)
    tiktok_username = Column(String(100), nullable=True)
    
    # หมายเหตุ
    notes = Column(Text, nullable=True)
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
    
    @property
    def display_name(self):
        if self.nickname:
            return f"{self.nickname} ({self.first_name})"
        return self.full_name


class Influencer(BaseModel, SoftDeleteMixin):
    """
    ข้อมูล Influencer สำหรับ track ค่าจ้างและ performance
    """
    
    __tablename__ = "influencers"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ข้อมูล Influencer
    name = Column(String(255), nullable=False)  # ชื่อจริง (ถ้ามี)
    
    # TikTok Info
    tiktok_username = Column(String(100), unique=True, nullable=True, index=True)
    tiktok_user_id = Column(String(100), nullable=True)
    
    # Facebook/IG Info
    facebook_page = Column(String(255), nullable=True)
    instagram_username = Column(String(100), nullable=True)
    
    # Tier/ประเภท
    tier = Column(String(50), nullable=True)  # mega, macro, micro, nano
    
    # ข้อมูลการจ้างงาน
    default_rate = Column(Numeric(12, 2), nullable=True)  # ค่าจ้างเริ่มต้น/คลิป
    currency = Column(String(10), default="THB")
    
    # สถิติ
    total_contents = Column(Integer, default=0)
    total_cost_paid = Column(Numeric(15, 2), default=0)
    avg_views = Column(Integer, default=0)
    avg_engagement_rate = Column(Numeric(5, 2), nullable=True)
    
    # Follower counts (snapshot)
    tiktok_followers = Column(Integer, nullable=True)
    instagram_followers = Column(Integer, nullable=True)
    last_follower_update = Column(DateTime(timezone=True), nullable=True)
    
    # ข้อมูลติดต่อ
    contact_info = Column(JSON, nullable=True)
    # {"email": "...", "phone": "...", "line_id": "...", "agency": "..."}
    
    # สถานะ
    is_active = Column(Boolean, default=True)
    
    # หมายเหตุ
    notes = Column(Text, nullable=True)
    
    @property
    def display_name(self):
        if self.tiktok_username:
            return f"@{self.tiktok_username}"
        return self.name


class ContentCreatorAssignment(BaseModel):
    """
    เชื่อมโยง Content กับ Creator (Employee หรือ Influencer)
    สำหรับกรณีที่ Content นึงอาจมีหลายคนทำ
    """
    
    __tablename__ = "content_creator_assignments"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Content reference
    content_id = Column(Integer, nullable=False, index=True)
    
    # Creator type and ID
    creator_type = Column(String(20), nullable=False)  # 'employee' or 'influencer'
    employee_id = Column(Integer, nullable=True, index=True)
    influencer_id = Column(Integer, nullable=True, index=True)
    
    # ค่าจ้าง (สำหรับ Influencer)
    cost = Column(Numeric(12, 2), nullable=True)
    
    # หมายเหตุ
    role = Column(String(100), nullable=True)  # เช่น 'main', 'support', 'editor'
    notes = Column(Text, nullable=True)

