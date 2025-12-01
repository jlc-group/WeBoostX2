# WeBoostX 2.0 – Full System Requirements (Multi-Platform Version)

## 1. SYSTEM PURPOSE

WeBoostX 2.0 คือระบบบริหารจัดการ “Content + Multi-Platform Ad Optimization” สำหรับ:

- TikTok
- Facebook / Instagram (Meta Ads)
- (รองรับการเพิ่มแพลตฟอร์มในอนาคต เช่น YouTube, LINE Ads)

ระบบนี้เน้น:

1. Content Management (ทุกแพลตฟอร์ม)
2. Ad Automation (ACE/ABX สำหรับ TikTok และ Adset Automation สำหรับ Facebook)
3. Performance Scoring แบบรวมทุกแพลตฟอร์ม
4. Unified Budget Optimization
5. Sales / Scan / Offline เป็นสัญญาณประกอบ

---

## 2. CORE MODULES

### 2.1 CONTENT MANAGEMENT MODULE (Multi-Platform)

- Sync content จากหลายแพลตฟอร์ม:
  - TikTok Posts
  - Facebook Page Videos/Reels
  - Instagram Reels (ผ่าน Graph API)
- เก็บข้อมูล content descriptor:

  - platform (TIKTOK / FACEBOOK / IG)
  - platform_post_id
  - products (SKU / ProductGroup)
  - content_type (SALE / REVIEW / BRANDING / ECOM)
  - source (INFLUENCER / PAGE / STAFF / UGC)
  - owner (influencer_id / employee / team)
  - status (READY / TEST_AD / ACTIVE_AD / EXPIRED)
  - boost flags

- เก็บ performance ต่อแพลตฟอร์ม:

  - TikTok: views, watch_time, engagement, ctr, cvr (from ads)
  - Facebook: reach, impressions, plays, 3s/ThruPlay, CPC, CTR, ROAS (from ads)

- Content detail page ต้องแสดงรวมทุกแพลตฟอร์ม:
  - organic metrics
  - ad metrics
  - cost united from ads

---

### 2.2 AD MANAGEMENT & OPTIMIZATION MODULE (Multi-Platform)

#### TikTok

- Campaign/adgroup/ad sync
- ACE/ABX automation
- Budget optimization per adgroup
- Content → Ad creation flow

#### Facebook/Instagram (Meta Ads)

- Campaign/Adset/Ad sync:
  - via Graph API v19+
- Bind Ad → Content
  - ad.creative.object_story_id ↔ page_post_id ↔ content model
- Adset parameters:
  - targeting
  - budget
  - optimization goal
  - schedule
- Management Actions:
  - create ads from content
  - pause / activate ad or adset
  - update daily budget
  - retrieve ROAS/CTR/CVR/cost per result

#### Ad Optimization (Unified)

Rule-Based (MVP):

- CTR ต่ำทุก platform → ลดงบ/ปิด
- ROAS ต่ำ → ลดงบ/ปิด
- High content score → เพิ่มงบ
- Frequency สูงเกิน → ลดงบ FB/IG

Score-Based:

- ใช้ "Unified Content Impact Score" เพื่อจัดลำดับสิทธิ์การใช้งบในทุก platform

---

## 3. DATA PIPELINES

### 3.1 Content Sync (Multi-Platform)

Schedule: ทุก 30–60 นาที

TikTok:

- ใช้ open_api/v1.3/ กับ endpoints ของ posts

Facebook/Instagram:

- GET /{page_id}/posts?fields=insights,permalink_url,attachments
- GET /{ig_business_id}/media

Fields:

- platform_post_id
- create_time
- views/plays
- watch time (ถ้ามี)
- engagement (reactions/comments/shares)
- product assignment mapping

---

### 3.2 Ad Sync Pipeline (Multi-Platform)

Schedule: ทุก 15–30 นาที

TikTok:

- /campaign/get
- /adgroup/get
- /ad/get
- /report/integrated/get

Facebook/Instagram:

- GET /act\_{ad_account_id}/campaigns
- GET /act\_{ad_account_id}/adsets
- GET /act\_{ad_account_id}/ads
- GET /{ad_id}/insights?fields=reach,impressions,clicks,ctr,cpc,spend,actions

Goal:

