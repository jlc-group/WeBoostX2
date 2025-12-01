"""
Database initialization script - Force use weboostx database
"""
import sys
import os

# Force override DATABASE_URL
os.environ['DATABASE_URL'] = 'postgresql://postgres:julaherb789!@localhost:5432/weboostx'

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Create engine directly
DATABASE_URL = 'postgresql://postgres:julaherb789!@localhost:5432/weboostx'
engine = create_engine(DATABASE_URL, echo=True)

# Import models
from app.models.base import Base
from app.models import *  # Import all models to register them

def create_tables():
    """Create all tables"""
    print("Creating tables in weboostx...")
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully")

def create_initial_data():
    """Create initial data"""
    from app.core.security import get_password_hash
    from app.models.user import User
    from app.models.enums import UserRole, UserStatus
    
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # Check if admin exists
        admin = session.query(User).filter(User.email == "admin@weboostx.com").first()
        
        if not admin:
            admin = User(
                email="admin@weboostx.com",
                password_hash=get_password_hash("admin123"),
                first_name="Admin",
                last_name="WeBoostX",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            session.add(admin)
            session.commit()
            print("✅ Created admin user: admin@weboostx.com / admin123")
        else:
            print("ℹ️ Admin user already exists")
    finally:
        session.close()

def main():
    print("=" * 50)
    print("WeBoostX 2.0 - Force Init to weboostx database")
    print("=" * 50)
    print(f"Database: {DATABASE_URL}")
    
    create_tables()
    create_initial_data()
    
    print("\n✅ Done!")

if __name__ == "__main__":
    main()

