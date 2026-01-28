"""
Dual Database Configuration
- Facebook DB: Local PostgreSQL (localhost:5433)
- TikTok DB: AWS RDS (starcontent)
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

# Facebook Database (Local)
FACEBOOK_DATABASE_URL = "postgresql://postgres:Ais%409894@localhost:5433/postgres"

# TikTok Database (AWS RDS)
TIKTOK_DATABASE_URL = "postgresql://julaherbbackend:dd4kL75DmjwLf8M4aXdj@saversure-julaherb-db-dev-2.cms4i8jm3njf.ap-southeast-1.rds.amazonaws.com:5432/starcontent"

# Create engines
facebook_engine = create_engine(
    FACEBOOK_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False
)

tiktok_engine = create_engine(
    TIKTOK_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False
)

# Create session factories
FacebookSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=facebook_engine)
TiktokSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=tiktok_engine)


def get_facebook_db() -> Generator[Session, None, None]:
    """Get Facebook database session"""
    db = FacebookSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tiktok_db() -> Generator[Session, None, None]:
    """Get TikTok database session"""
    db = TiktokSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Helper functions for direct queries
def get_facebook_session() -> Session:
    """Get a new Facebook database session (remember to close it!)"""
    return FacebookSessionLocal()


def get_tiktok_session() -> Session:
    """Get a new TikTok database session (remember to close it!)"""
    return TiktokSessionLocal()
