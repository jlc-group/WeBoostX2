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
from typing import Dict, List, Tuple, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import (
    AdAccount,
    Campaign,
    AdGroup,
    Ad,
    Content,
    Platform,
)
from app.models.enums import AdAccountStatus, AdStatus, Platform as PlatformEnum
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
        """

        token = cls._get_access_token()
        if not token:
            print("[TikTokAdsService] Missing access token, skip fetch_ads_last_days")
            return []

        use_date_filter = days is not None and days > 0

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days if use_date_filter else 0)

        start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")

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
                            # Campaign/AdGroup objective & optimization
                            "objective_type",
                            "optimization_goal",
                            "create_time",
                            "secondary_status",
                            "modify_time",
                        ]
                    ),
                    "page": page,
                    "page_size": 100,
                }

                if use_date_filter:
                    filtering = {
                        "creation_filter_start_time": start_str,
                        "creation_filter_end_time": end_str,
                    }
                    params["filtering"] = json.dumps(filtering)

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
                    break

                d = data["data"]
                ads = d.get("list") or []
                if not ads:
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
        cls, db: Session, ad_account: AdAccount, days: int = 31
    ) -> Dict:
        """
        Sync Ads ของ AdAccount (TikTok Advertiser) หนึ่งบัญชี
        - upsert Campaign / AdGroup / Ad
        - map Ad กลับไปหา Content (ผ่าน tiktok_item_id)
        - อัปเดต ads_count และ ads_details ของ Content
        """

        ads_raw = cls.fetch_ads_last_days(ad_account.external_account_id, days=days)
        if not ads_raw:
            return {
                "ads": 0,
                "mapped_contents": 0,
                "ads_without_item_id": 0,
                "item_ids_total": 0,
                "ensure_stats": {"requested": 0, "created_or_updated": 0, "failed": 0},
                "item_ids_unresolved": 0,
            }

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
                    ad_group_id=adgroup.id,
                    external_ad_id=ad_id,
                    name=_truncate(ad_data.get("ad_name") or f"Ad {ad_id}"),
                )
                db.add(ad)
            else:
                if ad_data.get("ad_name"):
                    ad.name = _truncate(ad_data["ad_name"])

            # map status
            operation_status = ad_data.get("operation_status")
            ad.status = cls._map_operation_status(operation_status)

            # link to content
            if item_id and item_id in content_by_item:
                content = content_by_item[item_id]
                ad.content_id = content.id
                # ensure content.ad_account_id ชี้มาที่ account นี้ (ถ้ายังไม่เคยตั้ง)
                if not content.ad_account_id:
                    content.ad_account_id = ad_account.id

                # เตรียม summary สำหรับ ads_details
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
                
                # Update details
                c.ace_details = ace_ads if ace_ads else None
                c.abx_details = abx_ads if abx_ads else None
                
                details = c.ads_details or {}
                details["tiktok"] = ads_list
                c.ads_details = details

            db.commit()

        mapped_contents = len(content_ads_map)

        return {
            "ads": ads_created_or_updated,
            "mapped_contents": mapped_contents,
            "ads_without_item_id": ads_without_item_id,
            "item_ids_total": len(item_ids),
            "ensure_stats": ensure_stats,
            "item_ids_unresolved": len(unresolved_item_ids),
        }

    @classmethod
    def sync_all_tiktok_ads(cls, days: int = 31) -> Dict:
        """
        Helper สำหรับ job: sync Ads ของทุก TikTok AdAccount ในระบบ
        """
        db = SessionLocal()
        total_ads = 0
        total_contents = 0
        total_ads_without_item = 0
        total_item_ids = 0
        total_detail_failed = 0
        total_unresolved = 0

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
        
        ad_spend_map: Dict[str, float] = {}
        
        with cls._get_client() as client:
            url = f"{cls.BASE_URL}/report/integrated/get/"
            
            # TikTok API filtering format: list of filter objects
            # See: https://business-api.tiktok.com/portal/docs?id=1751443956638722
            params = {
                "advertiser_id": advertiser_id,
                "report_type": "BASIC",
                "data_level": "AUCTION_AD",
                "dimensions": json.dumps(["ad_id"]),
                "metrics": json.dumps(["spend"]),
                "query_lifetime": True,
                "filtering": json.dumps([
                    {
                        "field_name": "ad_id",
                        "filter_type": "IN",
                        "filter_value": json.dumps(ad_ids)  # Must be JSON string of array
                    }
                ]),
                "page_size": 100,
                "page": 1,
            }
            
            try:
                resp = client.get(
                    url,
                    headers={"Access-Token": token},
                    params=params,
                )
                
                if resp.status_code != 200:
                    print(f"[TikTokAdsService] fetch_spend_for_ads error {resp.status_code}")
                    return {}
                
                data = resp.json()
                if data.get("code") != 0:
                    print(f"[TikTokAdsService] fetch_spend_for_ads API error: {data.get('message')}")
                    return {}
                
                reports = data.get("data", {}).get("list", [])
                
                for report in reports:
                    ad_id = report.get("dimensions", {}).get("ad_id")
                    spend = float(report.get("metrics", {}).get("spend", 0))
                    if ad_id:
                        ad_spend_map[ad_id] = spend
                
                print(f"[TikTokAdsService] Fetched spend for {len(ad_spend_map)}/{len(ad_ids)} ads")
                
            except Exception as e:
                print(f"[TikTokAdsService] fetch_spend_for_ads exception: {e}")
        
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

