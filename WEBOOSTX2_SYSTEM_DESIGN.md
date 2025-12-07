## WeBoostX 2.0 – System Design (Multi‑Platform, Multi‑Objective)

> **Version:** 2.0 (Draft)\
> **Scope:** ออกแบบให้รองรับหลายแพลตฟอร์ม หลาย Objective และหลายรูปแบบ Ad Structure (1 adgroup/1 content, 1 adgroup/หลาย content)\
> **Focus:** TikTok เป็นหลักในเฟสแรก แต่โครงสร้างพร้อมต่อยอดไป Facebook/Instagram

---

## 1. System Purpose & Concept

WeBoostX 2.0 คือระบบ **Ad & Content Orchestration** ที่ทำหน้าที่เป็น “ชั้นกลาง” ระหว่าง Business Goal กับ Ads Manager ของแต่ละแพลตฟอร์ม

- **Cross‑Platform:** TikTok, Facebook, Instagram (ต่อยอดแพลตฟอร์มอื่นได้)
- **Multi‑Objective:** รองรับทุก Advertising Objective ที่สำคัญ เช่น Reach, Video Views, Community Interaction, Conversion, Sales/GMV, App Promotion ฯลฯ
- **Multi‑Structure:** รองรับทั้ง
  - 1 Adgroup / 1 Content (ACE‑style, Single Content)
  - 1 Adgroup / หลาย Content (ABX‑style, Multi Content)
  - Adgroup ที่สร้างเอง (Manual / General) แต่ดึงข้อมูลมา Optimize ร่วมกันได้
- **Content‑Centric:** ทุกอย่างโยงกลับมาที่ `Content` เป็นตัวกลางในการรวม performance ข้ามแพลตฟอร์ม

---

## 2. Core Data Model (High Level)

### 2.1 Content (Unified Across Platforms)

ตาราง `contents` (model `Content`) เป็นตัวแทนของคลิป/โพสต์จากทุกแพลตฟอร์ม:

- Identity & Platform
  - `platform`: `tiktok` / `facebook` / `instagram`
  - `platform_post_id`: item_id / post_id / media_id
  - `ad_account_id`: FK ไปหา `AdAccount` (บัญชีโฆษณาหลักของ content นี้)
- Content Info
  - URL, caption, thumbnail, platform_created_at
- Classification
  - `content_type`: `sale` | `review` | `branding` | `ecom` | `other`
  - `content_source`: `influencer` | `page` | `staff` | `ugc`
  - `status`: `ready` | `test_ad` | `active_ad` | `paused` | `expired`
- Product Mapping
  - `product_codes`: JSON ของ SKU codes
  - `product_group_id`: FK ไป `product_groups`
- Creator / Owner
  - `creator_id`, `creator_name`, `creator_details`
  - `employee_id`, `influencer_id`, `influencer_cost`
- Organic Metrics (Normalized)
  - views, impressions, reach, likes, comments, shares, saves
  - total_watch_time, avg_watch_time, completion_rate
  - `platform_metrics`: JSON สำหรับ field เฉพาะของแต่ละแพลตฟอร์ม
- Ad Performance (Aggregated)
  - `ads_total_cost`: total spend รวมทุกแพลตฟอร์ม
  - `ads_count`: จำนวน ads ที่ใช้ content นี้
  - `ace_ad_count`, `abx_ad_count`, `ace_details`, `abx_details`
  - `ads_details`: JSON รวมทุกแพลตฟอร์ม (`{"tiktok": [...], "facebook": [...]}`)
- Scoring
  - `pfm_score`: TikTok PFM
  - `fb_score`: Facebook/IG performance score
  - `unified_score`: Unified Content Impact Score (0–100)
  - `score_details`: breakdown ของคะแนน
- Boost & Expiration
  - `boost_factor`, `boost_start_date`, `boost_end_date`, `boost_reason`
  - `expire_date`
- Targeting
  - `targeting_template_id`, `targeting_override`

**History:** ตาราง `content_score_history` เก็บ snapshot ของคะแนนและ metrics เพื่อติดตามการเปลี่ยนแปลง

---

### 2.2 Ad Accounts & Platforms

ตาราง `ad_accounts` (model `AdAccount`) เก็บข้อมูลบัญชีโฆษณาในแต่ละแพลตฟอร์ม:

