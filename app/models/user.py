"""
User and authentication models
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, Text, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel, SoftDeleteMixin
from app.models.enums import UserRole, UserStatus


class User(BaseModel, SoftDeleteMixin):
    """User model for authentication and authorization"""
    
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    
    # Profile
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    display_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    avatar_url = Column(String(500), nullable=True)
    
    # Role & Status
    role = Column(
        Enum(UserRole),
        default=UserRole.VIEWER,
        nullable=False
    )
    status = Column(
        Enum(UserStatus),
        default=UserStatus.PENDING,
        nullable=False
    )
    
    # Approval
    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(String, nullable=True)
    
    # SSO Integration
    sso_id = Column(String(255), unique=True, nullable=True)  # JLC SSO user ID
    sso_user = Column(Boolean, default=False)  # True if user came from SSO
    
    # Settings
    notification_settings = Column(Text, nullable=True)  # JSON string
    
    # Relationships
    notifications = relationship("Notification", back_populates="user", foreign_keys="Notification.user_id")
    
    @property
    def full_name(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.display_name or self.email.split("@")[0]
    
    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
    
    @property
    def can_manage_ads(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.AD_MANAGER]
    
    @property
    def can_manage_content(self) -> bool:
        return self.role in [UserRole.ADMIN, UserRole.AD_MANAGER, UserRole.CONTENT_CREATOR]


class Notification(BaseModel):
    """User notifications"""
    
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=True)
    notification_type = Column(String(50), nullable=True)  # info, warning, error, success
    link = Column(String(500), nullable=True)
    
    is_read = Column(Boolean, default=False)
    
    # Relationships
    user = relationship("User", back_populates="notifications", foreign_keys=[user_id])

