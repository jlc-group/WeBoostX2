"""
TikTok Targeting Service

Service for fetching targeting options from TikTok Business API:
- Interest Categories (hierarchical tree)
- Action Categories (Video Related, Creator Related, Hashtag Related)
- Locations/Regions
- Languages
"""

import json
from typing import Dict, List, Optional, Any
import httpx

from app.core.config import settings
from app.services.tiktok_service import TikTokService


class TikTokTargetingService:
    """Service for fetching targeting options from TikTok API"""
    
    BASE_URL = settings.TIKTOK_API_BASE_URL
    
    @classmethod
    def _get_access_token(cls) -> Optional[str]:
        """
        Get TikTok access token - เหมือน TikTokAdsService
        
        ลำดับความสำคัญ:
        1) TIKTOK_AD_TOKEN (legacy)
        2) TikTokService.get_access_token() (refresh flow)
        3) tiktok_content_access_token (fallback)
        """
        # 1) token ฝั่ง Ads โดยตรง (legacy behavior)
        if settings.TIKTOK_AD_TOKEN:
            return settings.TIKTOK_AD_TOKEN
        
        # 2) token refresh-flow จาก TikTokService
        token = TikTokService.get_access_token()
        if token:
            return token
        
        # 3) fallback สุดท้าย
        return settings.tiktok_content_access_token or ""
    
    @classmethod
    def _get_advertiser_id(cls) -> Optional[str]:
        """Get default advertiser ID from settings"""
        return settings.ADVERTISER_ID_IDAC_MAIN
    
    @classmethod
    def _get_client(cls) -> httpx.Client:
        """Create HTTP client with proper timeout"""
        return httpx.Client(timeout=30.0)
    
    # ============================================
    # Interest Categories (Tree Structure)
    # ============================================
    
    @classmethod
    def fetch_interest_categories(cls, language: str = "th", version: int = 2) -> Dict:
        """
        Fetch interest categories from TikTok API
        
        Returns hierarchical data with:
        - interest_category_id
        - interest_category_name
        - level (1-4)
        - sub_category_ids (children)
        """
        token = cls._get_access_token()
        advertiser_id = cls._get_advertiser_id()
        
        if not token or not advertiser_id:
            return {"error": "Missing TikTok credentials", "data": []}
        
        url = f"{cls.BASE_URL}/tool/interest_category/"
        
        with cls._get_client() as client:
            try:
                resp = client.get(
                    url,
                    headers={"Access-Token": token},
                    params={
                        "advertiser_id": advertiser_id,
                        "language": language,
                        "version": version
                    }
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokTargetingService] fetch_interest_categories error: {resp.status_code}")
                    return {"error": f"API error: {resp.status_code}", "data": []}
                
                data = resp.json()
                
                if data.get("code") != 0:
                    return {"error": data.get("message", "Unknown error"), "data": []}
                
                interest_categories = data.get("data", {}).get("interest_categories", [])
                
                return {
                    "success": True,
                    "data": interest_categories,
                    "count": len(interest_categories)
                }
                
            except Exception as e:
                print(f"[TikTokTargetingService] fetch_interest_categories exception: {e}")
                return {"error": str(e), "data": []}
    
    # ============================================
    # Action Categories (Video, Creator, Hashtag)
    # ============================================
    
    @classmethod
    def fetch_action_categories(cls, language: str = "th", special_industries: List[str] = None) -> Dict:
        """
        Fetch action categories from TikTok API
        
        Returns data with action_scene types:
        - VIDEO_RELATED
        - CREATOR_RELATED
        - HASHTAG_RELATED
        """
        token = cls._get_access_token()
        advertiser_id = cls._get_advertiser_id()
        
        if not token or not advertiser_id:
            return {"error": "Missing TikTok credentials", "data": []}
        
        url = f"{cls.BASE_URL}/tool/action_category/"
        
        params = {
            "advertiser_id": advertiser_id,
            "language": language
        }
        
        if special_industries:
            params["special_industries"] = json.dumps(special_industries)
        
        with cls._get_client() as client:
            try:
                resp = client.get(
                    url,
                    headers={"Access-Token": token},
                    params=params
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokTargetingService] fetch_action_categories error: {resp.status_code}")
                    return {"error": f"API error: {resp.status_code}", "data": []}
                
                data = resp.json()
                
                if data.get("code") != 0:
                    return {"error": data.get("message", "Unknown error"), "data": []}
                
                action_categories = data.get("data", {}).get("action_categories", [])
                
                # Group by action_scene
                video_related = [c for c in action_categories if c.get("action_scene") == "VIDEO_RELATED"]
                creator_related = [c for c in action_categories if c.get("action_scene") == "CREATOR_RELATED"]
                hashtag_related = [c for c in action_categories if c.get("action_scene") == "HASHTAG_RELATED"]
                
                return {
                    "success": True,
                    "data": action_categories,
                    "video_related": video_related,
                    "creator_related": creator_related,
                    "hashtag_related": hashtag_related,
                    "count": len(action_categories)
                }
                
            except Exception as e:
                print(f"[TikTokTargetingService] fetch_action_categories exception: {e}")
                return {"error": str(e), "data": []}
    
    # ============================================
    # Locations/Regions
    # ============================================
    
    @classmethod
    def fetch_regions(cls, language: str = "th", objective_type: str = "VIDEO_VIEWS") -> Dict:
        """
        Fetch available regions/locations from TikTok API
        
        Returns list of regions with:
        - location_id
        - name
        - region_code
        - level
        """
        token = cls._get_access_token()
        advertiser_id = cls._get_advertiser_id()
        
        if not token or not advertiser_id:
            return {"error": "Missing TikTok credentials", "data": []}
        
        url = f"{cls.BASE_URL}/tool/region/"
        
        with cls._get_client() as client:
            try:
                resp = client.get(
                    url,
                    headers={"Access-Token": token},
                    params={
                        "advertiser_id": advertiser_id,
                        "placements": '["PLACEMENT_TIKTOK"]',
                        "objective_type": objective_type,
                        "language": language
                    }
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokTargetingService] fetch_regions error: {resp.status_code}")
                    return {"error": f"API error: {resp.status_code}", "data": []}
                
                data = resp.json()
                
                if data.get("code") != 0:
                    return {"error": data.get("message", "Unknown error"), "data": []}
                
                regions = data.get("data", {}).get("region_info", [])
                
                # Filter for Thailand (TH) regions
                th_regions = [r for r in regions if r.get("region_code") == "TH"]
                
                return {
                    "success": True,
                    "data": th_regions,
                    "all_regions": regions,
                    "count": len(th_regions)
                }
                
            except Exception as e:
                print(f"[TikTokTargetingService] fetch_regions exception: {e}")
                return {"error": str(e), "data": []}
    
    # ============================================
    # Languages
    # ============================================
    
    @classmethod
    def fetch_languages(cls) -> Dict:
        """
        Fetch available languages from TikTok API
        """
        token = cls._get_access_token()
        
        if not token:
            return {"error": "Missing TikTok credentials", "data": []}
        
        # TikTok Language API (v1)
        url = "https://business-api.tiktok.com/open_api/v1/targeting/languages"
        
        with cls._get_client() as client:
            try:
                resp = client.post(
                    url,
                    headers={"Access-Token": token}
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokTargetingService] fetch_languages error: {resp.status_code}")
                    return {"error": f"API error: {resp.status_code}", "data": []}
                
                data = resp.json()
                languages = data.get("data", [])
                
                return {
                    "success": True,
                    "data": languages,
                    "count": len(languages)
                }
                
            except Exception as e:
                print(f"[TikTokTargetingService] fetch_languages exception: {e}")
                return {"error": str(e), "data": []}
    
    # ============================================
    # Hashtag Search
    # ============================================
    
    @classmethod
    def recommend_hashtags(cls, keywords: List[str]) -> Dict:
        """
        Search/Recommend hashtags by keywords
        Matches old system: /tool/hashtag/recommend/
        """
        token = cls._get_access_token()
        advertiser_id = cls._get_advertiser_id()
        
        if not token or not advertiser_id:
            return {"error": "Missing TikTok credentials", "data": []}
        
        url = f"{cls.BASE_URL}/tool/hashtag/recommend/"
        
        with cls._get_client() as client:
            try:
                resp = client.get(
                    url,
                    headers={"Access-Token": token},
                    params={
                        "advertiser_id": advertiser_id,
                        "keywords": json.dumps(keywords),
                        "operator": "OR"
                    }
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokTargetingService] recommend_hashtags error: {resp.status_code}")
                    return {"error": f"API error: {resp.status_code}", "data": []}
                
                data = resp.json()
                # DEBUG
                print(f"[TikTokTargetingService] recommend_hashtags response: {data}")
                
                if data.get("code") != 0:
                    return {"error": data.get("message", "Unknown error"), "data": []}
                
                hashtags = data.get("data", {}).get("recommend_keywords", [])
                
                return {
                    "success": True,
                    "data": hashtags,
                    "count": len(hashtags)
                }
                
            except Exception as e:
                print(f"[TikTokTargetingService] recommend_hashtags exception: {e}")
                return {"error": str(e), "data": []}
    
    # ============================================
    # Hashtag Status
    # ============================================
    
    @classmethod
    def check_hashtag_status(cls, keyword_ids: List[str]) -> Dict:
        """
        Check status of hashtags (ONLINE/OFFLINE)
        Matches old system: /tool/hashtag/get/
        """
        token = cls._get_access_token()
        advertiser_id = cls._get_advertiser_id()
        
        if not token or not advertiser_id:
            return {"error": "Missing TikTok credentials", "data": []}
        
        url = f"{cls.BASE_URL}/tool/hashtag/get/"
        
        with cls._get_client() as client:
            try:
                resp = client.get(
                    url,
                    headers={"Access-Token": token},
                    params={
                        "advertiser_id": advertiser_id,
                        "keyword_ids": json.dumps(keyword_ids)
                    }
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokTargetingService] check_hashtag_status error: {resp.status_code}")
                    return {"error": f"API error: {resp.status_code}", "data": []}
                
                data = resp.json()
                
                if data.get("code") != 0:
                    return {"error": data.get("message", "Unknown error"), "data": []}
                
                # Response structure: { "data": { "keywords_status": [ { "keyword_id": "...", "keyword_status": "ONLINE", "keyword": "..." } ] } }
                keywords_status = data.get("data", {}).get("keywords_status", [])
                
                return {
                    "success": True,
                    "data": keywords_status,
                    "count": len(keywords_status)
                }
                
            except Exception as e:
                print(f"[TikTokTargetingService] check_hashtag_status exception: {e}")
                return {"error": str(e), "data": []}

    # ============================================
    # Audience Size Estimation
    # ============================================
    
    @classmethod
    def get_audience_size(
        cls,
        location_ids: List[str] = None,
        age_groups: List[str] = None,
        gender: str = "GENDER_UNLIMITED",
        languages: List[str] = None,
        interest_category_ids: List[str] = None,
        action_categories: List[Dict] = None
    ) -> Dict:
        """
        Get estimated audience size for targeting criteria
        Uses old system endpoint: /ad/audience_size/estimate/
        """
        token = cls._get_access_token()
        advertiser_id = cls._get_advertiser_id()
        
        if not token or not advertiser_id:
            return {"error": "Missing TikTok credentials", "data": None}
        
        # Use endpoint from old system
        url = "https://business-api.tiktok.com/open_api/v1.3/ad/audience_size/estimate/"
        
        # Construct payload to match old system
        request_data = {
            "advertiser_id": advertiser_id,
            "location_ids": location_ids if location_ids else ["6252001"],  # Default to Thailand if empty
            "age_groups": age_groups if age_groups else [],
            "genders": [gender] if gender else ["GENDER_UNLIMITED"],
            "languages": languages if languages else [],
            "interest_category_ids": [str(i) for i in interest_category_ids] if interest_category_ids else [],
            "actions": action_categories if action_categories else [],
            "placement_type": 'PLACEMENT_TYPE_NORMAL',
            "objective_type": 'REACH',
            "optimization_goal": 'REACH'
        }
        
        with cls._get_client() as client:
            try:
                resp = client.post(
                    url,
                    headers={
                        "Access-Token": token,
                        "Content-Type": "application/json"
                    },
                    json=request_data
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokTargetingService] get_audience_size error: {resp.status_code}")
                    # print(resp.text)
                    return {"error": f"API error: {resp.status_code} - {resp.text}", "data": None}
                
                data = resp.json()
                
                if data.get("code") != 0:
                    return {"error": data.get("message", "Unknown error"), "data": None}
                
                return {
                    "success": True,
                    "data": data.get("data", {})
                }
                
            except Exception as e:
                print(f"[TikTokTargetingService] get_audience_size exception: {e}")
                return {"error": str(e), "data": None}
    
    # ============================================
    # Static Data (Age Groups, Genders)
    # ============================================
    
    @classmethod
    def get_age_groups(cls) -> List[Dict]:
        """Get available age group options"""
        return [
            {"id": "AGE_13_17", "name": "13-17"},
            {"id": "AGE_18_24", "name": "18-24"},
            {"id": "AGE_25_34", "name": "25-34"},
            {"id": "AGE_35_44", "name": "35-44"},
            {"id": "AGE_45_54", "name": "45-54"},
            {"id": "AGE_55_100", "name": "55+"},
        ]
    
    @classmethod
    def get_genders(cls) -> List[Dict]:
        """Get available gender options"""
        return [
            {"id": "GENDER_UNLIMITED", "name": "ทั้งหมด (All)"},
            {"id": "GENDER_MALE", "name": "ชาย (Male)"},
            {"id": "GENDER_FEMALE", "name": "หญิง (Female)"},
        ]