- `platform`: `tiktok` / `facebook` / `instagram`
- `external_account_id`: advertiser_id / act_xxx
- `name`, `status`, `timezone`, `currency`
- `config`: JSON สำหรับ config เฉพาะ เช่น pixel id, catalog id ฯลฯ
- ความสัมพันธ์:
  - `campaigns`: One‑to‑Many → `Campaign`
  - `contents`: เนื้อหาที่ผูกกับ account นี้เป็นหลัก

---

### 2.3 Campaign / AdGroup / Ad (Unified Ads Layer)

สามตารางหลักใน `campaigns`, `ad_groups`, `ads` ใช้ร่วมกันได้ทุกแพลตฟอร์ม

#### Campaign

- Platform & Account
  - `platform`, `ad_account_id`, `external_campaign_id`
- Info
  - `name`, `status`
- Objective & Budget
  - `objective`: map เข้า enum `CampaignObjective` (เช่น `reach`, `video_views`, `conversions`, `gmv_max`, `awareness`, `sales`)
  - `objective_raw`: string ตามที่แพลตฟอร์มส่งมา (เผื่อ enum ยังไม่รองรับ)
  - `budget_type`: `daily` / `lifetime`
  - `daily_budget`, `lifetime_budget`
- Schedule & Platform Data
  - `start_date`, `end_date`, `platform_data`, `last_synced_at`

#### AdGroup (TikTok AdGroup / Facebook AdSet)

- Platform & Campaign
  - `platform`, `campaign_id`, `external_adgroup_id`
- Info
  - `name`, `status`
- Optimization & Budget
  - `optimization_goal`, `optimization_goal_raw`, `billing_event`, bid fields
  - `budget_type`, `daily_budget`, `lifetime_budget`
- Schedule & Targeting
  - `start_time`, `end_time`, `schedule`
  - `targeting_template_id`, `targeting` (JSON)
- Aggregated Performance
  - `total_spend`, `impressions`, `clicks`, `conversions`
  - CTR, CPC, CPM, ROAS
- **New (2.0): Structure & Strategy**
  - `structure`: enum `AdGroupStructure`
    - `single_content` → 1 adgroup / 1 content (ACE‑style หรือ campaign แบบ “คลิปเดี่ยว”)
    - `multi_content` → 1 adgroup / หลาย content (ABX‑style, DCO หรือรวมหลายคลิป)
    - `unknown` → adgroup ที่ระบบยังไม่จัดหมวด (สร้างเอง/manual)
  - `strategy_tag`: string ระบุชื่อกลยุทธ์ของระบบ เช่น `"ACE"`, `"ABX"`, `"BRANDING_MULTI"`, `"PERFORMANCE_SINGLE"`, `"MANUAL"`
  - `content_style`: enum `ContentType` (sale / review / branding / ecom / other) เพื่อให้รู้ว่า adgroup นี้โฟกัสคอนเทนต์สไตล์ไหน (ใช้ช่วยตอน optimize)
- Tracking
  - `platform_data`, `last_synced_at`

#### Ad (Creative / Ad Level)

- Platform & AdGroup
  - `platform`, `ad_group_id`, `external_ad_id`
- Content Link
  - `content_id`: FK → `contents` (หนึ่ง ad ใช้เนื้อหาใดเป็นหลัก)
  - `creative_id`, `object_story_id` (ใช้กับ Facebook)
- Performance Metrics
  - spend, impressions, reach, clicks, video_views, thruplay, conversions, purchases, purchase_value
  - CTR, CPC, CPM, CVR, ROAS, frequency
  - `platform_metrics`: JSON เพิ่มเติม
- History
  - `ad_performance_history`: snapshot รายวันของ metrics

**ผลลัพธ์:** เราสามารถ query ได้ทั้ง

- “ทุก adgroup ที่เป็น `structure = 'single_content'` และ objective = `sales`”
- “ทุก adgroup ที่เป็น `multi_content` และ content_style = `branding`”

ทำให้ rule ของ optimizer เขียนได้ง่ายขึ้นมาก

---

### 2.4 ABX Adgroup (TikTok‑Specific Automation)

ตาราง `abx_adgroups` (model `ABXAdgroup`) ใช้สำหรับจัดการ adgroup ที่เป็น “ชุดทดสอบหลาย content” (ABX‑style) ฝั่ง TikTok:

