"""
Test update API directly
"""
import requests

# Get JWT token first
login_resp = requests.post('http://localhost:8000/api/v1/auth/login', json={
    'email': 'admin@weboostx.com',
    'password': 'admin123'
})
print('Login response:', login_resp.status_code)
if login_resp.status_code != 200:
    print(login_resp.text)
    exit(1)

token = login_resp.json()['data']['access_token']
print(f'Got token: {token[:50]}...')

# Test update
headers = {'Authorization': f'Bearer {token}'}
update_resp = requests.put(
    'http://localhost:8000/api/v1/settings/ad-accounts/5',
    json={'is_active': False},
    headers=headers
)
print()
print(f'Update response: {update_resp.status_code}')
print(update_resp.json())

# Check if it changed
check_resp = requests.get(
    'http://localhost:8000/api/v1/settings/ad-accounts',
    headers=headers
)
print()
print(f'List response: {check_resp.status_code}')
for acc in check_resp.json().get('data', []):
    print(f"  ID:{acc['id']} - {acc['name']} - is_active={acc.get('is_active')}")

