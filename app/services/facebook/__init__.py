# Facebook Services Module

# Legacy mapper (uses psycopg2 only - no httpx needed)
from app.services.facebook.fb_legacy_mapper import (
    FacebookLegacyDB,
    FacebookLegacyMapper,
    get_legacy_db,
    get_legacy_mapper,
)

# Optional: Facebook API (requires httpx)
# Uncomment when httpx is installed:
# from app.services.facebook.fb_api import FacebookAPI
# from app.services.facebook.fb_sync import FacebookSyncService

__all__ = [
    "FacebookLegacyDB",
    "FacebookLegacyMapper",
    "get_legacy_db",
    "get_legacy_mapper",
]
