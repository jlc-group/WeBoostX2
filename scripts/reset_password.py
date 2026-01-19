"""
Reset password for a user or create if not exists
Usage: python scripts/reset_password.py
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user import User, UserRole, UserStatus
from app.core.security import get_password_hash


def reset_or_create_user(email: str, password: str):
    """Reset password or create user if not exists"""
    session = SessionLocal()

    try:
        user = session.query(User).filter(User.email == email).first()

        if user:
            # Reset password
            user.password_hash = get_password_hash(password)
            session.commit()
            print(f"✅ Password reset for: {email}")
        else:
            # Create new user
            user = User(
                email=email,
                password_hash=get_password_hash(password),
                first_name="Admin",
                last_name="WeBoostX",
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            session.commit()
            print(f"✅ Created new admin user: {email}")

        print(f"   Password: {password}")
        return True

    except Exception as e:
        session.rollback()
        print(f"❌ Error: {e}")
        return False
    finally:
        session.close()


if __name__ == "__main__":
    email = "admin@jlcgroup.me"
    password = "admin123"

    print("=" * 50)
    print("WeBoostX 2.0 - User Setup")
    print("=" * 50)

    reset_or_create_user(email, password)