- Update ad performance
- Update ad cost to content
- Update platform metrics to unified score engine
- Feed budget optimizer

---

### 3.3 Sales Pipelines (Support Only)

- online sales sync (tiktok shop / shopee / lazada)
- saversure daily scan
- offline weekly 7-11

ไม่ผูกรายคลิปใน MVP  
ใช้เป็น **SKU-level signals** เพื่อช่วย budget optimizer

---

## 4. SCORING SYSTEM

### 4.1 PFM Score (TikTok only)

- ใช้สูตรของ TikTok-optimized PFM เดิม
- คำนวณตาม CTR / CVR / ViewTime / ROAS / Spend efficiency

### 4.2 Facebook Adset/Ad Performance Score

สูตรแบบ parallel:

- FB_score = weighted(CTR, CPC, Cost per result, ROAS, Frequency, ThruPlay rate)

### 4.3 Unified Content Impact Score (All Platforms)

Weight (MVP):

- TikTok online performance = ~50%
- Facebook/IG online performance = ~30%
- Saversure/Offline demand = ~20% (SKU-level signal only)

Output:

- final_score 0–100
- ใช้สำหรับ ranking content
- ใช้ตัดสินใจเพิ่มงบ/หยุดคอนเทนต์
- ใช้สำหรับ ACE/ABX และ FB ad automation

---

## 5. MULTI-PLATFORM AD OPTIMIZATION ENGINE

Inputs:

- PFM (TikTok content)
- FB_score (Facebook ad)
- Unified Content Impact Score
- ProductGroup target budget
- Platform efficiency (ROAS by platform)
- Spending velocity (burn rate)
- DailyBudget plan

Actions:

- เพิ่มงบ adgroup/adset ใน platform ที่มีประสิทธิภาพดีกว่า
- ลด/หยุด ads ที่อ่อนทั้งฝ่าย TikTok/Facebook
- เลือก “winning content” ข้ามแพลตฟอร์ม
- ดัน content เดียวให้เกิดผลบนทั้ง FB + TikTok ตาม performance
- แจ้งเตือนเมื่อต้องการ content เพิ่มสำหรับ SKU/PG

Scheduling:

- Optimization run ทุก 2–3 ชั่วโมง
- Preview mode ก่อน apply

---

## 6. DATABASE STRUCTURE (UPDATE FOR MULTI-PLATFORM)

### NEW fields in `TiktokPost` → rename to `Content`

- content_id (UUID)
- platform (TIKTOK / FACEBOOK / INSTAGRAM)
- platform_post_id
- platform_metrics JSON:
  - (tiktok: views, watch_time, engagement)
  - (facebook: reach, impressions, thruplay, CTR)
  - (instagram: plays, reach)
- ads_cost_total (รวมทุก platform)
- ads_details JSON (multiplatform)
- content_source
- content_owner
- influencer_cost
- product_sku_list
- content_type
- status

### NEW models:

- facebook_ads
- facebook_adsets
- facebook_campaigns

- tiktok_ads (from v1)
- abx_adgroup (TikTok only)

- saversure_scan_daily
- offline_sale_weekly
- content_impact_score

---

## 7. CRON JOBS / SCHEDULERS

### Every 15–30 mins

- TikTok: campaign/adgroup/ad/report sync
- Facebook: campaign/adset/ad/insights sync
- Update PFM + FB score
- Update Content Impact Score
- Run Auto Budget Optimization

### Every 60 mins

- Content sync (TikTok + FB + IG)

### Daily

- Saversure Scan sync
- Recalculate Unified Content Ranking

### Weekly

- Offline sale-out sync (7-11)
- SKU-level adjustment

---

## 8. MVP SCOPE

### MUST-HAVE

- Multi-platform content sync (TikTok + FB + IG)
- Multi-platform ads sync (TikTok + FB)
- Ad control (pause/activate/change budget)
- Create ads from content (TikTok ACE + FB Ad)
- PFM + FB performance scoring
- Unified Content Impact Score
- Rule-based budget optimizer (TikTok/FB)
- Basic SKU-level signals (online sales + scan)

### PHASE 2

- Cross-platform AI budget optimizer
- AI content recommendation
- Multi-touch attribution (heuristic)
- Auto-campaign creation flow
- Creator performance prediction model

---

## END OF MULTI-PLATFORM REQUIREMENTS
