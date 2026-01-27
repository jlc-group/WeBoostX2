import os
import requests
import psycopg2
from dotenv import load_dotenv

load_dotenv()

PG_HOST = os.getenv("PG_HOST")
PG_PORT = os.getenv("PG_PORT")
PG_DB = os.getenv("PG_DB")
PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")
FB_USER_ACCESS_TOKEN = os.getenv("FB_USER_ACCESS_TOKEN").split(',')

COMPANY_AD_ACCOUNT_IDS = ["act_486765798095431", "act_599000711226225"]  # ใส่ id ของบริษัทที่ต้องการ

def insert_ad_account(conn, ad_account):
    """Insert or update Facebook ad account with proper field mapping"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO facebook_ad_accounts (
                id, account_id, name, currency, account_status, 
                business_id, business_name, owner_id, timezone_id, timezone_name,
                created_time, created_at, updated_at
            ) VALUES (
                %(id)s, %(account_id)s, %(name)s, %(currency)s, %(account_status)s,
                %(business_id)s, %(business_name)s, %(owner_id)s, %(timezone_id)s, %(timezone_name)s,
                %(created_time)s, NOW(), NOW()
            )
            ON CONFLICT (id) DO UPDATE SET
                account_id = EXCLUDED.account_id,
                name = EXCLUDED.name,
                currency = EXCLUDED.currency,
                account_status = EXCLUDED.account_status,
                business_id = EXCLUDED.business_id,
                business_name = EXCLUDED.business_name,
                owner_id = EXCLUDED.owner_id,
                timezone_id = EXCLUDED.timezone_id,
                timezone_name = EXCLUDED.timezone_name,
                created_time = EXCLUDED.created_time,
                updated_at = NOW();
        """, ad_account)

def fetch_ad_accounts(token):
    # Use only the most basic fields that are guaranteed to work
    fields = [
        'id',                   # Ad Account ID (required)
        'name',                 # Account name
        'account_status',       # Status: 1=ACTIVE, 2=DISABLED, etc.
        'currency',             # Account currency
        'created_time'          # ISO 8601 datetime
    ]
    
    url = f"https://graph.facebook.com/v23.0/me/adaccounts"
    params = {
        'fields': ','.join(fields),
        'access_token': token
    }
    
    try:
        resp = requests.get(url, params=params)
        resp.raise_for_status()  # Raise exception for HTTP errors
        data = resp.json()
        
        if 'error' in data:
            print(f"Facebook API Error: {data['error']}")
            return []
            
        print(f"Successfully fetched {len(data.get('data', []))} ad accounts")
        print(f"Sample response: {data}")
        return data.get("data", [])
        
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []

def main():
    """Main function to sync Facebook ad accounts to database"""
    try:
        conn = psycopg2.connect(
            host=PG_HOST, port=PG_PORT, dbname=PG_DB,
            user=PG_USER, password=PG_PASSWORD
        )
        conn.autocommit = True
        print("Database connection established")

        total_synced = 0
        
        for i, token in enumerate(FB_USER_ACCESS_TOKEN, 1):
            print(f"\nProcessing token {i}/{len(FB_USER_ACCESS_TOKEN)}")
            ad_accounts = fetch_ad_accounts(token)
            
            for acc in ad_accounts:
                acc_id = acc.get("id")
                
                # Filter only company ad accounts
                if acc_id not in COMPANY_AD_ACCOUNT_IDS:
                    print(f"Skipping non-company account: {acc_id}")
                    continue
                
                # Prepare ad account data with basic fields only
                ad_account = {
                    "id": acc_id,
                    "account_id": None,  # Not available in basic response
                    "name": acc.get("name"),
                    "currency": acc.get("currency"),
                    "account_status": str(acc.get("account_status", "")),
                    "business_id": None,  
                    "business_name": None,  
                    "owner_id": None,  
                    "timezone_id": None,
                    "timezone_name": None,
                    "created_time": acc.get("created_time")
                }
                
                insert_ad_account(conn, ad_account)
                total_synced += 1
                print(f"✓ Synced ad account: {acc_id} - {ad_account.get('name', 'Unknown')}")

        print(f"\n🎉 Successfully synced {total_synced} ad accounts to database")

    except psycopg2.Error as e:
        print(f"Database error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()
            print("Database connection closed")

if __name__ == "__main__":
    main()