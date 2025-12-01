"""
Authentication schemas
"""
from typing import Optional
from pydantic import BaseModel, EmailStr

from app.models.enums import UserRole, UserStatus


class Token(BaseModel):
    """Token response"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Token payload"""
    sub: str
    exp: int
    type: str


class LoginRequest(BaseModel):
    """Login request"""
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    """User registration request"""
    email: EmailStr
    password: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None


class UserResponse(BaseModel):
    """User response"""
    id: int
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    display_name: Optional[str]
    role: UserRole
    status: UserStatus
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """User update request"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None


class PasswordChange(BaseModel):
    """Password change request"""
    current_password: str
    new_password: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""
    refresh_token: str

