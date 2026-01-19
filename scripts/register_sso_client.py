"""
Register WeBoostX as OAuth client in JLC SSO
Run this once to set up SSO integration
"""
import psycopg2
import secrets


def main():
    # SSO Database connection (jlc_sso_db)
    # Update these values to match your SSO database
    SSO_DB_HOST = "localhost"
    SSO_DB_PORT = 5432
    SSO_DB_NAME = "jlc_sso_db"
    SSO_DB_USER = "sso_user"  # Update with actual username
    SSO_DB_PASSWORD = "your-password"  # Update with actual password
    
    # WeBoostX OAuth client config
    CLIENT_ID = "weboostx"
    CLIENT_SECRET = secrets.token_hex(32)  # Generate secure secret
    CLIENT_NAME = "WeBoostX 2.0"
    DESCRIPTION = "Multi-Platform Ad Management"
    
    # Redirect URIs (add both dev and prod)
    REDIRECT_URIS = [
        "http://localhost:8201/auth/callback",      # Dev
        "http://localhost:9201/auth/callback",      # Prod local
        "https://weboostx.jlcgroup.co/auth/callback"  # Prod domain
    ]
    
    try:
        conn = psycopg2.connect(
            host=SSO_DB_HOST,
            port=SSO_DB_PORT,
            dbname=SSO_DB_NAME,
            user=SSO_DB_USER,
            password=SSO_DB_PASSWORD
        )
        cursor = conn.cursor()
        
        # Check if client already exists
        cursor.execute(
            "SELECT client_id FROM oauth_clients WHERE client_id = %s",
            (CLIENT_ID,)
        )
        existing = cursor.fetchone()
        
        if existing:
            print(f"[WARNING] Client '{CLIENT_ID}' already exists!")
            print("Do you want to update the client secret? (y/n)")
            choice = input().strip().lower()
            if choice == 'y':
                cursor.execute("""
                    UPDATE oauth_clients 
                    SET client_secret = %s, 
                        redirect_uris = %s,
                        updated_at = NOW()
                    WHERE client_id = %s
                """, (CLIENT_SECRET, REDIRECT_URIS, CLIENT_ID))
                conn.commit()
                print("[OK] Client secret updated!")
            else:
                print("[SKIP] No changes made.")
                return
        else:
            # Insert new client
            cursor.execute("""
                INSERT INTO oauth_clients (
                    client_id, 
                    client_secret, 
                    name, 
                    description, 
                    redirect_uris, 
                    is_active,
                    created_at
                ) VALUES (%s, %s, %s, %s, %s, true, NOW())
            """, (CLIENT_ID, CLIENT_SECRET, CLIENT_NAME, DESCRIPTION, REDIRECT_URIS))
            conn.commit()
            print("[OK] OAuth client created!")
        
        print()
        print("=" * 60)
        print("OAuth Client Credentials")
        print("=" * 60)
        print(f"Client ID:     {CLIENT_ID}")
        print(f"Client Secret: {CLIENT_SECRET}")
        print()
        print("Add these to your .env.dev:")
        print("-" * 60)
        print(f"SSO_ENABLED=true")
        print(f"SSO_BASE_URL=http://127.0.0.1:9100")
        print(f"SSO_CLIENT_ID={CLIENT_ID}")
        print(f"SSO_CLIENT_SECRET={CLIENT_SECRET}")
        print(f"SSO_REDIRECT_URI=http://localhost:8201/auth/callback")
        print("=" * 60)
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"[ERROR] {e}")
        print()
        print("Alternative: Run this SQL manually in jlc_sso_db:")
        print("-" * 60)
        print(f"""
INSERT INTO oauth_clients (
    client_id, 
    client_secret, 
    name, 
    description, 
    redirect_uris, 
    is_active
) VALUES (
    '{CLIENT_ID}',
    '{CLIENT_SECRET}',
    '{CLIENT_NAME}',
    '{DESCRIPTION}',
    ARRAY{REDIRECT_URIS},
    true
);
        """)


if __name__ == "__main__":
    main()
