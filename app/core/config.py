"""
WeBoostX 2.0 Configuration
Load settings from environment variables
"""
from functools import lru_cache
from typing import Optional, List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # ============================================
    # Application Settings
    # ============================================
    APP_NAME: str = "WeBoostX 2.0"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = True  # Enable debug by default for development
    ENVIRONMENT: str = "development"  # development, staging, production
    
    # ============================================
    # Database Settings
    # ============================================
    POSTGRES_USER: str = "postgres"
    POSTGRES_PWD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "weboostx"
    DATABASE_URL: Optional[str] = None
    
    @property
    def database_url(self) -> str:
        """Get database URL, construct from parts if not provided"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PWD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @property
    def async_database_url(self) -> str:
        """Get async database URL for SQLAlchemy async"""
        url = self.database_url
        return url.replace("postgresql://", "postgresql+asyncpg://")
    
    # ============================================
    # Security Settings
    # ============================================
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"
    
    # ============================================
    # CORS Settings
    # ============================================
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    # ============================================
    # TikTok API Settings
    # ============================================
    TIKTOK_APP_ID: Optional[str] = None
    TIKTOK_APP_SECRET: Optional[str] = None
    # Primary access token fields (new system)
    TIKTOK_ACCESS_TOKEN: Optional[str] = None
    TIKTOK_BUSINESS_ID: Optional[str] = None
    # OAuth2 refresh-flow (เหมือนระบบเดิม แต่ย้ายมาอยู่ใน .env)
    TIKTOK_CLIENT_ID: Optional[str] = None
    TIKTOK_CLIENT_SECRET: Optional[str] = None
    TIKTOK_REFRESH_TOKEN: Optional[str] = None
    # Backwards-compatible env names from legacy systems
    TIKTOK_MAIN_ACCESS_TOKEN: Optional[str] = None
    BUSINESS_ID: Optional[str] = None
    TIKTOK_AD_TOKEN: Optional[str] = None
    ADVERTISER_ID_IDAC_MAIN: Optional[str] = None
    ADVERTISER_ID_IDAC_ECOM: Optional[str] = None
    ADVERTISER_ID_IDAC_JDENT: Optional[str] = None
    ADVERTISER_ID_ENTRA: Optional[str] = None
    ADVERTISER_ID_GRVT: Optional[str] = None
    TIKTOK_API_BASE_URL: str = "https://business-api.tiktok.com/open_api/v1.3"
    
    # ============================================
    # Facebook/Meta API Settings
    # ============================================
    FACEBOOK_APP_ID: Optional[str] = None
    FACEBOOK_APP_SECRET: Optional[str] = None
    FACEBOOK_ACCESS_TOKEN: Optional[str] = None
    FACEBOOK_API_VERSION: str = "v19.0"
    FACEBOOK_API_BASE_URL: str = "https://graph.facebook.com"
    
    @property
    def facebook_api_url(self) -> str:
        return f"{self.FACEBOOK_API_BASE_URL}/{self.FACEBOOK_API_VERSION}"
    
    # ============================================
    # LINE Notify Settings
    # ============================================
    LINE_NOTIFY_TOKEN: Optional[str] = None
    LINE_NOTIFY_TOKEN_ADMIN: Optional[str] = None
    
    # ============================================
    # Scheduler Settings
    # ============================================
    SCHEDULER_ENABLED: bool = True
    CONTENT_SYNC_INTERVAL_MINUTES: int = 60
    AD_SYNC_INTERVAL_MINUTES: int = 30
    OPTIMIZATION_INTERVAL_HOURS: int = 2
    
    # ============================================
    # Redis Settings (for caching/celery)
    # ============================================
    REDIS_URL: Optional[str] = None
    
    @property
    def tiktok_content_access_token(self) -> Optional[str]:
        """
        Effective TikTok token used for content sync.
        Prefer TIKTOK_ACCESS_TOKEN, fall back to legacy envs.
        """
        return (
            self.TIKTOK_ACCESS_TOKEN
            or self.TIKTOK_MAIN_ACCESS_TOKEN
            or self.TIKTOK_AD_TOKEN
        )

    @property
    def tiktok_business_id(self) -> Optional[str]:
        """
        Effective TikTok business id used for content sync.
        Prefer TIKTOK_BUSINESS_ID, fall back to legacy BUSINESS_ID.
        """
        return self.TIKTOK_BUSINESS_ID or self.BUSINESS_ID

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from .env


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Global settings instance
settings = get_settings()

