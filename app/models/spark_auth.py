"""
Spark Ad Authorization Model - เก็บ Auth Codes จาก Influencers

ใช้สำหรับ:
1. Pre-register auth codes ก่อนยิง ad (bulk import)
2. ระบบจับคู่ auth code กับ content อัตโนมัติ
3. Fallback manual input ตอนสร้าง ad
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, Text, Date, DateTime, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime

from app.models.base import BaseModel, SoftDeleteMixin
from app.models.enums import Platform


class SparkAuthStatus(str, __import__('enum').Enum):
    """Status of Spark Ad Authorization"""
    PENDING = "pending"           # รอ authorize กับ TikTok
    AUTHORIZED = "authorized"     # Authorize แล้ว รอจับคู่กับ content
    BOUND = "bound"               # จับคู่กับ content แล้ว
    USED = "used"                 # ถูกใช้สร้าง ad แล้ว
    EXPIRED = "expired"           # หมดอายุ
    FAILED = "failed"             # Authorize ไม่สำเร็จ
    REVOKED = "revoked"           # ถูกยกเลิก


class SparkAdAuth(BaseModel, SoftDeleteMixin):
    """
    เก็บ Auth Codes จาก Influencers สำหรับ Spark Ads
    
    Flow:
    1. Import auth_code (status=PENDING)
    2. Call TikTok API /tt_video/authorize/ 
       - สำเร็จ → status=AUTHORIZED, ได้ item_id + auth_end_time
       - ไม่สำเร็จ → status=FAILED
    3. Auto-match หา content ที่มี platform_post_id = item_id
       - เจอ → status=BOUND, content_id = matched content
    4. ตอนสร้าง ad จะเช็คว่า content มี auth ที่ BOUND/AUTHORIZED ไหม
       - มี → ใช้ได้เลย, status=USED
       - ไม่มี → แสดง UI ให้กรอก manual
    """
    
    __tablename__ = "spark_ad_auths"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Auth Code Info (จาก Influencer)
    # ============================================
    auth_code = Column(String(255), nullable=False, index=True)
    platform = Column(Enum(Platform), default=Platform.TIKTOK, nullable=False)
    
    # Status tracking
    status = Column(Enum(SparkAuthStatus), default=SparkAuthStatus.PENDING, index=True)
    error_message = Column(Text, nullable=True)  # เก็บ error ถ้า authorize ไม่สำเร็จ
    
    # ============================================
    # Influencer Info (optional - สำหรับ tracking)
    # ============================================
    influencer_id = Column(Integer, ForeignKey("influencers.id"), nullable=True, index=True)
    influencer_name = Column(String(255), nullable=True)  # ชื่อ influencer ที่ส่ง code มา
    creator_username = Column(String(255), nullable=True)  # TikTok username
    
    # Agency/Source info
    agency_name = Column(String(255), nullable=True)  # ชื่อ agency ที่ส่งมา
    batch_name = Column(String(255), nullable=True)   # ชื่อ batch/campaign ที่ import
    notes = Column(Text, nullable=True)               # หมายเหตุ
    
    # ============================================
    # TikTok API Response (หลัง authorize)
    # ============================================
    item_id = Column(String(100), nullable=True, index=True)  # TikTok post ID
    identity_id = Column(String(100), nullable=True)
    identity_type = Column(String(50), nullable=True)  # AUTH_CODE, TT_USER
    
    # Authorization dates
    auth_start_time = Column(DateTime(timezone=True), nullable=True)
    auth_end_time = Column(DateTime(timezone=True), nullable=True)
    ad_auth_status = Column(String(50), nullable=True)  # Status จาก TikTok
    
    # ============================================
    # Binding Info (เมื่อจับคู่กับ content)
    # ============================================
    content_id = Column(Integer, ForeignKey("contents.id"), nullable=True, index=True)
    ad_account_id = Column(Integer, ForeignKey("ad_accounts.id"), nullable=True, index=True)
    
    # ============================================
    # Usage Tracking
    # ============================================
    authorized_at = Column(DateTime(timezone=True), nullable=True)
    bound_at = Column(DateTime(timezone=True), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    used_in_ad_id = Column(Integer, ForeignKey("ads.id"), nullable=True)
    
    # Who imported this code
    imported_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    imported_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # ============================================
    # Relationships
    # ============================================
    influencer = relationship("Influencer", backref="spark_auths", foreign_keys=[influencer_id])
    content = relationship("Content", backref="spark_auths", foreign_keys=[content_id])
    ad_account = relationship("AdAccount", backref="spark_auths", foreign_keys=[ad_account_id])
    
    def __repr__(self):
        return f"<SparkAdAuth {self.id}: {self.auth_code[:10]}... status={self.status.value}>"
    
    @property
    def is_usable(self) -> bool:
        """ตรวจสอบว่า auth code นี้ใช้ได้หรือไม่"""
        from datetime import datetime, timezone
        
        # Status ต้องเป็น AUTHORIZED หรือ BOUND
        if self.status not in [SparkAuthStatus.AUTHORIZED, SparkAuthStatus.BOUND]:
            return False
        
        # ต้องไม่หมดอายุ
        if self.auth_end_time:
            now = datetime.now(timezone.utc)
            if self.auth_end_time < now:
                return False
        
        return True
    
    @property
    def days_until_expire(self) -> int:
        """จำนวนวันก่อนหมดอายุ"""
        from datetime import datetime, timezone
        
        if not self.auth_end_time:
            return -1
        
        now = datetime.now(timezone.utc)
        delta = self.auth_end_time - now
        return max(delta.days, 0)


class SparkAuthImportLog(BaseModel):
    """Log การ import auth codes"""
    
    __tablename__ = "spark_auth_import_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Import info
    batch_name = Column(String(255), nullable=True)
    agency_name = Column(String(255), nullable=True)
    source = Column(String(50), nullable=True)  # 'csv', 'manual', 'api'
    
    # Stats
    total_codes = Column(Integer, default=0)
    authorized_count = Column(Integer, default=0)
    bound_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    
    # Details
    details = Column(JSON, nullable=True)  # รายละเอียดแต่ละ code
    
    # Who imported
    imported_by = Column(Integer, ForeignKey("users.id"), nullable=True)

