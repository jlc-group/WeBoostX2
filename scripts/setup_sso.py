"""
Setup SSO Integration for WeBoostX
Run all 3 steps in one script
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
import sys

# ============================================
# Configuration
# ============================================
CLIENT_SECRET = "e1183296a68b11617e04b75e8afb31fc0ad9321b6b371fceaaeebe8bcda667bb"

# SSO Database (jlc_sso_db)
SSO_DB = {
    "host": "localhost",
    "port": 5432,
    "dbname": "jlc_sso_db",
    "user": "postgres",
    "password": os.environ.get("POSTGRES_PASSWORD", "")
}

# WeBoostX Database (weboostx_dev_db)
WEBOOSTX_DB = {
    "host": "localhost",
    "port": 5432,
    "dbname": "weboostx_dev_db",
    "user": "weboostx_dev_user",
    "password": "mUisyHGbfByIsWAc"
}


def step1_register_oauth_client():
    """Step 1: Register OAuth client in jlc_sso_db"""
    print("\n" + "=" * 60)
    print("STEP 1: Register OAuth Client in JLC SSO")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(**SSO_DB)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if client exists
        cursor.execute("SELECT client_id FROM oauth_clients WHERE client_id = 'weboostx'")
        existing = cursor.fetchone()
        
        if existing:
            print("[INFO] Client 'weboostx' already exists, updating...")
            cursor.execute("""
                UPDATE oauth_clients 
                SET client_secret = %s,
                    name = 'WeBoostX 2.0',
                    description = 'Multi-Platform Ad Management',
                    redirect_uris = %s,
                    is_active = true,
                    updated_at = NOW()
                WHERE client_id = 'weboostx'
            """, (
                CLIENT_SECRET,
                ['http://localhost:8201/auth/callback',
                 'http://localhost:9201/auth/callback',
                 'https://weboostx.jlcgroup.co/auth/callback']
            ))
            print("[OK] OAuth client updated!")
        else:
            cursor.execute("""
                INSERT INTO oauth_clients (
                    client_id, client_secret, name, description, 
                    redirect_uris, is_active, created_at
                ) VALUES (
                    'weboostx', %s, 'WeBoostX 2.0', 'Multi-Platform Ad Management',
                    %s, true, NOW()
                )
            """, (
                CLIENT_SECRET,
                ['http://localhost:8201/auth/callback',
                 'http://localhost:9201/auth/callback',
                 'https://weboostx.jlcgroup.co/auth/callback']
            ))
            print("[OK] OAuth client created!")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        print("\n[MANUAL] Run this SQL in jlc_sso_db:")
        print("-" * 60)
        print(f"""
INSERT INTO oauth_clients (client_id, client_secret, name, description, redirect_uris, is_active)
VALUES (
    'weboostx',
    '{CLIENT_SECRET}',
    'WeBoostX 2.0',
    'Multi-Platform Ad Management',
    ARRAY['http://localhost:8201/auth/callback', 'http://localhost:9201/auth/callback', 'https://weboostx.jlcgroup.co/auth/callback'],
    true
) ON CONFLICT (client_id) DO UPDATE SET client_secret = EXCLUDED.client_secret;
""")
        return False


def step2_update_env():
    """Step 2: Update .env.dev with SSO config"""
    print("\n" + "=" * 60)
    print("STEP 2: Update .env.dev with SSO config")
    print("=" * 60)
    
    env_path = r"D:\Server\run\weboostx\.env.dev"
    
    sso_config = f"""
# ============================================
# JLC SSO Integration
# ============================================
SSO_ENABLED=true
SSO_BASE_URL=http://127.0.0.1:9100
SSO_CLIENT_ID=weboostx
SSO_CLIENT_SECRET={CLIENT_SECRET}
SSO_REDIRECT_URI=http://localhost:8201/auth/callback
"""
    
    try:
        # Read existing content
        with open(env_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check if SSO config already exists
        if 'SSO_CLIENT_ID' in content:
            print("[INFO] SSO config already exists in .env.dev")
            print("[INFO] Updating SSO_CLIENT_SECRET...")
            
            # Replace existing secret
            lines = content.split('\n')
            new_lines = []
            for line in lines:
                if line.startswith('SSO_CLIENT_SECRET='):
                    new_lines.append(f'SSO_CLIENT_SECRET={CLIENT_SECRET}')
                else:
                    new_lines.append(line)
            
            with open(env_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(new_lines))
            
            print("[OK] SSO_CLIENT_SECRET updated!")
        else:
            # Append SSO config
            with open(env_path, 'a', encoding='utf-8') as f:
                f.write(sso_config)
            print("[OK] SSO config added to .env.dev!")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        print("\n[MANUAL] Add this to D:\\Server\\run\\weboostx\\.env.dev:")
        print("-" * 60)
        print(sso_config)
        return False


def step3_update_schema():
    """Step 3: Add sso_id column to users table"""
    print("\n" + "=" * 60)
    print("STEP 3: Update database schema (add sso_id)")
    print("=" * 60)
    
    try:
        conn = psycopg2.connect(**WEBOOSTX_DB)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()
        
        # Check if column exists
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'sso_id'
        """)
        exists = cursor.fetchone()
        
        if exists:
            print("[INFO] Column 'sso_id' already exists")
        else:
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN sso_id VARCHAR(255) UNIQUE
            """)
            print("[OK] Column 'sso_id' added!")
        
        # Check sso_user column
        cursor.execute("""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = 'users' AND column_name = 'sso_user'
        """)
        exists = cursor.fetchone()
        
        if exists:
            print("[INFO] Column 'sso_user' already exists")
        else:
            cursor.execute("""
                ALTER TABLE users 
                ADD COLUMN sso_user BOOLEAN DEFAULT FALSE
            """)
            print("[OK] Column 'sso_user' added!")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        print("\n[MANUAL] Run this SQL in weboostx_dev_db:")
        print("-" * 60)
        print("""
ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_id VARCHAR(255) UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS sso_user BOOLEAN DEFAULT FALSE;
""")
        return False


def main():
    print("\n" + "=" * 60)
    print("  WeBoostX SSO Integration Setup")
    print("=" * 60)
    
    results = []
    
    # Step 1
    results.append(("Register OAuth Client", step1_register_oauth_client()))
    
    # Step 2
    results.append(("Update .env.dev", step2_update_env()))
    
    # Step 3
    results.append(("Update Schema", step3_update_schema()))
    
    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    
    for name, success in results:
        status = "[OK]" if success else "[FAILED]"
        print(f"  {status} {name}")
    
    print("\n" + "=" * 60)
    print("  SSO Credentials")
    print("=" * 60)
    print(f"  Client ID:     weboostx")
    print(f"  Client Secret: {CLIENT_SECRET}")
    print(f"  Redirect URI:  http://localhost:8201/auth/callback")
    print("=" * 60)
    
    all_success = all(r[1] for r in results)
    if all_success:
        print("\n[SUCCESS] SSO Integration setup complete!")
        print("Restart WeBoostX to apply changes.")
    else:
        print("\n[WARNING] Some steps failed. Check manual instructions above.")


if __name__ == "__main__":
    main()
