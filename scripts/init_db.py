"""
Database initialization script
Creates all tables and initial data
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine, SessionLocal, Base
from app.models import *  # Import all models to register them
from app.core.security import get_password_hash


def create_database():
    """Create the database if it doesn't exist"""
    from sqlalchemy import create_engine
    from app.core.config import settings
    
    # Connect to postgres database to create our database
    postgres_url = f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PWD}@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/postgres"
    temp_engine = create_engine(postgres_url, isolation_level="AUTOCOMMIT")
    
    with temp_engine.connect() as conn:
        # Check if database exists
        result = conn.execute(
            text(f"SELECT 1 FROM pg_database WHERE datname = '{settings.POSTGRES_DB}'")
        )
        exists = result.fetchone() is not None
        
        if not exists:
            conn.execute(text(f"CREATE DATABASE {settings.POSTGRES_DB}"))
            print(f"✅ Created database: {settings.POSTGRES_DB}")
        else:
            print(f"ℹ️ Database already exists: {settings.POSTGRES_DB}")
    
    temp_engine.dispose()


def create_tables():
    """Create all tables"""
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created successfully")


def create_initial_data():
    """Create initial data (admin user, etc.)"""
    session = SessionLocal()
    
    try:
        # Check if admin exists
        admin = session.query(User).filter(User.email == "admin@weboostx.com").first()
        
        if not admin:
            # Create admin user
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
        
        # Create sample content types (if needed)
        # Add more initial data here as needed
        
    except Exception as e:
        session.rollback()
        print(f"❌ Error creating initial data: {e}")
        raise
    finally:
        session.close()


def main():
    """Main initialization function"""
    print("=" * 50)
    print("WeBoostX 2.0 - Database Initialization")
    print("=" * 50)
    
    try:
        # Step 1: Create database
        print("\n📦 Step 1: Creating database...")
        create_database()
        
        # Step 2: Create tables
        print("\n📋 Step 2: Creating tables...")
        create_tables()
        
        # Step 3: Create initial data
        print("\n📝 Step 3: Creating initial data...")
        create_initial_data()
        
        print("\n" + "=" * 50)
        print("✅ Database initialization completed!")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ Initialization failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

