"""
Restore converted SQL file to database
"""
import psycopg2
import os
import re
from dotenv import load_dotenv

load_dotenv()

def main():
    password = os.getenv('POSTGRES_PWD', '')
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5432')
    user = os.getenv('POSTGRES_USER', 'postgres')
    db_name = os.getenv('POSTGRES_DB', 'weboostx_dev_db')
    
    sql_file = r'D:\ShareAll\weboostx-converted.sql'
    
    print(f'[RESTORE] Reading {sql_file}...')
    with open(sql_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f'[RESTORE] File size: {len(content):,} bytes')
    
    # Connect to database
    print(f'[RESTORE] Connecting to {db_name}@{host}:{port}...')
    
    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name
    )
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Split into individual statements
    # Simple split by semicolon at end of line
    lines = content.split('\n')
    
    statements = []
    current = []
    
    for line in lines:
        current.append(line)
        if line.rstrip().endswith(';'):
            statements.append('\n'.join(current))
            current = []
    
    if current:
        statements.append('\n'.join(current))
    
    print(f'[RESTORE] Found {len(statements)} statements')
    
    # Execute statements
    success = 0
    errors = 0
    skip_errors = [
        'already exists',
        'duplicate key',
        'violates unique constraint',
    ]
    
    for i, stmt in enumerate(statements):
        stmt = stmt.strip()
        if not stmt or stmt.startswith('--'):
            continue
        
        try:
            cursor.execute(stmt)
            success += 1
            
            if success % 5000 == 0:
                print(f'[RESTORE] Progress: {success} statements executed...')
                
        except Exception as e:
            error_msg = str(e).lower()
            
            # Skip certain expected errors
            is_expected = any(se in error_msg for se in skip_errors)
            
            if not is_expected:
                errors += 1
                if errors <= 10:
                    # Truncate for display
                    stmt_preview = stmt[:100].replace('\n', ' ')
                    print(f'[ERROR] {str(e)[:100]}')
                    print(f'        Statement: {stmt_preview}...')
    
    print()
    print(f'[RESTORE] Completed!')
    print(f'[RESTORE] Success: {success}')
    print(f'[RESTORE] Errors: {errors}')
    
    # Verify tables
    cursor.execute("""
        SELECT table_name FROM information_schema.tables 
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)
    tables = cursor.fetchall()
    print(f'[RESTORE] Tables in database: {len(tables)}')
    for t in tables:
        print(f'  - {t[0]}')
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
