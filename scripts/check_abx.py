"""Check ABX Adgroups"""
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
from app.core.database import SessionLocal
from app.models.abx import ABXAdgroup

db = SessionLocal()
count = db.query(ABXAdgroup).count()
print('ABXAdgroup count:', count)
if count > 0:
    sample = db.query(ABXAdgroup).first()
    print('Sample:', sample.name if sample else None)
db.close()

