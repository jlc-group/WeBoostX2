"""Find content with products"""
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
from app.core.database import SessionLocal
from app.models import Content

db = SessionLocal()

# หา content ที่มี product_codes
contents = db.query(Content).filter(Content.product_codes.isnot(None)).limit(10).all()
print('Contents with product_codes:')
for c in contents:
    prods = c.product_codes
    print(f'  ID: {c.id}, Products: {prods}')
db.close()

