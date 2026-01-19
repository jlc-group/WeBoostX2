import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import uuid

CLIENT_SECRET = "e1183296a68b11617e04b75e8afb31fc0ad9321b6b371fceaaeebe8bcda667bb"

try:
    conn = psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="jlc_sso_db",
        user="postgres",
        password="julaherb789"
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Check if client exists
    cursor.execute("SELECT client_id FROM oauth_clients WHERE client_id = 'weboostx'")
    existing = cursor.fetchone()
    
    redirect_uris = [
        "http://localhost:8201/auth/callback",
        "http://localhost:9201/auth/callback",
        "https://weboostx.jlcgroup.co/auth/callback"
    ]
    
    if existing:
        print("[INFO] Client exists, updating...")
        cursor.execute("""
            UPDATE oauth_clients 
            SET client_secret = %s,
                redirect_uris = %s,
                is_active = true
            WHERE client_id = 'weboostx'
        """, (CLIENT_SECRET, redirect_uris))
        print("[OK] OAuth client updated!")
    else:
        print("[INFO] Creating new OAuth client...")
        client_uuid = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO oauth_clients (
                id, client_id, client_secret, name, description, 
                redirect_uris, is_active, created_at
            ) VALUES (
                %s, 'weboostx', %s, 'WeBoostX 2.0', 'Multi-Platform Ad Management',
                %s, true, NOW()
            )
        """, (client_uuid, CLIENT_SECRET, redirect_uris))
        print("[OK] OAuth client created!")
    
    # Verify
    cursor.execute("SELECT client_id, name, is_active FROM oauth_clients WHERE client_id = 'weboostx'")
    row = cursor.fetchone()
    if row:
        print(f"[VERIFIED] Client: {row[0]}, Name: {row[1]}, Active: {row[2]}")
    
    cursor.close()
    conn.close()
    print("[SUCCESS] OAuth client registered!")
    
except Exception as e:
    print(f"[ERROR] {e}")
