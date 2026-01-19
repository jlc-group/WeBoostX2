# Token Usage Guide - WeBoostX 2.0

คู่มือการใช้งาน Access Tokens สำหรับ TikTok และ Facebook APIs

---

## TikTok

### Service Class
```python
from app.services.tiktok_service import TikTokService
```

### วิธีใช้งาน

**วิธีที่ 1: ใช้ Class Method (แนะนำ)**
```python
access_token = TikTokService.get_access_token()
business_id = TikTokService.get_business_id()

# ใช้กับ API calls
response = TikTokService.get_videos_list(access_token, business_id)
```

**วิธีที่ 2: สร้าง Instance (auto-load tokens)**
```python
service = TikTokService()
token = service.access_token
biz_id = service.business_id
```

### ลำดับความสำคัญในการหา Token

| ลำดับ | แหล่งข้อมูล | คำอธิบาย |
|-------|-------------|----------|
| 1 | Database | `app_settings.key = 'tiktok_access_token'` |
| 2 | Database + Refresh | ถ้ามี `client_id` + `client_secret` + `refresh_token` → ใช้ OAuth2 refresh flow |
| 3 | Environment | `TIKTOK_ACCESS_TOKEN` หรือ `TIKTOK_MAIN_ACCESS_TOKEN` หรือ `TIKTOK_AD_TOKEN` |

### Environment Variables

| Variable | Required | คำอธิบาย |
|----------|----------|----------|
| `TIKTOK_ACCESS_TOKEN` | Yes* | Access Token หลัก |
| `TIKTOK_BUSINESS_ID` | Yes | Business ID สำหรับ API calls |
| `TIKTOK_CLIENT_ID` | No | สำหรับ OAuth2 refresh flow |
| `TIKTOK_CLIENT_SECRET` | No | สำหรับ OAuth2 refresh flow |

> *Required ถ้าไม่มี token ใน Database

### ตัวอย่าง .env
```env
TIKTOK_ACCESS_TOKEN=your_access_token_here
TIKTOK_BUSINESS_ID=your_business_id_here
```

---

## Facebook

### Service Class
```python
from app.services.facebook.fb_api import FacebookAPI
```

### วิธีใช้งาน

**สร้าง Instance (auto-load จาก settings/.env)**
```python
api = FacebookAPI()
token = api.page_access_token

# ใช้กับ API calls
posts = await api.fetch_posts(page_id="123456789")
```

**ระบุ Token โดยตรง**
```python
api = FacebookAPI(
    page_access_token="your_page_token",
    user_access_token="your_user_token",
    page_id="123456789"
)
```

**ดึง Page IDs จาก Config**
```python
page_ids = FacebookAPI.get_page_ids()       # List[str]
ad_account_ids = FacebookAPI.get_ad_account_ids()  # List[str]
```

### ลำดับความสำคัญในการหา Token

| ลำดับ | แหล่งข้อมูล | คำอธิบาย |
|-------|-------------|----------|
| 1 | Parameter | Token ที่ส่งเข้ามาใน constructor |
| 2 | Settings | `settings.fb_page_access_token` (ตัวแรกจาก `FB_PAGE_ACCESS_TOKENS`) |
| 3 | Settings | `settings.FACEBOOK_ACCESS_TOKEN` (fallback) |

### Environment Variables

| Variable | Required | คำอธิบาย |
|----------|----------|----------|
| `FB_PAGE_ACCESS_TOKENS` | Yes | Page Access Tokens (comma-separated ถ้ามีหลาย tokens) |
| `FB_USER_ACCESS_TOKEN` | No | User Access Token สำหรับบาง operations |
| `FB_PAGE_IDS` | Yes | Facebook Page IDs (comma-separated) |
| `FB_AD_ACCOUNT_IDS` | No | Ad Account IDs สำหรับ Ads API |

### ตัวอย่าง .env
```env
# Single page
FB_PAGE_ACCESS_TOKENS=EAAxxxxxxxx
FB_PAGE_IDS=123456789

# Multiple pages (comma-separated)
FB_PAGE_ACCESS_TOKENS=EAAtoken1,EAAtoken2,EAAtoken3
FB_PAGE_IDS=page_id_1,page_id_2,page_id_3
FB_AD_ACCOUNT_IDS=act_111111,act_222222
```

---

## Settings Configuration

ทั้ง TikTok และ Facebook tokens ถูกจัดการผ่าน `app/core/config.py`:

```python
from app.core.config import settings

# TikTok
settings.tiktok_content_access_token  # TIKTOK_ACCESS_TOKEN
settings.TIKTOK_BUSINESS_ID           # Business ID

# Facebook
settings.fb_page_access_token         # ตัวแรกจาก FB_PAGE_ACCESS_TOKENS
settings.fb_page_ids                  # List[str] จาก FB_PAGE_IDS
settings.fb_ad_account_ids            # List[str] จาก FB_AD_ACCOUNT_IDS
settings.FB_USER_ACCESS_TOKEN         # User token
```

---

## Quick Reference

| Platform | Get Token | Get IDs |
|----------|-----------|---------|
| TikTok | `TikTokService.get_access_token()` | `TikTokService.get_business_id()` |
| Facebook | `FacebookAPI().page_access_token` | `FacebookAPI.get_page_ids()` |

---

## Troubleshooting

### TikTok: Token ไม่ทำงาน
1. ตรวจสอบว่ามี `TIKTOK_ACCESS_TOKEN` ใน `.env`
2. ตรวจสอบว่า token ยังไม่หมดอายุ
3. ลอง refresh token ถ้ามี `client_id` และ `client_secret`

### Facebook: 403 Forbidden
1. ตรวจสอบว่ามี `FB_PAGE_ACCESS_TOKENS` ใน `.env`
2. ตรวจสอบว่า token มี permissions ที่ต้องการ
3. ตรวจสอบว่า Page ID ตรงกับ token

### Debug: ดู Token ปัจจุบัน
```python
# TikTok
from app.services.tiktok_service import TikTokService
print(f"TikTok Token: {TikTokService.get_access_token()[:20]}...")

# Facebook
from app.services.facebook.fb_api import FacebookAPI
api = FacebookAPI()
print(f"FB Token: {api.page_access_token[:20]}...")
```

---

*Last updated: January 2026*
