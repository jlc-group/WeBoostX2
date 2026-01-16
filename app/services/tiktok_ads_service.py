"""
TikTok Ads Service - ดึงข้อมูลโฆษณาและแมปกลับไปหา Content

โฟกัสเวอร์ชันแรก:
    - ดึงรายการ Ads จาก Business API `/ad/get/` ตาม TikTok Ad Accounts (advertiser_id)
    - สร้าง/อัปเดต Campaign, AdGroup, Ad ในฐานข้อมูล
    - แมป Ad แต่ละตัวกลับไปหา `Content` ผ่าน `tiktok_item_id` → upsert `Ad.content_id`
    - อัปเดตฟิลด์ `ads_count` และ `ads_details['tiktok']` ใน `Content`

NOTE:
    - ยัง **ไม่ได้** ดึง spend/report แบบละเอียด (total_spend ยังเป็น 0)
      ส่วนนี้จะต่อยอดภายหลังด้วย report API แยกต่างหาก
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import (
    Ad,
    AdAccount,
    AdGroup,
    Campaign,
    Content,
    Platform,
)
from app.models.enums import AdAccountStatus, AdStatus
from app.models.enums import Platform as PlatformEnum
from app.services.tiktok_service import TikTokService


def _truncate(value: Optional[str], max_length: int = 255) -> Optional[str]:
    """ตัด string ไม่ให้ยาวเกินความยาวคอลัมน์ในฐานข้อมูล"""
    if value is None:
        return None
    s = str(value)
    return s if len(s) <= max_length else s[:max_length]


class TikTokAdsService:
    """บริการดึงและ sync ข้อมูล TikTok Ads"""

    BASE_URL = settings.TIKTOK_API_BASE_URL

    @classmethod
    def _get_access_token(cls) -> str:
        """
        ดึง access token สำหรับ TikTok Ads API.

        ลำดับความสำคัญ:
        1) ถ้ามี TIKTOK_AD_TOKEN ใน .env → ใช้อันนี้ก่อน (เหมือนระบบเดิม)
        2) ถ้าไม่มี ให้ใช้ token จาก TikTokService.get_access_token()
        3) ถ้าไม่ได้ทั้งสอง ให้ fallback ไปที่ settings.tiktok_content_access_token
        """
        # 1) token ฝั่ง Ads โดยตรง (legacy behavior)
        if settings.TIKTOK_AD_TOKEN:
            return settings.TIKTOK_AD_TOKEN

        # 2) token refresh-flow จาก TikTokService (เน้น content scope)
        token = TikTokService.get_access_token()
        if token:
            return token

        # 3) fallback สุดท้าย
        return settings.tiktok_content_access_token or ""

    @classmethod
    def _get_client(cls) -> httpx.Client:
        return httpx.Client(timeout=30.0)

    @classmethod
    def fetch_ads_last_days(
        cls, advertiser_id: str, days: int = 31
    ) -> List[Dict]:
        """
        ดึง Ads ของ advertiser_id ในช่วง N วันที่ผ่านมา

        - ใช้ endpoint `/ad/get/` ของ TikTok Business API
        - ใช้ pagination ผ่าน field `page_info`
        - ถ้า days = -1 หรือ None จะดึง ads ทั้งหมดโดยไม่มี filter (full sync)
        """

        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_ads_last_days")
            return []

        # days = -1 หรือ None หมายถึงไม่ใช้ filter (ดึง ads ทั้งหมด)
        use_date_filter = days is not None and days > 0

        all_ads: List[Dict] = []
        page = 1

        with cls._get_client() as client:
            while True:
                params = {
                    "advertiser_id": advertiser_id,
                    "fields": json.dumps(
                        [
                            "advertiser_id",
                            "campaign_id",
                            "adgroup_id",
                            "ad_id",
                            "tiktok_item_id",
                            "ad_name",
                            "operation_status",
                            "app_name",
                            "adgroup_name",
                            "campaign_name",
                            "ad_text",
                            "display_name",
                            "create_time",
                            "secondary_status",
                            "modify_time",
                        ]
                    ),
                    "page": page,
                    "page_size": 1000,  # ใช้ page_size 1000 เหมือนระบบเก่า
                }

                # ถ้ามี filter ตาม creation time
                if use_date_filter:
                    end_date = datetime.utcnow()
                    start_date = end_date - timedelta(days=days)
                    start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
                    end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")
                    
                    filtering = {
                        "creation_filter_start_time": start_str,
                        "creation_filter_end_time": end_str,
                    }
                    params["filtering"] = json.dumps(filtering)
                    print(f"[TikTokAdsService] Fetching ads created in last {days} days")
                else:
                    print(f"[TikTokAdsService] Fetching ALL ads (no date filter)")

                url = f"{cls.BASE_URL}/ad/get/"

                try:
                    resp = client.get(
                        url,
                        headers={"Access-Token": token},
                        params=params,
                    )
                    if resp.status_code != 200:
                        print(
                            f"[TikTokAdsService] fetch_ads_last_days error "
                            f"{resp.status_code}: {resp.text}"
                        )
                        break

                    data = resp.json()
                except Exception as e:
                    print(f"[TikTokAdsService] HTTP error while fetching ads: {e}")
                    break

                if not isinstance(data, dict) or "data" not in data:
                    print(f"[TikTokAdsService] Unexpected response: {data}")
                    break

                d = data["data"]
                ads = d.get("list") or []
                if not ads:
                    if page == 1:
                        print(f"[TikTokAdsService] No ads found for advertiser_id={advertiser_id}")
                    break

                all_ads.extend(ads)

                page_info = d.get("page_info") or {}
                total_page = page_info.get("total_page") or 1
                print(
                    f"[TikTokAdsService] advertiser_id={advertiser_id} "
                    f"page {page}/{total_page}, ads_so_far={len(all_ads)}"
                )

                if page >= total_page:
                    break
                page += 1


        return all_ads

    @classmethod
    def fetch_active_ad_ids_with_spend(
        cls, advertiser_id: str, days: int = 7
    ) -> Dict[str, float]:
        """
        ดึง ad_ids ที่มี spend ภายใน N วันที่ผ่านมา
        
        ใช้ report endpoint เพื่อดึงเฉพาะ ads ที่มี activity
        ไม่ต้องระบุ ad_ids ล่วงหน้า - จะดึงทั้งหมดที่มี spend
        
        Returns:
            Dict[ad_id, spend_in_period] - ad_id และ spend ในช่วง N วัน
        """
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_active_ad_ids_with_spend")
            return {}
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        ad_spend_map: Dict[str, float] = {}
        page = 1
        
        with cls._get_client() as client:
            url = f"{cls.BASE_URL}/report/integrated/get/"
            
            while True:
                params = {
                    "advertiser_id": advertiser_id,
                    "report_type": "BASIC",
                    "data_level": "AUCTION_AD",
                    "dimensions": json.dumps(["ad_id"]),
                    "metrics": json.dumps(["spend"]),
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "page": page,
                    "page_size": 1000,
                }
                
                try:
                    resp = client.get(
                        url,
                        headers={"Access-Token": token},
                        params=params,
                    )
                    
                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_active_ad_ids error {resp.status_code}")
                        break
                    
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"[TikTokAdsService] fetch_active_ad_ids API error: {data.get('message')}")
                        break
                    
                    reports = data.get("data", {}).get("list", [])
                    if not reports:
                        break
                    
                    for report in reports:
                        dims = report.get("dimensions", {})
                        metrics = report.get("metrics", {})
                        ad_id = dims.get("ad_id")
                        spend = float(metrics.get("spend", 0) or 0)
                        if ad_id and spend > 0:
                            ad_spend_map[ad_id] = spend
                    
                    page_info = data.get("data", {}).get("page_info", {})
                    total_page = page_info.get("total_page", 1)
                    
                    print(f"[TikTokAdsService] advertiser={advertiser_id} "
                          f"page {page}/{total_page}, active_ads_so_far={len(ad_spend_map)}")
                    
                    if page >= total_page:
                        break
                    page += 1
                    
                except Exception as e:
                    print(f"[TikTokAdsService] fetch_active_ad_ids exception: {e}")
                    break
        
        print(f"[TikTokAdsService] Found {len(ad_spend_map)} active ads with spend in last {days} days")
        return ad_spend_map

    @classmethod
    def fetch_ads_by_ids(cls, advertiser_id: str, ad_ids: List[str]) -> List[Dict]:
        """
        ดึง Ad metadata เฉพาะ ad_ids ที่ระบุ
        
        ใช้ filtering โดย ad_ids แทนการดึงทั้งหมด
        """
        if not ad_ids:
            return []
        
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_ads_by_ids")
            return []
        
        all_ads: List[Dict] = []
        
        with cls._get_client() as client:
            # TikTok API allows filtering by ad_ids (max ~100 per request)
            batch_size = 100
            
            for i in range(0, len(ad_ids), batch_size):
                batch = ad_ids[i:i + batch_size]
                page = 1
                
                while True:
                    params = {
                        "advertiser_id": advertiser_id,
                        "fields": json.dumps([
                            "advertiser_id",
                            "campaign_id",
                            "adgroup_id",
                            "ad_id",
                            "tiktok_item_id",
                            "ad_name",
                            "operation_status",
                            "app_name",
                            "adgroup_name",
                            "campaign_name",
                            "ad_text",
                            "display_name",
                            "create_time",
                            "secondary_status",
                            "modify_time",
                        ]),
                        "filtering": json.dumps({"ad_ids": batch}),
                        "page": page,
                        "page_size": 100,
                    }
                    
                    try:
                        resp = client.get(
                            f"{cls.BASE_URL}/ad/get/",
                            headers={"Access-Token": token},
                            params=params,
                        )
                        
                        if resp.status_code != 200:
                            print(f"[TikTokAdsService] fetch_ads_by_ids error {resp.status_code}")
                            break
                        
                        data = resp.json()
                        if not isinstance(data, dict) or "data" not in data:
                            break
                        
                        d = data["data"]
                        ads = d.get("list") or []
                        if not ads:
                            break
                        
                        all_ads.extend(ads)
                        
                        page_info = d.get("page_info") or {}
                        if page >= page_info.get("total_page", 1):
                            break
                        page += 1
                        
                    except Exception as e:
                        print(f"[TikTokAdsService] fetch_ads_by_ids exception: {e}")
                        break
        
        print(f"[TikTokAdsService] Fetched metadata for {len(all_ads)} ads")
        return all_ads

    @classmethod
    def _map_operation_status(cls, status: str) -> AdStatus:
        """แมป operation_status ของ TikTok ให้เป็น AdStatus ภายในระบบ"""
        if not status:
            return AdStatus.ACTIVE
        s = status.lower()
        if s in {"enable", "active"}:
            return AdStatus.ACTIVE
        if s in {"disable", "pause", "suspend", "deleted"}:
            return AdStatus.PAUSED
        if s in {"pending", "under_review"}:
            return AdStatus.PENDING
        if s in {"rejected"}:
            return AdStatus.REJECTED
        return AdStatus.ACTIVE

    @classmethod
    def _map_objective(cls, objective_raw: str):
        """
        แมป TikTok objective_type ให้เป็น CampaignObjective
        
        TikTok objectives:
        - REACH: Brand awareness through reach
        - VIDEO_VIEWS: Video view optimization
        - TRAFFIC: Website/app traffic
        - CONVERSIONS: Website conversions
        - APP_INSTALLS: App installations
        - LEAD_GENERATION: Lead forms
        - PRODUCT_SALES: TikTok Shop sales (GMV)
        - RF: Reach & Frequency campaigns
        """
        from app.models.enums import CampaignObjective
        
        if not objective_raw:
            return None
        
        obj = objective_raw.upper()
        mapping = {
            "REACH": CampaignObjective.REACH,
            "VIDEO_VIEWS": CampaignObjective.VIDEO_VIEWS,
            "TRAFFIC": CampaignObjective.TRAFFIC,
            "CONVERSIONS": CampaignObjective.CONVERSIONS,
            "WEB_CONVERSIONS": CampaignObjective.CONVERSIONS,
            "APP_INSTALL": CampaignObjective.APP_INSTALL,
            "APP_INSTALLS": CampaignObjective.APP_INSTALL,
            "LEAD_GENERATION": CampaignObjective.LEAD_GENERATION,
            "PRODUCT_SALES": CampaignObjective.GMV_MAX,
            "RF": CampaignObjective.REACH_FREQUENCY,
            "REACH_AND_FREQUENCY": CampaignObjective.REACH_FREQUENCY,
            # Brand/Awareness objectives
            "BRAND_CONSIDERATION": CampaignObjective.AWARENESS,
            "AWARENESS": CampaignObjective.AWARENESS,
            "ENGAGEMENT": CampaignObjective.ENGAGEMENT,
        }
        return mapping.get(obj)

    @classmethod
    def _map_optimization_goal(cls, goal_raw: str):
        """
        แมป TikTok optimization_goal ให้เป็น OptimizationGoal
        
        TikTok optimization goals:
        - REACH: Maximize reach
        - SHOW: Maximize impressions
        - VIDEO_VIEW: Maximize video views (2s or 6s views)
        - ENGAGED_VIEW: Maximize engaged views
        - CLICK: Maximize clicks
        - CONVERSION: Maximize conversions
        - VALUE: Maximize conversion value
        - INSTALL: Maximize app installs
        - LEAD: Maximize leads
        """
        from app.models.enums import OptimizationGoal
        
        if not goal_raw:
            return None
        
        goal = goal_raw.upper()
        mapping = {
            "REACH": OptimizationGoal.REACH,
            "SHOW": OptimizationGoal.IMPRESSIONS,
            "IMPRESSION": OptimizationGoal.IMPRESSIONS,
            "VIDEO_VIEW": OptimizationGoal.VIDEO_VIEW,
            "ENGAGED_VIEW": OptimizationGoal.VIDEO_VIEW,
            "CLICK": OptimizationGoal.LINK_CLICK,
            "CONVERSION": OptimizationGoal.CONVERSION,
            "VALUE": OptimizationGoal.VALUE,
            "INSTALL": OptimizationGoal.APP_INSTALL,
            "LEAD": OptimizationGoal.LEAD,
        }
        return mapping.get(goal)

    @classmethod
    def fetch_campaigns(cls, advertiser_id: str) -> List[Dict]:
        """
        ดึง Campaign details รวมถึง objective_type
        """
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_campaigns")
            return []
        
        all_campaigns: List[Dict] = []
        page = 1
        
        with cls._get_client() as client:
            while True:
                params = {
                    "advertiser_id": advertiser_id,
                    "fields": json.dumps([
                        "campaign_id",
                        "campaign_name",
                        "objective_type",
                        "budget_mode",
                        "budget",
                        "operation_status",
                        "secondary_status",
                        "create_time",
                        "modify_time",
                    ]),
                    "page_size": 100,
                    "page": page,
                }
                
                try:
                    resp = client.get(
                        f"{cls.BASE_URL}/campaign/get/",
                        headers={"Access-Token": token},
                        params=params,
                    )
                    
                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_campaigns error {resp.status_code}")
                        break
                    
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"[TikTokAdsService] fetch_campaigns API error: {data.get('message')}")
                        break
                    
                    campaigns = data.get("data", {}).get("list", [])
                    if not campaigns:
                        break
                    
                    all_campaigns.extend(campaigns)
                    
                    page_info = data.get("data", {}).get("page_info", {})
                    if page >= page_info.get("total_page", 1):
                        break
                    page += 1
                    
                except Exception as e:
                    print(f"[TikTokAdsService] fetch_campaigns exception: {e}")
                    break
        
        print(f"[TikTokAdsService] Fetched {len(all_campaigns)} campaigns from {advertiser_id}")
        return all_campaigns

    @classmethod
    def fetch_adgroups(cls, advertiser_id: str) -> List[Dict]:
        """
        ดึง AdGroup details รวมถึง optimization_goal
        """
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_adgroups")
            return []
        
        all_adgroups: List[Dict] = []
        page = 1
        
        with cls._get_client() as client:
            while True:
                params = {
                    "advertiser_id": advertiser_id,
                    "fields": json.dumps([
                        "adgroup_id",
                        "adgroup_name",
                        "campaign_id",
                        "optimization_goal",
                        "billing_event",
                        "bid_type",
                        "bid_price",  # Changed from "bid" to "bid_price"
                        "budget_mode",
                        "budget",
                        "operation_status",
                        "secondary_status",
                        "create_time",
                        "modify_time",
                    ]),
                    "page_size": 100,
                    "page": page,
                }
                
                try:
                    resp = client.get(
                        f"{cls.BASE_URL}/adgroup/get/",
                        headers={"Access-Token": token},
                        params=params,
                    )
                    
                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_adgroups error {resp.status_code}")
                        break
                    
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"[TikTokAdsService] fetch_adgroups API error: {data.get('message')}")
                        break
                    
                    adgroups = data.get("data", {}).get("list", [])
                    if not adgroups:
                        break
                    
                    all_adgroups.extend(adgroups)
                    
                    page_info = data.get("data", {}).get("page_info", {})
                    if page >= page_info.get("total_page", 1):
                        break
                    page += 1
                    
                except Exception as e:
                    print(f"[TikTokAdsService] fetch_adgroups exception: {e}")
                    break
        
        print(f"[TikTokAdsService] Fetched {len(all_adgroups)} adgroups from {advertiser_id}")
        return all_adgroups

    @classmethod
    def update_campaign_objectives(cls, db: Session, ad_account: AdAccount) -> int:
        """
        อัพเดท Campaign objectives จาก TikTok API
        """
        from app.models import Campaign
        from app.models.enums import Platform as PlatformEnum
        
        campaigns_data = cls.fetch_campaigns(ad_account.external_account_id)
        updated = 0
        
        for camp_data in campaigns_data:
            campaign_id = camp_data.get("campaign_id")
            if not campaign_id:
                continue
            
            campaign = db.query(Campaign).filter(
                Campaign.platform == PlatformEnum.TIKTOK,
                Campaign.ad_account_id == ad_account.id,
                Campaign.external_campaign_id == campaign_id,
            ).first()
            
            if campaign:
                objective_raw = camp_data.get("objective_type")
                if objective_raw:
                    campaign.objective_raw = objective_raw
                    campaign.objective = cls._map_objective(objective_raw)
                    updated += 1
        
        db.commit()
        print(f"[TikTokAdsService] Updated {updated} campaign objectives for {ad_account.name}")
        return updated

    @classmethod
    def update_adgroup_optimization_goals(cls, db: Session, ad_account: AdAccount) -> int:
        """
        อัพเดท AdGroup optimization_goals จาก TikTok API
        """
        from app.models import AdGroup, Campaign
        from app.models.enums import Platform as PlatformEnum
        
        adgroups_data = cls.fetch_adgroups(ad_account.external_account_id)
        updated = 0
        
        # Build campaign_id -> internal campaign map
        campaigns = db.query(Campaign).filter(
            Campaign.platform == PlatformEnum.TIKTOK,
            Campaign.ad_account_id == ad_account.id,
        ).all()
        campaign_map = {c.external_campaign_id: c.id for c in campaigns}
        
        for ag_data in adgroups_data:
            adgroup_id = ag_data.get("adgroup_id")
            campaign_id = ag_data.get("campaign_id")
            
            if not adgroup_id:
                continue
            
            internal_campaign_id = campaign_map.get(campaign_id)
            if not internal_campaign_id:
                continue
            
            adgroup = db.query(AdGroup).filter(
                AdGroup.platform == PlatformEnum.TIKTOK,
                AdGroup.campaign_id == internal_campaign_id,
                AdGroup.external_adgroup_id == adgroup_id,
            ).first()
            
            if adgroup:
                opt_goal_raw = ag_data.get("optimization_goal")
                if opt_goal_raw:
                    adgroup.optimization_goal_raw = opt_goal_raw
                    adgroup.optimization_goal = cls._map_optimization_goal(opt_goal_raw)
                    
                # Update budget info too
                budget = ag_data.get("budget")
                if budget:
                    adgroup.daily_budget = float(budget) / 1000000 if budget > 10000 else float(budget)
                    
                updated += 1
        
        db.commit()
        print(f"[TikTokAdsService] Updated {updated} adgroup optimization goals for {ad_account.name}")
        return updated

    @classmethod
    def sync_ads_for_account(
        cls, db: Session, ad_account: AdAccount, days: int = 7
    ) -> Dict:
        """
        Sync Ads ของ AdAccount (TikTok Advertiser) หนึ่งบัญชี
        - ดึงเฉพาะ ads ที่มี spend ใน N วันล่าสุด (ไม่ดึงทั้งหมด)
        - ดึง lifetime cost ของ ads เหล่านั้น
        - upsert Campaign / AdGroup / Ad พร้อม total_spend
        - map Ad กลับไปหา Content (ผ่าน tiktok_item_id)
        - อัปเดต ads_count, ads_total_cost และ ads_details ของ Content
        
        Args:
            days: จำนวนวันที่จะดึง ads ที่มี activity (default=7 วัน)
        """
        advertiser_id = ad_account.external_account_id
        
        # STEP 1: ดึง ad_ids ที่มี spend ใน N วันล่าสุด
        print(f"[TikTokAdsService] Step 1: Finding ads with spend in last {days} days...")
        active_ads_spend = cls.fetch_active_ad_ids_with_spend(advertiser_id, days=days)
        
        if not active_ads_spend:
            print(f"[TikTokAdsService] No active ads found for {advertiser_id}")
            return {
                "ads": 0,
                "mapped_contents": 0,
                "ads_without_item_id": 0,
                "item_ids_total": 0,
                "ensure_stats": {"requested": 0, "created_or_updated": 0, "failed": 0},
                "item_ids_unresolved": 0,
                "total_spend_synced": 0,
            }
        
        active_ad_ids = list(active_ads_spend.keys())
        print(f"[TikTokAdsService] Found {len(active_ad_ids)} ads with recent activity")
        
        # STEP 2: ดึง metadata ของ ads เหล่านั้น
        print(f"[TikTokAdsService] Step 2: Fetching ad metadata...")
        ads_raw = cls.fetch_ads_by_ids(advertiser_id, active_ad_ids)
        if not ads_raw:
            print(f"[TikTokAdsService] Could not fetch ad metadata")
            return {
                "ads": 0,
                "mapped_contents": 0,
                "ads_without_item_id": 0,
                "item_ids_total": 0,
                "ensure_stats": {"requested": 0, "created_or_updated": 0, "failed": 0},
                "item_ids_unresolved": 0,
                "total_spend_synced": 0,
            }
        
        # STEP 3: ดึง lifetime spend ของ ads เหล่านั้น
        print(f"[TikTokAdsService] Step 3: Fetching lifetime spend...")
        lifetime_spend_map = cls.fetch_spend_for_ads(advertiser_id, active_ad_ids)
        total_spend_synced = sum(lifetime_spend_map.values())
        print(f"[TikTokAdsService] Total lifetime spend: {total_spend_synced:.2f}")

        # cache campaign/adgroup ตาม external_id -> instance
        campaign_cache: Dict[str, Campaign] = {}
        adgroup_cache: Dict[str, AdGroup] = {}

        # เตรียม map content_id -> list of ad summaries
        content_ads_map: Dict[int, List[Dict]] = {}

        # เตรียม content cache จาก item_id ก่อน (ล่วงหน้า)
        ads_without_item_id = sum(1 for a in ads_raw if not a.get("tiktok_item_id"))
        item_ids = {
            a.get("tiktok_item_id") for a in ads_raw if a.get("tiktok_item_id")
        }

        contents: List[Content] = []
        if item_ids:
            contents = (
                db.query(Content)
                .filter(
                    Content.platform == PlatformEnum.TIKTOK,
                    Content.platform_post_id.in_(list(item_ids)),
                )
                .all()
            )

        content_by_item: Dict[str, Content] = {
            c.platform_post_id: c for c in contents if c.platform_post_id
        }

        ensure_stats: Dict = {"requested": 0, "created_or_updated": 0, "failed": 0}

        # Fallback: ถ้ามี item_id จาก ads ที่ยังไม่มีใน DB ให้สร้าง/อัปเดตจาก item detail
        missing_item_ids = [i for i in item_ids if i and i not in content_by_item]
        if missing_item_ids:
            print(
                f"[TikTokAdsService] Ensuring contents for "
                f"{len(missing_item_ids)} TikTok item_ids not in DB before mapping ads..."
            )
            ensure_stats = TikTokService.ensure_contents_for_item_ids(
                list(missing_item_ids), db=db
            )
            # โหลด content ใหม่สำหรับ item_ids ที่เพิ่งสร้าง
            new_contents = (
                db.query(Content)
                .filter(
                    Content.platform == PlatformEnum.TIKTOK,
                    Content.platform_post_id.in_(list(missing_item_ids)),
                )
                .all()
            )
            for c in new_contents:
                if c.platform_post_id:
                    content_by_item[c.platform_post_id] = c

        # item_ids ที่สุดท้ายแล้วยัง map content ไม่ได้เลย
        unresolved_item_ids = [i for i in item_ids if i and i not in content_by_item]

        ads_created_or_updated = 0

        for ad_data in ads_raw:
            campaign_id = ad_data.get("campaign_id")
            adgroup_id = ad_data.get("adgroup_id")
            ad_id = ad_data.get("ad_id")
            item_id = ad_data.get("tiktok_item_id")

            if not ad_id or not campaign_id or not adgroup_id:
                continue

            # ---------- Campaign ----------
            if campaign_id in campaign_cache:
                campaign = campaign_cache[campaign_id]
            else:
                campaign = (
                    db.query(Campaign)
                    .filter(
                        Campaign.platform == PlatformEnum.TIKTOK,
                        Campaign.ad_account_id == ad_account.id,
                        Campaign.external_campaign_id == campaign_id,
                    )
                    .first()
                )
                if not campaign:
                    campaign = Campaign(
                        platform=PlatformEnum.TIKTOK,
                        ad_account_id=ad_account.id,
                        external_campaign_id=campaign_id,
                        name=_truncate(
                            ad_data.get("campaign_name") or f"Campaign {campaign_id}"
                        ),
                    )
                    db.add(campaign)
                    # ให้แน่ใจว่า campaign.id ถูกสร้างก่อนนำไปอ้างอิงที่ AdGroup
                    db.flush()
                else:
                    # update name เผื่อมีเปลี่ยน
                    if ad_data.get("campaign_name"):
                        campaign.name = _truncate(ad_data["campaign_name"])
                
                # Update campaign objective if available
                objective_raw = ad_data.get("objective_type")
                if objective_raw and not campaign.objective_raw:
                    campaign.objective_raw = objective_raw
                    campaign.objective = cls._map_objective(objective_raw)
                
                campaign_cache[campaign_id] = campaign

            # ---------- AdGroup ----------
            if adgroup_id in adgroup_cache:
                adgroup = adgroup_cache[adgroup_id]
            else:
                adgroup = (
                    db.query(AdGroup)
                    .filter(
                        AdGroup.platform == PlatformEnum.TIKTOK,
                        AdGroup.campaign_id == campaign.id,
                        AdGroup.external_adgroup_id == adgroup_id,
                    )
                    .first()
                )
                if not adgroup:
                    adgroup = AdGroup(
                        platform=PlatformEnum.TIKTOK,
                        ad_account_id=ad_account.id,
                        campaign_id=campaign.id,
                        external_adgroup_id=adgroup_id,
                        name=_truncate(
                            ad_data.get("adgroup_name")
                            or f"AdGroup {adgroup_id}"
                        ),
                    )
                    db.add(adgroup)
                    # ให้แน่ใจว่า adgroup.id ถูกสร้างก่อนนำไปอ้างอิงที่ Ad
                    db.flush()
                else:
                    if ad_data.get("adgroup_name"):
                        adgroup.name = _truncate(ad_data["adgroup_name"])
                    # Update ad_account_id if not set
                    if not adgroup.ad_account_id:
                        adgroup.ad_account_id = ad_account.id
                
                # Update adgroup optimization_goal if available
                opt_goal_raw = ad_data.get("optimization_goal")
                if opt_goal_raw and not adgroup.optimization_goal_raw:
                    adgroup.optimization_goal_raw = opt_goal_raw
                    adgroup.optimization_goal = cls._map_optimization_goal(opt_goal_raw)
                
                adgroup_cache[adgroup_id] = adgroup

            # ---------- Ad ----------
            ad = (
                db.query(Ad)
                .filter(
                    Ad.platform == PlatformEnum.TIKTOK,
                    Ad.ad_group_id == adgroup.id,
                    Ad.external_ad_id == ad_id,
                )
                .first()
            )

            if not ad:
                ad = Ad(
                    platform=PlatformEnum.TIKTOK,
                    ad_account_id=ad_account.id,
                    ad_group_id=adgroup.id,
                    external_ad_id=ad_id,
                    name=_truncate(ad_data.get("ad_name") or f"Ad {ad_id}"),
                )
                db.add(ad)
            else:
                if ad_data.get("ad_name"):
                    ad.name = _truncate(ad_data["ad_name"])
                # Update ad_account_id if not set
                if not ad.ad_account_id:
                    ad.ad_account_id = ad_account.id

            # map status
            operation_status = ad_data.get("operation_status")
            ad.status = cls._map_operation_status(operation_status)
            
            # Update spend from lifetime spend map
            ad_spend = lifetime_spend_map.get(ad_id, 0)
            ad.total_spend = ad_spend
            ad.last_synced_at = datetime.utcnow()

            # link to content
            if item_id and item_id in content_by_item:
                content = content_by_item[item_id]
                ad.content_id = content.id
                # ensure content.ad_account_id ชี้มาที่ account นี้ (ถ้ายังไม่เคยตั้ง)
                if not content.ad_account_id:
                    content.ad_account_id = ad_account.id

                # เตรียม summary สำหรับ ads_details (พร้อม spend)
                ads_summary = {
                    "ad_id": ad_id,
                    "campaign_id": campaign_id,
                    "adgroup_id": adgroup_id,
                    "advertiser_id": ad_data.get("advertiser_id"),
                    "ad_name": ad.name,
                    "campaign_name": ad_data.get("campaign_name"),
                    "adgroup_name": ad_data.get("adgroup_name"),
                    "operation_status": operation_status,
                    "secondary_status": ad_data.get("secondary_status"),
                    "create_time": ad_data.get("create_time"),
                    "modify_time": ad_data.get("modify_time"),
                    "total_spend": float(ad_spend),  # lifetime spend
                }

                content_ads_map.setdefault(content.id, []).append(ads_summary)

            ads_created_or_updated += 1

        # commit สำหรับ Campaign/AdGroup/Ad ทั้งหมดก่อน
        db.commit()

        # ---------- Aggregate กลับไปที่ Content ----------
        if content_ads_map:
            from app.models import ABXAdgroup
            
            # Get all ABX adgroup IDs for quick lookup
            abx_adgroup_ids = set()
            abx_adgroups = db.query(ABXAdgroup.external_adgroup_id).all()
            for row in abx_adgroups:
                if row[0]:
                    abx_adgroup_ids.add(row[0])
            
            contents_to_update = (
                db.query(Content)
                .filter(Content.id.in_(list(content_ads_map.keys())))
                .all()
            )

            for c in contents_to_update:
                ads_list = content_ads_map.get(c.id, [])
                
                # Classify ads as ACE or ABX
                ace_ads = []
                abx_ads = []
                
                for ad_info in ads_list:
                    adgroup_id = ad_info.get("adgroup_id")
                    # ABX = adgroup_id exists in abx_adgroups table
                    # ACE = everything else (1 adgroup per 1 content)
                    if adgroup_id and adgroup_id in abx_adgroup_ids:
                        ad_info["type"] = "ABX"
                        abx_ads.append(ad_info)
                    else:
                        ad_info["type"] = "ACE"
                        ace_ads.append(ad_info)
                
                # Update counts
                c.ads_count = len(ads_list)
                c.ace_ad_count = len(ace_ads)
                c.abx_ad_count = len(abx_ads)
                
                # Aggregate total spend from all ads of this content
                content_total_spend = sum(
                    ad_info.get("total_spend", 0) for ad_info in ads_list
                )
                c.ads_total_cost = content_total_spend
                
                # Update details (use list copy to ensure SQLAlchemy detects change)
                c.ace_details = list(ace_ads) if ace_ads else None
                c.abx_details = list(abx_ads) if abx_ads else None
                
                # Ensure ads_details is a dict (might be list from old data)
                existing_details = c.ads_details
                if not isinstance(existing_details, dict):
                    existing_details = {}
                else:
                    existing_details = dict(existing_details)  # make a copy
                existing_details["tiktok"] = list(ads_list)
                c.ads_details = existing_details  # reassign to trigger change detection

            db.commit()

        mapped_contents = len(content_ads_map)

        return {
            "ads": ads_created_or_updated,
            "mapped_contents": mapped_contents,
            "ads_without_item_id": ads_without_item_id,
            "item_ids_total": len(item_ids),
            "ensure_stats": ensure_stats,
            "item_ids_unresolved": len(unresolved_item_ids),
            "total_spend_synced": total_spend_synced,
        }

    @classmethod
    def sync_all_tiktok_ads(cls, days: int = 7) -> Dict:
        """
        Helper สำหรับ job: sync Ads ของทุก TikTok AdAccount ในระบบ
        
        Args:
            days: จำนวนวันที่จะดึง ads (default=7 วัน สำหรับ daily sync)
                  - ใช้ 7 สำหรับ daily sync (แนะนำ)
                  - ใช้ 31 สำหรับ monthly sync
                  - ใช้ -1 สำหรับ full sync (ช้ามาก)
        """
        db = SessionLocal()
        total_ads = 0
        total_contents = 0
        total_ads_without_item = 0
        total_item_ids = 0
        total_detail_failed = 0
        total_unresolved = 0
        total_spend = 0.0

        try:
            accounts: List[AdAccount] = (
                db.query(AdAccount)
                .filter(
                    AdAccount.platform == PlatformEnum.TIKTOK,
                    AdAccount.status == AdAccountStatus.ACTIVE,
                )
                .all()
            )

            for acc in accounts:
                print(
                    f"[TikTokAdsService] Syncing ads for advertiser_id="
                    f"{acc.external_account_id} ({acc.name})"
                )
                r = cls.sync_ads_for_account(db, acc, days=days)
                total_ads += r.get("ads", 0)
                total_contents += r.get("mapped_contents", 0)
                total_ads_without_item += r.get("ads_without_item_id", 0)
                total_item_ids += r.get("item_ids_total", 0)
                total_spend += r.get("total_spend_synced", 0)

                ensure = r.get("ensure_stats") or {}
                total_detail_failed += ensure.get("failed", 0)
                total_unresolved += r.get("item_ids_unresolved", 0)
                
                # Update Campaign objectives and AdGroup optimization goals
                cls.update_campaign_objectives(db, acc)
                cls.update_adgroup_optimization_goals(db, acc)

            return {
                "ads": total_ads,
                "mapped_contents": total_contents,
                "ad_accounts": len(accounts),
                "ads_without_item_id": total_ads_without_item,
                "item_ids_total": total_item_ids,
                "item_detail_failed": total_detail_failed,
                "item_ids_unresolved": total_unresolved,
                "total_spend_synced": total_spend,
            }

        finally:
            db.close()

    @classmethod
    def fetch_spend_for_ads(cls, advertiser_id: str, ad_ids: List[str]) -> Dict[str, float]:
        """
        ดึง Lifetime Spend เฉพาะ Ad IDs ที่ระบุ (เร็วกว่า fetch_lifetime_spend มาก)
        
        Args:
            advertiser_id: TikTok advertiser ID
            ad_ids: List of ad IDs to fetch spend for
            
        Returns:
            Dict[ad_id, total_spend] - mapping ของ ad_id และ total spend
        """
        if not ad_ids:
            return {}
            
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_spend_for_ads")
            return {}

        # region agent log
        import json as _json  # type: ignore
        import os as _os  # type: ignore
        import time as _time  # type: ignore
        def _agent_log(hypothesisId: str, location: str, message: str, data: dict):
            try:
                payload = {
                    "sessionId": "debug-session",
                    "runId": "investigate-400",
                    "hypothesisId": hypothesisId,
                    "location": location,
                    "message": message,
                    "data": data,
                    "timestamp": int(_time.time() * 1000),
                }
                _os.makedirs(".cursor", exist_ok=True)
                with open(r".cursor\debug.log", "a", encoding="utf-8") as f:
                    f.write(_json.dumps(payload, ensure_ascii=False) + "\n")
            except Exception:
                pass
        # endregion
        _agent_log(
            "H1",
            "app/services/tiktok_ads_service.py:fetch_spend_for_ads",
            "enter",
            {"advertiser_tail": (advertiser_id or "")[-4:], "ad_ids_len": len(ad_ids)},
        )

        ad_spend_map: Dict[str, float] = {}

        # TikTok report endpoint querystring มี limit; ต้อง batch ad_ids เพื่อไม่ให้ 400 จาก edge/CDN
        batch_size = 100

        with cls._get_client() as client:
            url = f"{cls.BASE_URL}/report/integrated/get/"

            for i in range(0, len(ad_ids), batch_size):
                batch = ad_ids[i:i + batch_size]

                params = {
                    "advertiser_id": advertiser_id,
                    "report_type": "BASIC",
                    "data_level": "AUCTION_AD",
                    "dimensions": json.dumps(["ad_id"]),
                    "metrics": json.dumps(["spend"]),
                    "query_lifetime": True,
                    # ใช้ format เดียวกับ fetch_ads_report ที่ใช้งานได้จริง
                    # report/integrated/get ต้องการ filtering เป็น list ของ filter objects
                    # และ filter_value ต้องเป็น "string" (จาก log: filtering.0.filter_value: Not a valid string)
                    # โดยปกติจะเป็น JSON-string ของ array เช่น '["123","456"]'
                    "filtering": json.dumps([
                        {
                            "field_name": "ad_id",
                            "filter_type": "IN",
                            "filter_value": json.dumps(batch),
                        }
                    ]),
                    "page_size": 1000,
                    "page": 1,
                }

                try:
                    resp = client.get(
                        url,
                        headers={"Access-Token": token},
                        params=params,
                    )
                    _agent_log(
                        "H1",
                        "app/services/tiktok_ads_service.py:fetch_spend_for_ads",
                        "http_response",
                        {
                            "status_code": int(getattr(resp, "status_code", -1)),
                            "text_head": (getattr(resp, "text", "") or "")[:300],
                            "filtering_len": len(str(params.get("filtering") or "")),
                            "batch_len": len(batch),
                        },
                    )

                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_spend_for_ads error {resp.status_code}")
                        # ไม่ return ทันที เพื่อให้ batch อื่นๆ ยังทำงานต่อได้
                        continue

                    data = resp.json()
                    if data.get("code") != 0:
                        # region agent log
                        try:
                            _agent_log(
                                "H1",
                                "app/services/tiktok_ads_service.py:fetch_spend_for_ads",
                                "api_error",
                                {
                                    "code": data.get("code"),
                                    "message": data.get("message"),
                                    "request_id": data.get("request_id"),
                                    "batch_len": len(batch),
                                },
                            )
                        except Exception:
                            pass
                        # endregion
                        print(f"[TikTokAdsService] fetch_spend_for_ads API error: {data.get('message')}")
                        continue

                    reports = data.get("data", {}).get("list", []) or []
                    for report in reports:
                        ad_id = report.get("dimensions", {}).get("ad_id")
                        spend = float(report.get("metrics", {}).get("spend", 0) or 0)
                        if ad_id is not None:
                            ad_spend_map[str(ad_id)] = spend

                except Exception as e:
                    print(f"[TikTokAdsService] fetch_spend_for_ads exception: {e}")
                    continue

        print(f"[TikTokAdsService] Fetched spend for {len(ad_spend_map)}/{len(ad_ids)} ads")
        return ad_spend_map
    
    @classmethod
    def fetch_adgroup_details(cls, advertiser_id: str, adgroup_ids: List[str]) -> Dict[str, Dict]:
        """
        ดึงรายละเอียด AdGroup เฉพาะ adgroup_ids ที่ระบุ (เร็วกว่า fetch_adgroups มาก)
        
        Args:
            advertiser_id: TikTok advertiser ID
            adgroup_ids: List of adgroup IDs to fetch
            
        Returns:
            Dict[adgroup_id, {budget, budget_mode, operation_status, secondary_status}]
        """
        if not adgroup_ids:
            return {}
            
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_adgroup_details")
            return {}
        
        adgroup_map: Dict[str, Dict] = {}
        
        with cls._get_client() as client:
            url = f"{cls.BASE_URL}/adgroup/get/"
            
            # TikTok API uses "filtering" parameter to filter by adgroup_ids
            params = {
                "advertiser_id": advertiser_id,
                "filtering": json.dumps({"adgroup_ids": adgroup_ids}),
                "fields": json.dumps([
                    "adgroup_id", "budget", "budget_mode", 
                    "operation_status", "secondary_status"
                ]),
            }
            
            try:
                resp = client.get(
                    url,
                    headers={"Access-Token": token},
                    params=params,
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokAdsService] fetch_adgroup_details error {resp.status_code}")
                    return {}
                
                data = resp.json()
                if data.get("code") != 0:
                    print(f"[TikTokAdsService] fetch_adgroup_details API error: {data.get('message')}")
                    return {}
                
                adgroups = data.get("data", {}).get("list", [])
                
                for ag in adgroups:
                    ag_id = ag.get("adgroup_id")
                    if ag_id:
                        adgroup_map[ag_id] = {
                            'budget': ag.get('budget', 0),
                            'budget_mode': ag.get('budget_mode'),
                            'operation_status': ag.get('operation_status'),
                            'secondary_status': ag.get('secondary_status'),
                        }
                
                print(f"[TikTokAdsService] Fetched details for {len(adgroup_map)}/{len(adgroup_ids)} adgroups")
                
            except Exception as e:
                print(f"[TikTokAdsService] fetch_adgroup_details exception: {e}")
        
        return adgroup_map

    @classmethod
    def fetch_ad_details_batch(cls, advertiser_id: str, ad_ids: List[str]) -> Dict[str, Dict]:
        """
        ดึงรายละเอียด Ad เฉพาะ ad_ids ที่ระบุ (real-time)
        
        Args:
            advertiser_id: TikTok advertiser ID
            ad_ids: List of ad IDs to fetch
            
        Returns:
            Dict[ad_id, {ad_name, campaign_name, adgroup_name, operation_status, etc.}]
        """
        if not ad_ids:
            return {}
            
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_ad_details_batch")
            return {}
        
        ad_map: Dict[str, Dict] = {}
        
        with cls._get_client() as client:
            url = f"{cls.BASE_URL}/ad/get/"
            
            # TikTok API limits to 100 ad_ids per request
            for i in range(0, len(ad_ids), 100):
                chunk = ad_ids[i:i + 100]
                
                params = {
                    "advertiser_id": advertiser_id,
                    "filtering": json.dumps({"ad_ids": chunk}),
                    "fields": json.dumps([
                        "ad_id", "ad_name", "campaign_id", "campaign_name", 
                        "adgroup_id", "adgroup_name", "operation_status", 
                        "secondary_status", "display_name", "create_time", 
                        "modify_time", "tiktok_item_id"
                    ]),
                }
                
                try:
                    resp = client.get(
                        url,
                        headers={"Access-Token": token},
                        params=params,
                    )
                    
                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_ad_details_batch error {resp.status_code}")
                        continue
                    
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"[TikTokAdsService] fetch_ad_details_batch API error: {data.get('message')}")
                        continue
                    
                    ads = data.get("data", {}).get("list", [])
                    
                    for ad in ads:
                        ad_id = ad.get("ad_id")
                        if ad_id:
                            ad_map[ad_id] = {
                                'ad_name': ad.get('ad_name'),
                                'campaign_id': ad.get('campaign_id'),
                                'campaign_name': ad.get('campaign_name'),
                                'adgroup_id': ad.get('adgroup_id'),
                                'adgroup_name': ad.get('adgroup_name'),
                                'operation_status': ad.get('operation_status'),
                                'secondary_status': ad.get('secondary_status'),
                                'display_name': ad.get('display_name'),
                                'create_time': ad.get('create_time'),
                                'modify_time': ad.get('modify_time'),
                                'tiktok_item_id': ad.get('tiktok_item_id'),
                            }
                    
                except Exception as e:
                    print(f"[TikTokAdsService] fetch_ad_details_batch exception: {e}")
            
            print(f"[TikTokAdsService] Fetched ad details for {len(ad_map)}/{len(ad_ids)} ads")
        
        return ad_map

    @classmethod
    def fetch_lifetime_spend_by_advertiser(cls, advertiser_id: str) -> Dict[str, float]:
        """
        ดึง Lifetime Spend ของทุก Ad จาก TikTok Report API
        (query_lifetime=True ดึง spend ตั้งแต่เริ่มต้น)
        
        NOTE: ใช้ requests แทน httpx เพราะ httpx มีปัญหากับ TikTok API
        
        Returns:
            Dict[ad_id, total_spend] - mapping ของ ad_id และ total spend
        """
        import requests
        
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_lifetime_spend_by_advertiser")
            return {}
        
        ad_spend_map: Dict[str, float] = {}
        url = f"{cls.BASE_URL}/report/integrated/get/"
        headers = {"Access-Token": token}
        page = 1
        
        while True:
            params = {
                "advertiser_id": advertiser_id,
                "report_type": "BASIC",
                "data_level": "AUCTION_AD",
                "dimensions": json.dumps(["ad_id"]),
                "metrics": json.dumps(["spend"]),
                "query_lifetime": True,
                "page_size": 1000,
                "page": page,
            }
            
            try:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                
                if resp.status_code != 200:
                    print(f"[TikTokAdsService] fetch_lifetime_spend_by_advertiser error {resp.status_code}")
                    break
                
                data = resp.json()
                if data.get("code") != 0:
                    print(f"[TikTokAdsService] fetch_lifetime_spend_by_advertiser API error: {data.get('message')}")
                    break
                
                items = data.get("data", {}).get("list", [])
                
                for item in items:
                    dims = item.get("dimensions", {})
                    metrics = item.get("metrics", {})
                    ad_id = dims.get("ad_id")
                    if ad_id:
                        # Always store as string for consistent lookup
                        ad_id_str = str(ad_id)
                        spend = float(metrics.get("spend") or 0)
                        ad_spend_map[ad_id_str] = spend
                
                # Check if there are more pages
                if len(items) < 1000:
                    break
                page += 1
                
            except Exception as e:
                print(f"[TikTokAdsService] fetch_lifetime_spend_by_advertiser exception: {e}")
                break
        
        print(f"[TikTokAdsService] Fetched lifetime spend for {len(ad_spend_map)} ads from advertiser {advertiser_id}")
        
        return ad_spend_map

    @classmethod
    def fetch_lifetime_spend(cls, advertiser_id: str) -> Dict[str, float]:
        """
        ดึง Lifetime Spend ของทุก Ad จาก TikTok Report API
        (ใช้สำหรับ cronjob, สำหรับ Modal ใช้ fetch_spend_for_ads แทน)
        
        Returns:
            Dict[ad_id, total_spend] - mapping ของ ad_id และ total spend
        """
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_lifetime_spend")
            return {}
        
        ad_spend_map: Dict[str, float] = {}
        
        with cls._get_client() as client:
            url = f"{cls.BASE_URL}/report/integrated/get/"
            page = 1
            
            while True:
                params = {
                    "advertiser_id": advertiser_id,
                    "report_type": "BASIC",
                    "data_level": "AUCTION_AD",
                    "dimensions": json.dumps(["ad_id"]),
                    "metrics": json.dumps(["spend"]),
                    "query_lifetime": True,  # Get lifetime data (from account start date)
                    "page_size": 1000,
                    "page": page,
                }
                
                try:
                    resp = client.get(
                        url,
                        headers={"Access-Token": token},
                        params=params,
                    )
                    
                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_lifetime_spend error {resp.status_code}: {resp.text}")
                        break
                    
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"[TikTokAdsService] fetch_lifetime_spend API error: {data.get('message')}")
                        break
                    
                    reports = data.get("data", {}).get("list", [])
                    
                    if not reports:
                        break
                    
                    for report in reports:
                        ad_id = report.get("dimensions", {}).get("ad_id")
                        spend = float(report.get("metrics", {}).get("spend", 0))
                        if ad_id:
                            ad_spend_map[ad_id] = spend
                    
                    # Check if more pages
                    page_info = data.get("data", {}).get("page_info", {})
                    total_pages = page_info.get("total_page", 1)
                    
                    if page >= total_pages:
                        break
                    
                    page += 1
                    
                except Exception as e:
                    print(f"[TikTokAdsService] fetch_lifetime_spend exception: {e}")
                    break
        
        print(f"[TikTokAdsService] Fetched lifetime spend for {len(ad_spend_map)} ads from {advertiser_id}")
        return ad_spend_map

    @classmethod
    def fetch_ads_report(cls, advertiser_id: str, ad_ids: List[str], days: int = 30) -> List[Dict]:
        """
        ดึง Ad Report (spend data) จาก TikTok Business API
        
        ใช้ endpoint `/report/integrated/get/` เพื่อดึงข้อมูล spend ของแต่ละ ad
        """
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_ads_report")
            return []
        
        if not ad_ids:
            return []
        
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)
        
        all_reports: List[Dict] = []
        
        with cls._get_client() as client:
            url = f"{cls.BASE_URL}/report/integrated/get/"
            
            # TikTok API allows max 100 ad_ids per request
            batch_size = 100
            for i in range(0, len(ad_ids), batch_size):
                batch_ad_ids = ad_ids[i:i + batch_size]
                
                params = {
                    "advertiser_id": advertiser_id,
                    "report_type": "BASIC",
                    "dimensions": json.dumps(["ad_id"]),
                    "metrics": json.dumps([
                        "spend", 
                        "impressions", 
                        "clicks", 
                        "reach",
                        "video_views_p100",
                        "video_views_p75",
                        "conversion"
                    ]),
                    "data_level": "AUCTION_AD",
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": end_date.strftime("%Y-%m-%d"),
                    "filtering": json.dumps({
                        "ad_ids": batch_ad_ids
                    }),
                    "page": 1,
                    "page_size": 100,
                }
                
                try:
                    resp = client.get(
                        url,
                        headers={"Access-Token": token},
                        params=params,
                    )
                    
                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_ads_report error {resp.status_code}: {resp.text}")
                        continue
                    
                    data = resp.json()
                    if data.get("code") != 0:
                        print(f"[TikTokAdsService] fetch_ads_report API error: {data.get('message')}")
                        continue
                    
                    reports = data.get("data", {}).get("list", [])
                    all_reports.extend(reports)
                    
                except Exception as e:
                    print(f"[TikTokAdsService] fetch_ads_report exception: {e}")
                    continue
        
        return all_reports

    # ============================================
    # Daily performance snapshot (no ad_id filtering)
    # ============================================
    @classmethod
    def fetch_ad_daily_report(
        cls,
        advertiser_id: str,
        start_date: str,
        end_date: str,
        metrics: List[str] = None,
    ) -> List[Dict]:
        """
        Fetch ad-level daily report for a date range.

        Notes:
        - We intentionally DO NOT filter by ad_id because TikTok report API may not support it (runtime evidence).
        - Use dimensions ["ad_id","stat_time_day"] and page through results.
        """
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_ad_daily_report")
            return []

        # Keep to widely-supported metrics for AUCTION_AD level.
        # (runtime evidence: some accounts reject 'purchase_value')
        if metrics is None:
            metrics = ["spend", "impressions", "clicks", "reach", "conversion"]

        all_rows: List[Dict] = []
        page = 1

        with cls._get_client() as client:
            url = f"{cls.BASE_URL}/report/integrated/get/"
            while True:
                params = {
                    "advertiser_id": advertiser_id,
                    "report_type": "BASIC",
                    "data_level": "AUCTION_AD",
                    "dimensions": json.dumps(["ad_id", "stat_time_day"]),
                    "metrics": json.dumps(metrics),
                    "start_date": start_date,
                    "end_date": end_date,
                    "page_size": 1000,
                    "page": page,
                }
                try:
                    resp = client.get(url, headers={"Access-Token": token}, params=params)
                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_ad_daily_report error {resp.status_code}: {resp.text}")
                        break
                    data = resp.json()
                    if data.get("code") != 0:
                        # Signal failure to caller (do NOT advance cursor)
                        raise RuntimeError(f"{data.get('message')}")
                    rows = data.get("data", {}).get("list", []) or []
                    if not rows:
                        break
                    all_rows.extend(rows)
                    page_info = data.get("data", {}).get("page_info", {}) or {}
                    total_page = page_info.get("total_page", 1) or 1
                    if page >= total_page:
                        break
                    page += 1
                except Exception as e:
                    print(f"[TikTokAdsService] fetch_ad_daily_report exception: {e}")
                    break

        return all_rows

    @classmethod
    def upsert_tiktok_ad_performance_daily(
        cls,
        db: Session,
        ad_account: "AdAccount",
        start_date: str,
        end_date: str,
    ) -> Dict:
        """
        Upsert daily performance rows into `ad_performance_daily`.
        Cursor responsibility is handled by caller (script/task).
        """
        from datetime import datetime as _dt

        from app.models import AdPerformanceDaily
        from app.models.enums import Platform as PlatformEnum

        advertiser_id = ad_account.external_account_id
        rows = cls.fetch_ad_daily_report(advertiser_id, start_date=start_date, end_date=end_date)

        # Convert report rows to upsert records
        records = []
        for r in rows:
            dims = r.get("dimensions", {}) or {}
            mets = r.get("metrics", {}) or {}
            ext_ad_id = dims.get("ad_id")
            day = dims.get("stat_time_day")
            if not ext_ad_id or not day:
                continue
            try:
                # TikTok often returns "YYYY-MM-DD 00:00:00" for stat_time_day
                day_str = str(day).split(" ")[0]
                day_date = _dt.strptime(day_str, "%Y-%m-%d").date()
            except Exception:
                continue

            def _f(key):
                try:
                    return float(mets.get(key) or 0)
                except Exception:
                    return 0.0

            def _i(key):
                try:
                    return int(float(mets.get(key) or 0))
                except Exception:
                    return 0

            records.append(
                {
                    "platform": PlatformEnum.TIKTOK,
                    "ad_account_id": ad_account.id,
                    "external_ad_id": str(ext_ad_id),
                    "date": day_date,
                    "spend": _f("spend"),
                    "impressions": _i("impressions"),
                    "clicks": _i("clicks"),
                    "reach": _i("reach"),
                    "conversions": _i("conversion"),
                    "purchases": _i("purchase"),
                    "purchase_value": _f("purchase_value"),
                    "metrics": dict(mets),
                }
            )

        if not records:
            return {"inserted_or_updated": 0, "rows_fetched": 0}

        # Postgres upsert (batch to avoid max-parameter limits)
        from sqlalchemy.dialects.postgresql import insert

        total_affected = 0
        batch_size = 300
        now = _dt.utcnow()

        for i in range(0, len(records), batch_size):
            chunk = records[i:i + batch_size]
            stmt = insert(AdPerformanceDaily).values(chunk)
            update_cols = {
                "spend": stmt.excluded.spend,
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "reach": stmt.excluded.reach,
                "conversions": stmt.excluded.conversions,
                "purchases": stmt.excluded.purchases,
                "purchase_value": stmt.excluded.purchase_value,
                "metrics": stmt.excluded.metrics,
                "updated_at": now,
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["platform", "ad_account_id", "external_ad_id", "date"],
                set_=update_cols,
            )
            res = db.execute(stmt)
            total_affected += int(getattr(res, "rowcount", 0) or 0)

        db.commit()
        return {"inserted_or_updated": total_affected, "rows_fetched": len(rows)}

    # ============================================
    # AdGroup Update Methods (POST to TikTok API)
    # ============================================
    
    @classmethod
    def update_adgroup_status(
        cls,
        advertiser_id: str,
        adgroup_ids: List[str],
        status: str  # "ENABLE" or "DISABLE"
    ) -> Dict:
        """
        อัปเดท status ของ AdGroup ผ่าน TikTok API
        
        Args:
            advertiser_id: TikTok advertiser ID
            adgroup_ids: List of adgroup IDs to update
            status: "ENABLE" or "DISABLE"
            
        Returns:
            Dict with success status and message
        """
        token = cls._get_access_token()
        if not token:
            return {"success": False, "message": "Missing access token"}
        
        url = f"{cls.BASE_URL}/adgroup/status/update/"
        
        # TikTok API limits to 20 adgroups per request
        chunk_size = 20
        all_results = []
        
        with cls._get_client() as client:
            for i in range(0, len(adgroup_ids), chunk_size):
                chunk = adgroup_ids[i:i + chunk_size]
                
                payload = {
                    "advertiser_id": advertiser_id,
                    "adgroup_ids": chunk,
                    "operation_status": status
                }
                
                try:
                    resp = client.post(
                        url,
                        headers={
                            "Access-Token": token,
                            "Content-Type": "application/json"
                        },
                        json=payload
                    )
                    
                    data = resp.json()
                    
                    if resp.status_code == 200 and data.get("code") == 0:
                        all_results.append({
                            "success": True,
                            "adgroup_ids": chunk,
                            "status": status
                        })
                        print(f"[TikTokAdsService] Updated {len(chunk)} adgroups to {status}")
                    else:
                        all_results.append({
                            "success": False,
                            "adgroup_ids": chunk,
                            "error": data.get("message", "Unknown error")
                        })
                        print(f"[TikTokAdsService] Failed to update adgroups: {data.get('message')}")
                        
                except Exception as e:
                    all_results.append({
                        "success": False,
                        "adgroup_ids": chunk,
                        "error": str(e)
                    })
                    print(f"[TikTokAdsService] Exception updating adgroups: {e}")
        
        # Check if all succeeded
        all_success = all(r.get("success") for r in all_results)
        return {
            "success": all_success,
            "message": f"Updated {len(adgroup_ids)} adgroups to {status}" if all_success else "Some updates failed",
            "results": all_results
        }
    
    @classmethod
    def update_adgroup_budget(
        cls,
        advertiser_id: str,
        adgroup_id: str,
        budget: float
    ) -> Dict:
        """
        อัปเดท budget ของ AdGroup ผ่าน TikTok API
        
        Args:
            advertiser_id: TikTok advertiser ID
            adgroup_id: AdGroup ID to update
            budget: New budget amount (in local currency, e.g., THB)
            
        Returns:
            Dict with success status and message
        """
        token = cls._get_access_token()
        if not token:
            return {"success": False, "message": "Missing access token"}
        
        url = f"{cls.BASE_URL}/adgroup/update/"
        
        payload = {
            "advertiser_id": advertiser_id,
            "adgroup_id": adgroup_id,
            "budget": budget
        }
        
        with cls._get_client() as client:
            try:
                resp = client.post(
                    url,
                    headers={
                        "Access-Token": token,
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                
                data = resp.json()
                
                if resp.status_code == 200 and data.get("code") == 0:
                    print(f"[TikTokAdsService] Updated adgroup {adgroup_id} budget to {budget}")
                    return {
                        "success": True,
                        "message": f"Budget updated to {budget}",
                        "adgroup_id": adgroup_id,
                        "new_budget": budget
                    }
                else:
                    print(f"[TikTokAdsService] Failed to update budget: {data.get('message')}")
                    return {
                        "success": False,
                        "message": data.get("message", "Unknown error"),
                        "adgroup_id": adgroup_id
                    }
                    
            except Exception as e:
                print(f"[TikTokAdsService] Exception updating budget: {e}")
                return {
                    "success": False,
                    "message": str(e),
                    "adgroup_id": adgroup_id
                }
    
    @classmethod
    def update_adgroup_budget_and_status(
        cls,
        advertiser_id: str,
        adgroup_id: str,
        budget: Optional[float] = None,
        status: Optional[str] = None  # "ENABLE" or "DISABLE"
    ) -> Dict:
        """
        อัปเดททั้ง budget และ status ของ AdGroup
        
        Args:
            advertiser_id: TikTok advertiser ID
            adgroup_id: AdGroup ID to update
            budget: New budget amount (optional)
            status: "ENABLE" or "DISABLE" (optional)
            
        Returns:
            Dict with success status and results
        """
        results = {
            "success": True,
            "budget_result": None,
            "status_result": None
        }
        
        # Update status first (if provided)
        if status:
            status_result = cls.update_adgroup_status(advertiser_id, [adgroup_id], status)
            results["status_result"] = status_result
            if not status_result.get("success"):
                results["success"] = False
        
        # Update budget (if provided)
        if budget is not None:
            budget_result = cls.update_adgroup_budget(advertiser_id, adgroup_id, budget)
            results["budget_result"] = budget_result
            if not budget_result.get("success"):
                results["success"] = False
        
        return results

    # ============================================
    # Ad Creation Methods (POST to TikTok API)
    # ============================================
    
    @classmethod
    def create_campaign(
        cls,
        advertiser_id: str,
        campaign_name: str,
        objective_type: str = "VIDEO_VIEWS",
        budget_mode: str = "BUDGET_MODE_DAY",
        daily_budget: Optional[float] = 500.0,
    ) -> Dict:
        """
        สร้าง Campaign ใหม่บน TikTok
        
        Args:
            advertiser_id: TikTok advertiser ID
            campaign_name: ชื่อ campaign
            objective_type: VIDEO_VIEWS, REACH, TRAFFIC, CONVERSIONS etc.
            budget_mode: BUDGET_MODE_INFINITE (unlimited) or BUDGET_MODE_DAY (daily budget)
            
        Returns:
            Dict with success, campaign_id, campaign_name, message
        """
        token = cls._get_access_token()
        if not token:
            return {"success": False, "message": "Missing access token"}
        
        url = f"{cls.BASE_URL}/campaign/create/"
        
        payload = {
            "advertiser_id": advertiser_id,
            "campaign_name": campaign_name,
            "objective_type": objective_type,
            "budget_mode": budget_mode,
        }
        
        if budget_mode == "BUDGET_MODE_DAY" and daily_budget:
            payload["budget"] = daily_budget
        
        with cls._get_client() as client:
            try:
                resp = client.post(
                    url,
                    headers={
                        "Access-Token": token,
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                
                data = resp.json()
                
                if resp.status_code == 200 and data.get("code") == 0:
                    campaign_id = data.get("data", {}).get("campaign_id")
                    print(f"[TikTokAdsService] Created campaign {campaign_id}: {campaign_name}")
                    return {
                        "success": True,
                        "campaign_id": campaign_id,
                        "campaign_name": campaign_name,
                        "message": "Campaign created successfully"
                    }
                else:
                    error_msg = data.get("message", "Unknown error")
                    print(f"[TikTokAdsService] Failed to create campaign: {error_msg}")
                    return {
                        "success": False,
                        "message": error_msg
                    }
                    
            except Exception as e:
                print(f"[TikTokAdsService] Exception creating campaign: {e}")
                return {
                    "success": False,
                    "message": str(e)
                }
    
    @classmethod
    def get_identity_id(cls, advertiser_id: str, tiktok_item_id: str) -> Optional[str]:
        """
        ดึง identity_id จาก TikTok สำหรับ Spark Ads
        
        Spark Ads ต้องการ identity_id เพื่อระบุตัวตนของ content creator
        """
        token = cls._get_access_token()
        if not token:
            return None
        
        url = f"{cls.BASE_URL}/identity/get/"
        
        with cls._get_client() as client:
            try:
                params = {
                    "advertiser_id": advertiser_id,
                    "identity_type": "TT_USER",
                }
                
                resp = client.get(
                    url,
                    headers={"Access-Token": token},
                    params=params,
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokAdsService] get_identity_id error {resp.status_code}")
                    return None
                
                data = resp.json()
                if data.get("code") != 0:
                    print(f"[TikTokAdsService] get_identity_id API error: {data.get('message')}")
                    return None
                
                identities = data.get("data", {}).get("identity_list", [])
                if identities:
                    return identities[0].get("identity_id")
                
                return None
                
            except Exception as e:
                print(f"[TikTokAdsService] get_identity_id exception: {e}")
                return None
    
    @classmethod
    def create_ace_adgroup_and_ad(
        cls,
        advertiser_id: str,
        campaign_id: str,
        tiktok_item_id: str,
        adgroup_name: str,
        ad_name: str,
        targeting: Optional[Dict] = None,
        budget: float = 200.0,
        optimization_goal: str = "VIDEO_VIEW",
        identity_id: Optional[str] = None,
        identity_type: str = "TT_USER",
    ) -> Dict:
        """
        สร้าง ACE AdGroup และ Ad (1 adgroup = 1 content)
        
        Args:
            advertiser_id: TikTok advertiser ID
            campaign_id: Campaign ID ที่จะสร้าง adgroup ใต้
            tiktok_item_id: TikTok item ID (post ID)
            adgroup_name: ชื่อ adgroup
            ad_name: ชื่อ ad
            targeting: Targeting settings (optional)
            budget: Daily budget (default 200 THB)
            optimization_goal: VIDEO_VIEW, REACH, CLICK etc.
            
        Returns:
            Dict with success, adgroup_id, ad_id, message
        """
        token = cls._get_access_token()
        if not token:
            return {"success": False, "message": "Missing access token"}
        
        # Step 1: Create AdGroup
        adgroup_url = f"{cls.BASE_URL}/adgroup/create/"
        
        # Default targeting (Thailand, all genders, 18-55)
        default_targeting = {
            "location_ids": ["1012"],  # Thailand
            "gender": "GENDER_UNLIMITED",
            "age_groups": ["AGE_18_24", "AGE_25_34", "AGE_35_44", "AGE_45_54"],
        }
        
        targeting_settings = targeting or default_targeting
        
        adgroup_payload = {
            "advertiser_id": advertiser_id,
            "campaign_id": campaign_id,
            "adgroup_name": adgroup_name,
            "promotion_type": "SPARK_ADS",
            "placement_type": "PLACEMENT_TYPE_AUTOMATIC",
            "budget_mode": "BUDGET_MODE_DAY",
            "budget": budget,
            "schedule_type": "SCHEDULE_START_END",
            "schedule_start_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "optimization_goal": optimization_goal,
            "bid_type": "BID_TYPE_NO_BID",
            "billing_event": "CPV",
            "pacing": "PACING_MODE_SMOOTH",
            **targeting_settings,
        }
        
        with cls._get_client() as client:
            try:
                # Create AdGroup
                resp = client.post(
                    adgroup_url,
                    headers={
                        "Access-Token": token,
                        "Content-Type": "application/json"
                    },
                    json=adgroup_payload
                )
                
                data = resp.json()
                
                if resp.status_code != 200 or data.get("code") != 0:
                    error_msg = data.get("message", "Failed to create adgroup")
                    print(f"[TikTokAdsService] Failed to create adgroup: {error_msg}")
                    return {"success": False, "message": error_msg}
                
                adgroup_id = data.get("data", {}).get("adgroup_id")
                print(f"[TikTokAdsService] Created adgroup {adgroup_id}: {adgroup_name}")
                
                # Step 2: Create Ad
                ad_result = cls._create_spark_ad(
                    client,
                    token,
                    advertiser_id,
                    adgroup_id,
                    tiktok_item_id,
                    ad_name,
                    identity_id=identity_id,
                    identity_type=identity_type,
                )
                
                if not ad_result.get("success"):
                    return {
                        "success": False,
                        "adgroup_id": adgroup_id,
                        "message": ad_result.get("message", "Failed to create ad")
                    }
                
                return {
                    "success": True,
                    "adgroup_id": adgroup_id,
                    "ad_id": ad_result.get("ad_id"),
                    "message": "ACE AdGroup and Ad created successfully"
                }
                
            except Exception as e:
                print(f"[TikTokAdsService] Exception creating ACE adgroup/ad: {e}")
                return {"success": False, "message": str(e)}
    
    @classmethod
    def create_adgroup(
        cls,
        advertiser_id: str,
        campaign_id: str,
        adgroup_name: str,
        targeting: Optional[Dict] = None,
        budget: float = 500.0,
        optimization_goal: str = "VIDEO_VIEW",
    ) -> Dict:
        """
        สร้าง AdGroup ใหม่บน TikTok (สำหรับ ABX หรือ ACE)
        
        Args:
            advertiser_id: TikTok advertiser ID
            campaign_id: Campaign ID ที่จะสร้าง adgroup ใต้
            adgroup_name: ชื่อ adgroup
            targeting: Targeting settings (optional)
            budget: Daily budget (default 500 THB)
            optimization_goal: VIDEO_VIEW, REACH, CLICK etc.
            
        Returns:
            Dict with success, adgroup_id, message
        """
        token = cls._get_access_token()
        if not token:
            return {"success": False, "message": "Missing access token"}
        
        adgroup_url = f"{cls.BASE_URL}/adgroup/create/"
        
        # Default targeting (Thailand, all genders, 18-55)
        default_targeting = {
            "location_ids": ["1012"],  # Thailand
            "gender": "GENDER_UNLIMITED",
            "age_groups": ["AGE_18_24", "AGE_25_34", "AGE_35_44", "AGE_45_54"],
        }
        
        targeting_settings = targeting or default_targeting
        
        adgroup_payload = {
            "advertiser_id": advertiser_id,
            "campaign_id": campaign_id,
            "adgroup_name": adgroup_name,
            "promotion_type": "SPARK_ADS",
            "placement_type": "PLACEMENT_TYPE_AUTOMATIC",
            "budget_mode": "BUDGET_MODE_DAY",
            "budget": budget,
            "schedule_type": "SCHEDULE_START_END",
            "schedule_start_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "optimization_goal": optimization_goal,
            "bid_type": "BID_TYPE_NO_BID",
            "billing_event": "CPV",
            "pacing": "PACING_MODE_SMOOTH",
            **targeting_settings,
        }
        
        with cls._get_client() as client:
            try:
                resp = client.post(
                    adgroup_url,
                    headers={
                        "Access-Token": token,
                        "Content-Type": "application/json"
                    },
                    json=adgroup_payload
                )
                
                data = resp.json()
                
                if resp.status_code == 200 and data.get("code") == 0:
                    adgroup_id = data.get("data", {}).get("adgroup_id")
                    print(f"[TikTokAdsService] Created adgroup {adgroup_id}: {adgroup_name}")
                    return {
                        "success": True,
                        "adgroup_id": adgroup_id,
                        "message": "AdGroup created successfully"
                    }
                else:
                    error_msg = data.get("message", "Failed to create adgroup")
                    print(f"[TikTokAdsService] Failed to create adgroup: {error_msg}")
                    return {"success": False, "message": error_msg}
                    
            except Exception as e:
                print(f"[TikTokAdsService] Exception creating adgroup: {e}")
                return {"success": False, "message": str(e)}
    
    @classmethod
    def create_abx_ad(
        cls,
        advertiser_id: str,
        adgroup_id: str,
        tiktok_item_id: str,
        ad_name: str,
        identity_id: Optional[str] = None,
        identity_type: str = "TT_USER",
    ) -> Dict:
        """
        สร้าง ABX Ad (เพิ่ม content เข้า adgroup ที่มีอยู่แล้ว)
        
        Args:
            advertiser_id: TikTok advertiser ID
            adgroup_id: AdGroup ID ที่จะเพิ่ม ad เข้าไป
            tiktok_item_id: TikTok item ID (post ID)
            ad_name: ชื่อ ad
            
        Returns:
            Dict with success, ad_id, message
        """
        token = cls._get_access_token()
        if not token:
            return {"success": False, "message": "Missing access token"}
        
        with cls._get_client() as client:
            result = cls._create_spark_ad(
                client,
                token,
                advertiser_id,
                adgroup_id,
                tiktok_item_id,
                ad_name,
                identity_id=identity_id,
                identity_type=identity_type,
            )
            
            return result
    
    # ============================================
    # Spark Ad Posts (for expire date tracking)
    # ============================================
    
    @classmethod
    def fetch_spark_ad_posts(cls, advertiser_id: str) -> List[Dict]:
        """
        ดึงรายการ Spark Ad Posts (authorized content) จาก TikTok
        
        ใช้ endpoint `/tt_video/list/` เพื่อดึงข้อมูล:
        - item_id: TikTok post ID
        - auth_end_time: วันหมดอายุ authorization สำหรับ Spark Ads
        - ad_auth_status: สถานะ authorization
        
        สำหรับ Influencer content ที่ถูก authorize ให้ใช้เป็น Spark Ads
        """
        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_spark_ad_posts")
            return []
        
        all_posts: List[Dict] = []
        page = 1
        
        with cls._get_client() as client:
            while True:
                url = f"{cls.BASE_URL.replace('/open_api/v1.3', '/open_api/v1.3')}/tt_video/list/"
                
                params = {
                    "advertiser_id": advertiser_id,
                    "page_size": 50,
                    "page": page,
                }
                
                try:
                    resp = client.get(
                        url,
                        headers={"Access-Token": token},
                        params=params,
                    )
                    
                    if resp.status_code != 200:
                        print(f"[TikTokAdsService] fetch_spark_ad_posts error {resp.status_code}: {resp.text}")
                        break
                    
                    data = resp.json()
                    
                    if data.get("code") != 0:
                        print(f"[TikTokAdsService] fetch_spark_ad_posts API error: {data.get('message')}")
                        break
                    
                    items = data.get("data", {}).get("list", [])
                    
                    if not items:
                        break
                    
                    for item in items:
                        # Extract relevant fields
                        item_info = item.get("item_info", {})
                        auth_info = item.get("auth_info", {})
                        user_info = item.get("user_info", {})
                        
                        post_data = {
                            "item_id": item_info.get("item_id"),
                            "identity_id": user_info.get("identity_id"),
                            "auth_code": item_info.get("auth_code"),
                            "auth_start_time": auth_info.get("auth_start_time"),
                            "auth_end_time": auth_info.get("auth_end_time"),
                            "ad_auth_status": auth_info.get("ad_auth_status"),
                        }
                        all_posts.append(post_data)
                    
                    # Check if more pages
                    if len(items) < 50:
                        break
                    
                    page += 1
                    
                except Exception as e:
                    print(f"[TikTokAdsService] fetch_spark_ad_posts exception: {e}")
                    break
        
        print(f"[TikTokAdsService] Fetched {len(all_posts)} spark ad posts from {advertiser_id}")
        return all_posts
    
    @classmethod
    def fetch_all_spark_ad_posts(cls) -> Dict[str, Dict]:
        """
        ดึง Spark Ad Posts จากทุก ad account
        
        Returns:
            Dict[item_id, {auth_end_time, ad_auth_status, ...}]
        """
        from app.core.database import SessionLocal
        
        db = SessionLocal()
        all_posts_map: Dict[str, Dict] = {}
        
        try:
            accounts = (
                db.query(AdAccount)
                .filter(
                    AdAccount.platform == PlatformEnum.TIKTOK,
                    AdAccount.status == AdAccountStatus.ACTIVE,
                )
                .all()
            )
            
            for account in accounts:
                print(f"[TikTokAdsService] Fetching spark ad posts from {account.name}...")
                posts = cls.fetch_spark_ad_posts(account.external_account_id)
                
                for post in posts:
                    item_id = post.get("item_id")
                    if item_id:
                        # Store/update with latest auth_end_time
                        all_posts_map[item_id] = post
            
            print(f"[TikTokAdsService] Total spark ad posts: {len(all_posts_map)}")
            
        finally:
            db.close()
        
        return all_posts_map

    @classmethod
    def _create_spark_ad(
        cls,
        client: httpx.Client,
        token: str,
        advertiser_id: str,
        adgroup_id: str,
        tiktok_item_id: str,
        ad_name: str,
        identity_id: Optional[str] = None,
        identity_type: str = "TT_USER",
    ) -> Dict:
        """
        Internal: สร้าง Spark Ad จาก TikTok item_id
        
        Spark Ads = โฆษณาจาก organic content ที่มีอยู่แล้ว
        """
        ad_url = f"{cls.BASE_URL}/ad/create/"
        
        if not identity_id:
            return {"success": False, "message": "Identity ID not found for this content/advertiser"}
        
        ad_payload = {
            "advertiser_id": advertiser_id,
            "adgroup_id": adgroup_id,
            "creatives": [
                {
                    "ad_name": ad_name,
                    "ad_format": "SINGLE_VIDEO",
                    "tiktok_item_id": tiktok_item_id,
                    "identity_type": identity_type,
                    "identity_id": identity_id,
                }
            ],
        }
        
        try:
            resp = client.post(
                ad_url,
                headers={
                    "Access-Token": token,
                    "Content-Type": "application/json"
                },
                json=ad_payload
            )
            
            data = resp.json()
            
            if resp.status_code == 200 and data.get("code") == 0:
                ad_ids = data.get("data", {}).get("ad_ids", [])
                ad_id = ad_ids[0] if ad_ids else None
                print(f"[TikTokAdsService] Created ad {ad_id}: {ad_name}")
                return {
                    "success": True,
                    "ad_id": ad_id,
                    "message": "Ad created successfully"
                }
            else:
                error_msg = data.get("message", "Failed to create ad")
                
                # Check for identity error (common issue with Spark Ads)
                if "identity" in error_msg.lower():
                    error_msg = f"Identity ID not found. Please bind the TikTok account first. Original error: {error_msg}"
                
                print(f"[TikTokAdsService] Failed to create ad: {error_msg}")
                return {"success": False, "message": error_msg}
                
        except Exception as e:
            print(f"[TikTokAdsService] Exception creating ad: {e}")
            return {"success": False, "message": str(e)}