- External Links
  - `platform` (ปกติ = TikTok), `external_adgroup_id`, `external_campaign_id`, `external_advertiser_id`
  - `ad_group_id`: FK ไป `ad_groups` (เชื่อมกับ unified layer)
- Configuration
  - `name`
  - `group_style`: enum `ContentType` – SALE / REVIEW / BRANDING / ECOM
  - `product_group_id`
  - `targeting_template_id`
- Status & Budget
  - `status`, `is_active`, `is_current_plan`
  - `plan_budget`, `plan_status`
- Performance
  - `pfm_score`, `ad_count`, `good_pfm_ad_count`
  - `total_spend`, `today_spend`

**หมายเหตุ:** ใน 2.0 เราสามารถมอง `ABXAdgroup` เป็น “วิวเฉพาะของ TikTok” ที่ช่วยให้ optimizer ทำงานได้ง่ายขึ้น โดยโครงหลักยังอยู่บน `ad_groups`

---

### 2.5 Products, Product Groups & Strategy Groups

#### Product (`products`)

ตัวแทนของ **SKU จริง** ที่ขายในระบบ (TikTok Shop, Shopee, Lazada, 7‑11 ฯลฯ):

- `code`: รหัสสินค้า เช่น `S1`, `L7` (unique)
- `name`, `description`, `category`, `price`, `image_url`
- สถานะ: `is_active`, `can_allocate_budget` (อนุญาตให้เอา SKU นี้ไปอยู่ในงบหรือไม่)
- External IDs: `tiktok_product_id`, `shopee_product_id`, `lazada_product_id`

> หลักคิดสำคัญ: **Product = สินค้าจริงที่มียอดขายจริง** ใช้ในการเชื่อมกับ sales pipeline และ SKU signals

#### Product Group (`product_groups`)

หน่วยหลักสำหรับ **จัดสรรงบโฆษณาและดู performance** (Budget Unit):

- `name`: ชื่อกลุ่มสินค้า เช่น "สบู่แตงโม [S2]" หรือ "ACNE SET"
- `product_codes`: JSON list ของ SKU ในกลุ่ม เช่น `["S1", "S2", "L7"]`
- `is_active`
- `default_content_style_weights`: สัดส่วน SALE/REVIEW/BRANDING/ECOM สำหรับกลุ่มนี้
- ความสัมพันธ์สำคัญ:
  - `budget_allocations`: ใช้ ProductGroup เป็นแกนในการวางแผนงบ (`BudgetPlan`/`DailyBudget`)
  - `abx_adgroups`: ใช้เป็น scope การรัน ABX automation

> ProductGroup = “กองสินค้า” ที่ทีม Media ใช้คุยเรื่องงบ เช่น “ชุดสิว 500k / เดือน”

#### Strategy Group (`strategy_groups`) – NEW (WeBoostX 2.0)

ใช้แทน “ชุดกลยุทธ์การยิงโฆษณา” ที่อาจครอบหลาย ProductGroup / หลายแบรนด์ เช่น:

- HERO_SET_ACNE – รวมทุก SKU สิวที่อยากดันเป็น Hero
- BRANDING_TOP10 – กลุ่มสินค้าสำหรับทำ Brand Awareness แยกจาก performance set
- SEASONAL_SONGKRAN – กลยุทธ์สำหรับช่วงเทศกาลสงกรานต์

โครงสร้างเสนอ:

- `id`, `code`, `name`, `description`
- `strategy_type`: enum เช่น `hero`, `branding`, `performance`, `seasonal`, `cross_brand`, ฯลฯ
- `is_active`
- Optional config:
  - `default_objectives`: รายการ objective แนะนำเช่น `["reach", "video_views"]`
  - `default_platform_mix`: เช่น `{"tiktok": 0.7, "facebook": 0.3}`
  - `default_content_style_weights`: เช่น `{"branding": 80, "sale": 20}`

Mapping:

- ตารางกลาง `strategy_group_items` (many‑to‑many):
  - `strategy_group_id` → FK → `strategy_groups`
  - `product_code` → อ้างอิงไปยัง SKU ใน `products` (หรือ product_id ถ้าต้องการ)

> แนวคิด: **งบจริง** ยัง allocate ที่ ProductGroup/SKU, ส่วน StrategyGroup เป็น “มุมมองเชิงกลยุทธ์” ซ้อนทับ เพื่อใช้เลือกชุดสินค้า/PG ที่จะดันหรือวิเคราะห์ผลรวม

