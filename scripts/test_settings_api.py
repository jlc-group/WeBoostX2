"""
Test settings API
"""
from app.core.database import SessionLocal
from app.models import AdAccount

db = SessionLocal()

# Test getting account
account = db.query(AdAccount).filter(AdAccount.id == 5).first()
print('=== Account from DB ===')
print(f'id: {account.id}')
print(f'name: {account.name}')
print(f'platform: {account.platform}')
print(f'is_active: {account.is_active}')
print(f'has status attr: {hasattr(account, "status")}')
if hasattr(account, 'status'):
    print(f'status value: {account.status}')

# Try creating response manually
from app.schemas.settings import AdAccountResponse
print()
print('=== Trying to create AdAccountResponse ===')
try:
    resp = AdAccountResponse(
        id=account.id,
        name=account.name,
        platform=account.platform,
        external_account_id=account.external_account_id,
        is_active=account.is_active if account.is_active is not None else True,
        timezone=account.timezone,
        currency=account.currency,
    )
    print(f'SUCCESS: {resp}')
    print(f'as dict: {resp.model_dump()}')
except Exception as e:
    print(f'ERROR: {type(e).__name__}: {e}')

db.close()

