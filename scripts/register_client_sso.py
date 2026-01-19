"""
Register WeBoostX OAuth Client in JLC SSO Database
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import getpass

CLIENT_SECRET = "e1183296a68b11617e04b75e8afb31fc0ad9321b6b371fceaaeebe8bcda667bb"

def main():
    print("=" * 60)
    print("  Register WeBoostX OAuth Client in JLC SSO")
    print("=" * 60)
    
    # Get password
    print("\nDatabase: jlc_sso_db")
    print("User: postgres")
    password = getpass.getpass("Enter PostgreSQL password: ")
    
    try:
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            dbname="jlc_sso_db",
            user="postgres",
            password=password
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if client exists
        cursor.execute("SELECT client_id FROM oauth_clients WHERE client_id = 'weboostx'")
        existing = cursor.fetchone()
        
        redirect_uris = [
            'http://localhost:8201/auth/callback',
            'http://localhost:9201/auth/callback',
            'https://weboostx.jlcgroup.co/auth/callback'
        ]
        
        if existing:
            print("\n[INFO] Client 'weboostx' exists, updating secret...")
            cursor.execute("""
                UPDATE oauth_clients 
                SET client_secret = %s,
                    redirect_uris = %s,
                    is_active = true,
                    updated_at = NOW()
                WHERE client_id = 'weboostx'
            """, (CLIENT_SECRET, redirect_uris))
            print("[OK] OAuth client updated!")
        else:
            print("\n[INFO] Creating new OAuth client...")
            cursor.execute("""
                INSERT INTO oauth_clients (
                    client_id, client_secret, name, description, 
                    redirect_uris, is_active, created_at
                ) VALUES (
                    'weboostx', %s, 'WeBoostX 2.0', 'Multi-Platform Ad Management',
                    %s, true, NOW()
                )
            """, (CLIENT_SECRET, redirect_uris))
            print("[OK] OAuth client created!")
        
        # Verify
        cursor.execute("SELECT client_id, name, is_active FROM oauth_clients WHERE client_id = 'weboostx'")
        row = cursor.fetchone()
        if row:
            print(f"\n[VERIFIED] Client: {row[0]}, Name: {row[1]}, Active: {row[2]}")
        
        cursor.close()
        conn.close()
        
        print("\n" + "=" * 60)
        print("  SUCCESS! OAuth client registered.")
        print("=" * 60)
        print(f"  Client ID:     weboostx")
        print(f"  Client Secret: {CLIENT_SECRET}")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] {e}")


if __name__ == "__main__":
    main()