การใช้งาน:

- UI สามารถให้ user เลือก StrategyGroup เพื่อ:
  - ดู performance รวมของกลยุทธ์ (โดยดึง sales/ads ของทุก SKU/PG ที่อยู่ในกลุ่ม)
  - สร้าง BudgetAllocation ให้หลาย ProductGroup ตาม strategy เดียวกันในคลิกเดียว
- Optimizer สามารถใช้ StrategyGroup เป็นอีกมุมมองหนึ่ง (เช่น ปรับงบให้ทุก Hero set พร้อมกัน) โดยไม่ทำให้โครงสร้างงบจริง (ProductGroup) สับสน

---

### 2.6 Budget Planning & Daily Budgets

#### BudgetPlan (`budget_plans`)

- ช่วงเวลาและงบรวมของแผน (เช่น รายเดือน)
- `allocation_type`: `ace` | `abx` | `manual`
- `platform_budgets`: JSON ระบุสัดส่วนต่อแพลตฟอร์ม เช่น `{"tiktok": 0.7, "facebook": 0.3}`

#### BudgetAllocation (`budget_allocations`)

- ผูกกับ `budget_plan` + `product_group`
- `platform` (optional) – ถ้าต้องการระบุว่า allocation นี้สำหรับ TikTok หรือ Facebook โดยเฉพาะ
- `allocated_budget`, `actual_spend`, `is_locked`
- `content_style_weights`: สัดส่วน SALE/REVIEW/BRANDING/ECOM สำหรับ allocation นี้

#### DailyBudget (`daily_budgets`)

- แยกงบรายวันต่อ allocation
- `planned_budget`, `actual_spend`
- Flag สำหรับการจัดสรร:
  - `is_ace_allocated`, `is_abx_allocated`
  - `content_style_budgets`: breakdown ของ budget รายวันตาม content style

#### BudgetOptimizationLog (`budget_optimization_logs`)

- เก็บผลของการรัน optimizer ในแต่ละครั้ง (ACE หรือ ABX หรือ unified)
- `changes_detail` เป็น JSON list ของการปรับงบ เช่น
  - ACE: ต่อ content (`{"content_id": ..., "budget": ...}`)
  - ABX: ต่อ adgroup (`{"adgroup_id": ..., "budget": ...}`)

---

### 2.7 Sales & SKU Signals

รองรับ SKU‑level signals เพื่อใช้ใน Unified Score และ Budget Optimizer:

- `online_sales_daily`: ยอดขายออนไลน์รายวัน (TikTok Shop, Shopee, Lazada)
- `saversure_scans_daily`: จำนวน scan / unique users รายวัน
- `offline_sales_weekly`: ยอดขายออฟไลน์รายสัปดาห์ (7‑11 ฯลฯ)
- `sku_signals`: ตารางรวม signal ตามวันต่อ SKU
  - รวม revenue/orders/scan/offline_units และคำนวณ `demand_score` + `trend_pct`

---

## 3. Scoring & Optimization Logic (Concept)

### 3.1 Platform‑Specific Scores

- **TikTok PFM (`pfm_score`)**

  - มาจาก `TikTokService.calculate_pfm_score` โดยใช้ views, likes, comments, shares, bookmarks; ปรับตาม view tier
  - ใช้ทั้งบน `Content` และ `ABXAdgroup` (ผ่านการรวม performance ของ ads ในกลุ่ม)

- **Facebook/Instagram Score (`fb_score`)**
  - วัดจาก reach efficiency, engagement rate, thruplay/completion, CPM ฯลฯ ใช้ค่าใน `platform_metrics` และ `ads_total_cost`

### 3.2 Unified Content Impact Score (`unified_score`)

สูตรแนวคิด (0–100):

- TikTok performance ≈ 50% (normalize จาก `pfm_score`)
- Facebook/IG performance ≈ 30% (normalize จาก `fb_score`)
- SKU‑level demand ≈ 20% (จาก `sku_signals.demand_score` ตาม product_codes)
- Boost factor (`boost_factor`) เป็น multiplier เสริม

คำนวณโดย `score_tasks.calculate_unified_score` และเก็บ snapshot ลง `content_score_history`

### 3.3 AdGroup Structure & Strategy

ใช้ field ใหม่ใน `ad_groups`:

