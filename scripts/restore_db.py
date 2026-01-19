"""
Restore database from SQL dump
Strips psql-specific commands and executes via psycopg2
"""
import psycopg2
import os
import re
import sys
from dotenv import load_dotenv

load_dotenv()

def main():
    password = os.getenv('POSTGRES_PWD', '')
    host = os.getenv('POSTGRES_HOST', 'localhost')
    port = os.getenv('POSTGRES_PORT', '5432')
    user = os.getenv('POSTGRES_USER', 'postgres')
    db_name = os.getenv('POSTGRES_DB', 'weboostx_dev_db')
    
    dump_file = r'D:\ShareAll\dump-weboostx-202601162010.sql'
    
    print(f'[RESTORE] Reading {dump_file}...')
    with open(dump_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f'[RESTORE] File size: {len(content):,} bytes')
    
    # Find the weboostx database section
    # Look for the database dump section
    db_section_start = content.find('-- Database "weboostx" dump')
    if db_section_start == -1:
        db_section_start = content.find('-- PostgreSQL database dump')
    
    print(f'[RESTORE] Database section starts at: {db_section_start}')
    
    # Remove psql-specific commands
    lines = content.split('\n')
    cleaned_lines = []
    skip_patterns = [
        r'^\\',  # All backslash commands like \restrict, \unrestrict, \connect
        r'^SET default_transaction_read_only',
    ]
    skip_exact = ['']
    
    for line in lines:
        skip = False
        for pattern in skip_patterns:
            if re.match(pattern, line):
                skip = True
                break
        
        # Also skip CREATE ROLE postgres (already exists)
        if 'CREATE ROLE postgres' in line:
            skip = True
        if 'ALTER ROLE postgres' in line:
            skip = True
        
        if not skip:
            cleaned_lines.append(line)
    
    cleaned_sql = '\n'.join(cleaned_lines)
    
    print(f'[RESTORE] Cleaned SQL: {len(cleaned_sql):,} bytes')
    print(f'[RESTORE] Removed {len(content) - len(cleaned_sql):,} bytes')
    
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
    
    print('[RESTORE] Executing SQL...')
    
    try:
        cursor.execute(cleaned_sql)
        print('[RESTORE] Success!')
    except Exception as e:
        print(f'[ERROR] {e}')
        # Try to execute in smaller chunks
        print('[RESTORE] Trying statement by statement...')
        
        # Split by semicolons but be careful with function bodies
        statements = []
        current = []
        in_function = False
        
        for line in cleaned_lines:
            current.append(line)
            
            if 'CREATE FUNCTION' in line or 'CREATE OR REPLACE FUNCTION' in line:
                in_function = True
            
            if line.strip().endswith(';') and not in_function:
                statements.append('\n'.join(current))
                current = []
            elif line.strip() == '$$;' or line.strip().endswith('$$ LANGUAGE'):
                in_function = False
                statements.append('\n'.join(current))
                current = []
        
        if current:
            statements.append('\n'.join(current))
        
        print(f'[RESTORE] Found {len(statements)} statements')
        
        success = 0
        errors = 0
        for i, stmt in enumerate(statements):
            if stmt.strip() and not stmt.strip().startswith('--'):
                try:
                    cursor.execute(stmt)
                    success += 1
                except Exception as e2:
                    errors += 1
                    if errors <= 5:
                        print(f'[WARN] Statement {i}: {str(e2)[:100]}')
        
        print(f'[RESTORE] Completed: {success} success, {errors} errors')
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    main()
