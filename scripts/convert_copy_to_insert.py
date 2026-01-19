"""
Convert PostgreSQL COPY statements to INSERT statements
for use with psycopg2
"""
import re
import os
from dotenv import load_dotenv

load_dotenv()

def parse_copy_statement(copy_line):
    """Parse COPY statement to get table name and columns"""
    # COPY public.table_name (col1, col2, ...) FROM stdin;
    match = re.match(r'COPY ([\w.]+) \((.+)\) FROM stdin;', copy_line)
    if match:
        table = match.group(1)
        columns = [c.strip() for c in match.group(2).split(',')]
        return table, columns
    return None, None

def main():
    dump_file = r'D:\ShareAll\dump-weboostx-202601162010.sql'
    output_file = r'D:\ShareAll\weboostx-converted.sql'
    
    print(f'[CONVERT] Reading {dump_file}...')
    with open(dump_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f'[CONVERT] Processing {len(lines)} lines...')
    
    output_lines = []
    in_copy = False
    current_table = None
    current_columns = None
    copy_count = 0
    insert_count = 0
    
    for i, line in enumerate(lines):
        # Skip psql-specific commands
        if line.startswith('\\'):
            continue
        
        # Skip database/role creation (we'll use existing db)
        if 'CREATE DATABASE' in line or 'CREATE ROLE' in line:
            continue
        if 'ALTER DATABASE' in line or 'ALTER ROLE' in line:
            continue
        if 'SET ROLE' in line:
            continue
        
        # Handle COPY statement
        if line.startswith('COPY '):
            current_table, current_columns = parse_copy_statement(line.strip())
            if current_table:
                in_copy = True
                copy_count += 1
                if copy_count <= 5:
                    print(f'[COPY] Processing table: {current_table}')
            continue
        
        # End of COPY data
        if in_copy and line.strip() == '\\.':
            in_copy = False
            current_table = None
            current_columns = None
            continue
        
        # Convert COPY data to INSERT
        if in_copy and current_table and current_columns:
            # Parse tab-separated values
            values = line.rstrip('\n').split('\t')
            if len(values) == len(current_columns):
                # Escape values
                escaped_values = []
                for v in values:
                    if v == '\\N':
                        escaped_values.append('NULL')
                    else:
                        # Escape single quotes
                        v = v.replace("'", "''")
                        # Handle escaped characters
                        v = v.replace('\\n', '\n')
                        v = v.replace('\\t', '\t')
                        v = v.replace('\\r', '\r')
                        escaped_values.append(f"'{v}'")
                
                cols = ', '.join(current_columns)
                vals = ', '.join(escaped_values)
                insert = f"INSERT INTO {current_table} ({cols}) VALUES ({vals});\n"
                output_lines.append(insert)
                insert_count += 1
            continue
        
        # Keep other SQL statements
        output_lines.append(line)
    
    print(f'[CONVERT] Converted {copy_count} COPY statements')
    print(f'[CONVERT] Generated {insert_count} INSERT statements')
    print(f'[CONVERT] Writing to {output_file}...')
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(output_lines)
    
    print(f'[CONVERT] Done! Output size: {os.path.getsize(output_file):,} bytes')

if __name__ == '__main__':
    main()
