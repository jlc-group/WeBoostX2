import psycopg2

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="jlc_sso_db",
    user="postgres",
    password="julaherb789"
)
cursor = conn.cursor()

cursor.execute("""
    SELECT column_name, data_type, column_default, is_nullable
    FROM information_schema.columns 
    WHERE table_name = 'oauth_clients'
    ORDER BY ordinal_position
""")

print("oauth_clients table schema:")
print("-" * 80)
for row in cursor.fetchall():
    print(f"{row[0]:20} | {row[1]:15} | {str(row[2]):30} | {row[3]}")

cursor.close()
conn.close()
