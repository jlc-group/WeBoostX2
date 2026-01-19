"""List all users in database"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user import User

session = SessionLocal()
users = session.query(User).all()

print("=" * 60)
print("WeBoostX Users")
print("=" * 60)
for u in users:
    print(f"- {u.email} | {u.first_name} {u.last_name} | Role: {u.role}")
print("=" * 60)
print(f"Total: {len(users)} users")
session.close()