- `structure`:
  - `single_content` (ACE‑style): 1 adgroup ยิง 1 content ชัดๆ – เหมาะกับเน้นผลลัพธ์ของคลิปเดี่ยว
  - `multi_content` (ABX‑style หรือ Multi‑Creative): 1 adgroup ยิงหลาย content – เหมาะกับการเทสต์/หมุนหลายคลิปใน adgroup เดียว
  - `unknown`: ยังไม่จัดหมวด / manual
- `strategy_tag`:
  - ให้ระบบตั้งชื่อกลยุทธ์เอง เช่น `"TIKTOK_ACE_SALES"`, `"TIKTOK_ABX_BRANDING"`, `"FB_SINGLE_SALES"`, ฯลฯ
- `content_style`:
  - ระบุ content style หลักของ adgroup (sale / branding / review / ecom)

ด้วย 3 field นี้ เราสามารถเขียน rule เช่น

- “เพิ่มงบให้ทุก **single_content** adgroup ที่ objective = Sales และ content_style = `sale` ถ้า ROAS > X”
- “ลดงบ adgroup แบบ **multi_content** ที่มี unified_score เฉลี่ยต่ำกว่า threshold”

โดยไม่ผูกกับคำว่า ACE/ABX ตายตัว

### 3.4 Budget Optimizer (Rule‑Based MVP)

งานหลักใน `optimization_tasks.py`:

- ACE Allocation:
  - มองจากมุม `Content` ต่อ `DailyBudget` (allocation_type = `ace`)
  - แบ่งงบรายวันตาม `unified_score` ของ content ใน product_group
  - อนาคต: map ไปหา adgroup ที่ `structure = single_content` และ apply budget ผ่าน API
- ABX Allocation:
  - มองจากมุม `ABXAdgroup` ต่อ `DailyBudget` (allocation_type = `abx`)
  - ใช้ `pfm_score` + content style weights เพื่อปรับงบในแต่ละ adgroup

ต่อไปสามารถเพิ่ม rule multi‑platform เช่น:

- CTR/ROAS ต่ำทุกแพลตฟอร์ม → ลดงบ / ปิด adgroup
- Platform ไหน ROAS ดีกว่า → โยกส่วนของ budget plan ไป platform นั้นโดยเปลี่ยน `daily_budgets` ของ TikTok vs Facebook

---

## 4. Data Pipelines & Schedulers (Cron)

ดูได้ใน `tasks/scheduler.py`:

- Every 60 mins
  - `sync_content_job`: ดึง content จากทุกแพลตฟอร์ม (เริ่มจาก TikTok ก่อน)
  - `sync_ads_spend_job`: ดึง spend ของทุก ad แล้วอัปเดต `ads_details` + `ads_total_cost`
- Every 15–30 mins
  - `sync_ads_job`: ดึง campaign/adgroup/ad จากแพลตฟอร์ม (TikTok ทำแล้ว, Facebook วางโครงไว้)
  - `calculate_scores_job`: อัปเดต PFM/FB/unified score ทุก content
- Every 2–3 hours
  - `optimize_budget_job`: รัน budget optimizer (ACE/ABX)
- Daily
  - `sync_saversure_job`: ดึง Saversure scans (logic ยังเป็น TODO)
  - `daily_budget_job`: สร้าง & ปรับ `daily_budgets`
  - (ต่อยอด) update `sku_signals` และ recalc unified ranking
- Weekly
  - `sync_offline_sales_job`: ดึง offline sales (7‑11 ฯลฯ)

---

## 5. Naming Conventions & Shortcodes (ACE / ABX / Strategy)

### 5.1 หลักคิด

เพื่อให้ทั้ง **คน** และ **ระบบ** อ่านเข้าใจโครงสร้างแคมเปญได้ง่าย เราจะใช้ “shortcode” ในชื่อ Campaign / AdGroup / Ad ตามแนวทางของระบบเก่า โดยเชื่อมกับโครงสร้างใหม่ (`CampaignObjective`, `AdGroup.structure`, `content_style`, `strategy_tag`) ดังนี้:

- แยก **โครงสร้าง AdGroup** ด้วย `AdGroupStructure`:
  - `single_content` → 1 adgroup / 1 content (ACE‑style)
  - `multi_content` → 1 adgroup / หลาย content (ABX‑style หรือ multi‑creative)
  - `unknown` → adgroup ที่ยังไม่จัดประเภท (manual / ดึงจากนอกระบบ)
