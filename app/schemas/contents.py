"""
Schemas สำหรับ Content API
"""
from typing import List

from pydantic import BaseModel


class TikTokImportRequest(BaseModel):
    """Request body สำหรับ import TikTok content ด้วย item_id หรือ URL"""

    items: List[str]


