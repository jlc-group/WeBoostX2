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
from typing import Dict, List, Tuple

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


class TikTokAdsService:
    """บริการดึงและ sync ข้อมูล TikTok Ads"""

    BASE_URL = settings.TIKTOK_API_BASE_URL

    @classmethod
    def _get_access_token(cls) -> str:
        """
        ใช้ access token ตัวเดียวกับฝั่ง content (ผ่าน TikTokService)
        ถ้าอยากแยก token ฝั่ง ads โดยเฉพาะในอนาคต สามารถขยาย logic ตรงนี้ได้
        """
        token = TikTokService.get_access_token()
        if not token:
            # fallback ไปใช้ env ตรง ๆ ถ้ามี
            token = settings.TIKTOK_AD_TOKEN or settings.tiktok_content_access_token
        return token

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

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        start_str = start_date.strftime("%Y-%m-%d %H:%M:%S")
        end_str = end_date.strftime("%Y-%m-%d %H:%M:%S")

        all_ads: List[Dict] = []
        page = 1

        with cls._get_client() as client:
            while True:
                filtering = {
                    "creation_filter_start_time": start_str,
                    "creation_filter_end_time": end_str,
                }

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
                    "filtering": json.dumps(filtering),
                    "page": page,
                    "page_size": 100,
                }

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
            return {"ads": 0, "mapped_contents": 0}

        # cache campaign/adgroup ตาม external_id -> instance
        campaign_cache: Dict[str, Campaign] = {}
        adgroup_cache: Dict[str, AdGroup] = {}

        # เตรียม map content_id -> list of ad summaries
        content_ads_map: Dict[int, List[Dict]] = {}

        # เตรียม content cache จาก item_id ก่อน (ล่วงหน้า)
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

        # Fallback: ถ้ามี item_id จาก ads ที่ยังไม่มีใน DB ให้สร้าง/อัปเดตจาก item detail
        missing_item_ids = [i for i in item_ids if i and i not in content_by_item]
        if missing_item_ids:
            print(
                f"[TikTokAdsService] Ensuring contents for "
                f"{len(missing_item_ids)} TikTok item_ids not in DB before mapping ads..."
            )
            TikTokService.ensure_contents_for_item_ids(list(missing_item_ids), db=db)
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
                        name=ad_data.get("campaign_name") or f"Campaign {campaign_id}",
                    )
                    db.add(campaign)
                else:
                    # update name เผื่อมีเปลี่ยน
                    if ad_data.get("campaign_name"):
                        campaign.name = ad_data["campaign_name"]
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
                        name=ad_data.get("adgroup_name") or f"AdGroup {adgroup_id}",
                    )
                    db.add(adgroup)
                else:
                    if ad_data.get("adgroup_name"):
                        adgroup.name = ad_data["adgroup_name"]
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
                    name=ad_data.get("ad_name") or f"Ad {ad_id}",
                )
                db.add(ad)
            else:
                if ad_data.get("ad_name"):
                    ad.name = ad_data["ad_name"]

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
            contents_to_update = (
                db.query(Content)
                .filter(Content.id.in_(list(content_ads_map.keys())))
                .all()
            )

            for c in contents_to_update:
                ads_list = content_ads_map.get(c.id, [])
                c.ads_count = len(ads_list)

                details = c.ads_details or {}
                details["tiktok"] = ads_list
                c.ads_details = details

            db.commit()

        mapped_contents = len(content_ads_map)

        return {
            "ads": ads_created_or_updated,
            "mapped_contents": mapped_contents,
        }

    @classmethod
    def sync_all_tiktok_ads(cls, days: int = 31) -> Dict:
        """
        Helper สำหรับ job: sync Ads ของทุก TikTok AdAccount ในระบบ
        """
        db = SessionLocal()
        total_ads = 0
        total_contents = 0

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

            return {
                "ads": total_ads,
                "mapped_contents": total_contents,
                "ad_accounts": len(accounts),
            }

        finally:
            db.close()


