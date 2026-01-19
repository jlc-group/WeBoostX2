"""
JLC SSO Integration Service
OAuth2 Authorization Code Flow
"""
import secrets
import httpx
from typing import Optional, Dict, Any
from app.core.config import settings


class SSOService:
    """Service for JLC SSO OAuth2 integration"""
    
    def __init__(self):
        self.base_url = settings.SSO_BASE_URL
        self.client_id = settings.SSO_CLIENT_ID
        self.client_secret = settings.SSO_CLIENT_SECRET
        self.redirect_uri = settings.SSO_REDIRECT_URI
    
    def generate_state(self) -> str:
        """Generate random state for CSRF protection"""
        return secrets.token_urlsafe(32)
    
    def get_authorization_url(self, state: str) -> str:
        """Build SSO authorization URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "profile",
            "state": state,
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.base_url}/oauth/authorize?{query}"
    
    async def exchange_code_for_token(self, code: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for access token"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.base_url}/oauth/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self.redirect_uri,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"[SSO] Token exchange failed: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"[SSO] Token exchange error: {e}")
            return None
    
    async def get_user_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Get user info from SSO with access token"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/oauth/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"[SSO] User info failed: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            print(f"[SSO] User info error: {e}")
            return None


# Global instance
sso_service = SSOService()