- ใช้ฟิลด์ `strategy_tag` เพื่อผูกกลยุทธ์เชิงธุรกิจ เช่น `"TIKTOK_ACE_VIDEO_VIEWS_SALE"`, `"TIKTOK_ABX_REACH_BRANDING"`
- ใช้ `content_style` (enum `ContentType`) เพื่อสื่อว่าแอดกรุ๊ปนั้นเน้น SALE / REVIEW / BRANDING / ECOM ฯลฯ

### 5.2 รหัสย่อ Objective (OBJ Code)

สำหรับ TikTok (และต่อยอดไปแพลตฟอร์มอื่น) เรา map `CampaignObjective` เป็นรหัสสั้น ๆ ใช้ในชื่อ เช่น:

- `VIDEO_VIEWS` → `VV`
- `REACH` / `REACH_FREQUENCY` → `RCH`
- `CONVERSIONS` → `CV`
- `GMV_MAX` (Product Sales) → `GMV`
- `LEAD_GENERATION` → `LEAD`
- `APP_INSTALL` → `APP`
- (objective อื่น ๆ สามารถเพิ่ม mapping ได้ในภายหลัง)

### 5.3 Pattern สำหรับ TikTok – Single Content (ACE‑style)

ใช้เมื่อ `AdGroup.structure = SINGLE_CONTENT` และ `strategy_tag` ขึ้นต้นด้วย `ACE` หรือแนวคิดเดียวกัน:

- **Campaign name**
  - รูปแบบ:  
    `[{PRODUCT_CODES}]_ACE_<OBJ>_{STYLE}`  
    ตัวอย่าง: `[S1][S2]_ACE_<VV>_SALE`
- **AdGroup name**
  - รูปแบบ:  
    `[{PRODUCT_CODES}]_ACE_<{TARGETING_CODE}>_{STYLE}`  
    ตัวอย่าง: `[S1][S2]_ACE_<MF_ACNE_18_34>_SALE`
- **Ad name**
  - รูปแบบ:  
    `[{PRODUCT_CODES}]_ACE_<{TARGETING_CODE}>_{STYLE}_{ITEM_ID}_{YYYYMMDD}`  
    ตัวอย่าง: `[S1][S2]_ACE_<MF_ACNE_18_34>_SALE_741556431_2025-02-01`

**ข้อดี:** ยังใช้ `_ACE_` เหมือนระบบเก่า ทำให้ logic ปัจจุบันที่ detect ACE จากชื่อ (เช่น regex หรือ LIKE `'%_ACE_%'`) ใช้งานต่อได้ทันที

### 5.4 Pattern สำหรับ TikTok – Multi Content (ABX‑style)

ใช้เมื่อ `AdGroup.structure = MULTI_CONTENT` และ `strategy_tag` ระบุว่าเป็น ABX / multi‑content:

- **Campaign name**
  - รูปแบบ (เข้ากับระบบเก่า):  
    `[{PRODUCT_GROUP}]_ABX_ALLOCATE_ADGROUP`
