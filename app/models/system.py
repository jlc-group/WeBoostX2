"""
System-level models (global settings, etc.)
"""
from sqlalchemy import Column, Integer, String, Boolean, Text

from app.models.base import BaseModel


class AppSetting(BaseModel):
    """
    Key-value settings stored in the database.

    ใช้สำหรับเก็บ config ที่เคยอยู่ใน .env เช่น TikTok client_id / refresh_token ฯลฯ
    """

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)

    # เช่น "tiktok_client_id", "tiktok_business_id"
    key = Column(String(100), unique=True, index=True, nullable=False)

    # เก็บค่าเป็น text (อาจเป็น secret)
    value = Column(Text, nullable=True)

    # หมวดหมู่ เช่น "tiktok", "facebook"
    category = Column(String(50), nullable=True)

    # true = ควรซ่อน/ mask ตอนแสดงผล
    is_secret = Column(Boolean, default=False)

    # คำอธิบายสั้น ๆ
    description = Column(String(255), nullable=True)


