"""Check database schema - columns in tables"""
from sqlalchemy import text
from app.core.database import engine
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

with engine.connect() as conn:
    # Check ad_groups columns
    result = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'ad_groups'
        ORDER BY ordinal_position
    """))
    print('=== Columns in ad_groups table ===')
    for row in result:
        print(f'  {row[0]} - {row[1]}')
    
    # Check campaigns columns
    result2 = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'campaigns'
        ORDER BY ordinal_position
    """))
    print('\n=== Columns in campaigns table ===')
    for row in result2:
        print(f'  {row[0]} - {row[1]}')