- **AdGroup name**
  - รูปแบบ:  
    `[{PRODUCT_GROUP}]_ABX_({TARGETING_CODE})_{STYLE}#{NN}`  
    ตัวอย่าง: `[S1][S2]_ABX_(MF_ACNE_18_34)_SALE#01`
  - `NN` คือ running number ต่อกลยุทธ์เดียวกัน (เช่น #01–#05) เพื่อจำกัดจำนวน adgroup ต่อ targeting

ระบบจะยังคงใช้ `_ABX_` เพื่อตรวจจับ ABX adgroup และสามารถดึง `targeting_code` กลับจากชื่อผ่าน regex (`substring((ad->>'ad_name') from '_ABX_\\(([^\\)]+)\\)_')`) แบบที่ใช้ในระบบเก่าได้

### 5.5 การผูกกับ Field ใน DB

เมื่อระบบสร้างแคมเปญ/แอดกรุ๊ป/แอดใหม่จาก UI หรือ automation ควร:

1. ตัดสินใจจาก input ว่าเป็น single หรือ multi‑content → set `AdGroup.structure`
2. สร้าง `strategy_tag` เช่น `"TIKTOK_ACE_VV_SALE"` หรือ `"TIKTOK_ABX_RCH_BRANDING"` ตาม `(platform, objective, structure, content_style)`
3. เลือก naming template ตาม rule ในข้อ 5.3–5.4 แล้ว generate
4. บันทึกชื่อที่สร้างลง TikTok API และ sync กลับมาใน `ads_details` / `Campaign` / `AdGroup`

ผลลัพธ์คือ:

- ฝั่ง user เห็นชื่อแล้วเดาทันทีว่าแคมเปญนี้คืออะไร, ยิงอะไร, targeting ไหน, style ไหน
- ฝั่งระบบสามารถใช้ทั้ง **shortcode (`_ACE_`, `_ABX_`)** และ **field เชิงโครงสร้าง (`structure`, `strategy_tag`, `content_style`, `objective`)** ทำงานร่วมกันได้ เช่นการ detect และ optimize งบ

---

## 6. Extensibility for TikTok Objectives

Mapping ระหว่าง TikTok Objective กับ `CampaignObjective` จะอยู่ใน `TikTokAdsService._map_objective` เช่น:

- Awareness / Reach
  - TikTok: `REACH`, `RF` → `CampaignObjective.REACH` / `REACH_FREQUENCY`
- Consideration
  - `VIDEO_VIEWS` → `VIDEO_VIEWS`
  - `COMMUNITY_INTERACTION` (สามารถ map เป็น `ENGAGEMENT` หรือ `AWARENESS` ตามการใช้งาน)
  - `TRAFFIC` → `TRAFFIC`
- Conversion / Sales
  - `CONVERSIONS` → `CONVERSIONS`
  - `PRODUCT_SALES` → `GMV_MAX`
  - `LEAD_GENERATION` → `LEAD_GENERATION`
- App
  - `APP_INSTALLS` → `APP_INSTALL`

หาก TikTok เพิ่ม objective ใหม่ในอนาคต สามารถ:

1. เพิ่ม case ใน `_map_objective` หรือ
2. เก็บไว้ใน `objective_raw` และให้ optimizer อ่านค่าตรงนี้เป็นเงื่อนไข

โดยไม่ต้องแก้ schema

---

## 7. Roadmap Implementation (แนะนำ)

1. **เติม Facebook/Instagram Integrations**
   - Implement `sync_facebook_content` + `sync_instagram_content`
   - Implement `sync_facebook_ads` (campaign/adset/ad + insights)
2. **เติม Logic กำหนด `structure` + `strategy_tag` อัตโนมัติ**
   - จาก naming pattern (`_ACE_`, `_ABX_`) และ/หรือ จากข้อมูลใน `ABXAdgroup`
   - เพิ่ม logic ตอนสร้าง adgroup ผ่านระบบให้ set field เหล่านี้ให้ชัด
3. **Sales & SKU Signals**
   - Implement `sales_tasks.sync_saversure_data`, `sync_offline_sales`, `update_sku_signals`
   - ต่อ `score_tasks.calculate_unified_score` ให้ดึง `demand_score` จาก `sku_signals`
4. **Rule‑Based Multi‑Platform Optimizer**
   - ใช้ `CampaignObjective`, `AdGroup.structure`, `content_style`, `pfm_score`, `fb_score`, `sku_signals` เพื่อสร้าง rule ชุดแรก
   - เพิ่ม endpoint preview + apply เพื่อดูผลก่อน commit งบจริง
5. **AI/Phase 2**
   - หลัง rule‑based เสถียร ค่อยต่อยอด AI budget optimizer และ content recommendation ตาม requirement เดิม

---

## 8. Summary

- โครงสร้างฐานข้อมูล WeBoostX 2.0 ถูกออกแบบให้ **content‑centric**, รองรับหลายแพลตฟอร์มและหลาย objective โดยไม่ผูกตายกับคำว่า ACE/ABX
- Field ใหม่ใน `ad_groups` (`structure`, `strategy_tag`, `content_style`) ทำให้ระบบเข้าใจ pattern 1 adgroup/1 content หรือ 1 adgroup/หลาย content ได้ชัดเจน และช่วยให้เขียน rule optimization ได้ยืดหยุ่น
- ชั้น Scoring, Budget Plan, Sales/SKU signals และ Scheduler ถูกออกแบบให้ทำงานร่วมกัน เพื่อให้ในอนาคตสามารถทำ **Unified, Cross‑Platform Budget Optimization** ได้อย่างเป็นระบบ
