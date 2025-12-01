# 📋 WeBoostX - System Requirements Document

> **Version:** 1.0  
> **Last Updated:** November 2025  
> **Purpose:** สรุประบบทั้งหมดเพื่อใช้เป็น Reference สำหรับการ Redesign โปรเจคใหม่

---

## 📁 สารบัญ

1. [ภาพรวมระบบ](#1-ภาพรวมระบบ)
2. [Tech Stack](#2-tech-stack)
3. [Database Models](#3-database-models)
4. [Features & Modules](#4-features--modules)
5. [API Endpoints](#5-api-endpoints)
6. [Background Jobs / Cron](#6-background-jobs--cron)
7. [External Integrations](#7-external-integrations)
8. [User Roles & Authentication](#8-user-roles--authentication)
9. [Suggested Improvements](#9-suggested-improvements)

---

## 1. ภาพรวมระบบ

**WeBoostX** เป็นระบบจัดการโฆษณา TikTok Ads แบบ Automated ที่รวมการทำงานหลักๆ ดังนี้:

- 📊 **Content Management** - จัดการ TikTok Posts และวิเคราะห์ Performance (PFM Score)
- 💰 **Budget Management** - วางแผนและจัดสรรงบประมาณโฆษณาตาม Product Group
- 🎯 **Ad Automation** - สร้างและปรับ Budget โฆษณาอัตโนมัติ (ACE & ABX)
- 📈 **Analytics & Monitoring** - Dashboard และ Content Suggestion
- ⏰ **Scheduled Tasks** - งาน Background สำหรับ Sync ข้อมูลและปรับ Budget

---

## 2. Tech Stack

### Backend
| Technology | Version | Purpose |
|------------|---------|---------|
| Python | 3.8+ | Main Language |
| Flask | 2.x | Web Framework |
| SQLAlchemy | 1.4+ | ORM |
| PostgreSQL | 13+ | Database |
| APScheduler / Schedule | - | Background Jobs |

### Frontend
| Technology | Purpose |
|------------|---------|
| Jinja2 | Template Engine |
| Bootstrap 4.5 | CSS Framework |
| jQuery | JavaScript Library |
| DataTables | Table Plugin |
| Select2 | Dropdown Plugin |
| SweetAlert2 | Alert/Modal |
| DateRangePicker | Date Selection |
| Chart.js (optional) | Charts |

### External Services
| Service | Purpose |
|---------|---------|
| TikTok Marketing API | Ads Management |
| LINE Notify | Notifications |

---

## 3. Database Models

### 3.1 User Management

```python
# Users - ผู้ใช้งานระบบ
class Users:
    id: Integer (PK)
    email: String (unique)
    password_hash: String
    first_name: String
    last_name: String
    registered_on: DateTime
    last_login: DateTime
    is_active: Boolean
    is_approved: Boolean  # รอ Admin approve
    user_type: String  # 'admin', 'user', 'viewer'
```

### 3.2 Product Management

```python
# Products - สินค้าทั้งหมด
class Products:
    code: String (PK)  # รหัสสินค้า เช่น "S1", "L7"
    productname: String
    status: String  # '1' = active, '0' = inactive
    allocate_status: Boolean  # อนุญาตให้จัดสรร budget ได้หรือไม่

# ProductGroup - กลุ่มสินค้า (ใช้จัดสรร budget)
class ProductGroup:
    id: Integer (PK)
    name: String  # เช่น "สบู่แตงโม [S2]"
    products: JSON  # ["S1", "S2"] - รายการสินค้าในกลุ่ม
    is_active: Boolean
    created_at: DateTime
    updated_at: DateTime
```

### 3.3 TikTok Content

```python
# TiktokPost - Content จาก TikTok
class TiktokPost:
    item_id: String (PK)  # TikTok video ID
    create_time: Timestamp
    update_time: Timestamp
    channel_acc_id: Integer
    channel_type: String
    url: String
    caption: String
    thumbnail_url: String
    
    # Video Stats
    video_duration: Float
    video_views: Integer
    likes: Integer
    bookmarks: Integer
    comments: Integer
    shares: Integer
    reach: Integer
    
    # Watch Time Stats
    total_time_watched: Float
    average_time_watched: Float
    full_video_watched_rate: Float
    
    # Performance
    pfm_score: Float  # คะแนน Performance (0-2+)
    
    # Product & Content Info
    products: String  # Legacy field
    products_json: JSON  # ["S1", "S2"]
    content_type: String  # SALE, REVIEW, BRANDING, ECOM
    content_status: String  # ACE_AD, DELETED, etc.
    content_expire_date: Timestamp
    
    # Ads Info
    ads_details: JSON
    ads_total_media_cost: Float
    ace_ad_count: Integer
    ace_details: JSON
    abx_ad_count: Integer
    abx_details: JSON
    
    # Boost Feature (เพิ่ม priority ให้ content)
    boost_factor: Decimal(3,2)  # ตัวคูณ priority
    boost_start_date: Date
    boost_expire_date: Date
    boost_reason: Text
    boost_created_by: String
    
    # Creator Info
    creator_details: JSON
    created_cost_content: Float
    created_budget_date: Date
    
    # Targeting
    targeting_details: JSON
```

### 3.4 TikTok Targeting

```python
# TikTokTargeting - Template สำหรับ Ad Targeting
class TikTokTargeting:
    id: Integer (PK)
    name: String
    age: JSON  # ["AGE_18_24", "AGE_25_34"]
    gender: String  # MALE, FEMALE, UNLIMITED
    location: JSON  # Location IDs
    language: JSON
    interest_categories: JSON
    action_categories: JSON
    device_types: JSON
    network_types: JSON
    create_user: String
    create_time: DateTime
    is_approve: Boolean  # Admin approved
    audience_lower: Integer  # Estimated audience
    audience_upper: Integer
    status: Boolean
```

### 3.5 Budget Management

```python
# BudgetPlan - แผนงบประมาณรายเดือน
class BudgetPlan:
    id: Integer (PK)
    name: String  # เช่น "Budget Dec 2024"
    start_date: Date
    end_date: Date
    total_budget: Decimal(15,2)
    allocate_type: String  # 'content' หรือ 'adgroup'
    created_at: DateTime
    updated_at: DateTime

# BudgetAllocation - จัดสรร budget ให้แต่ละ Product Group
class BudgetAllocation:
    id: Integer (PK)
    budget_plan_id: FK -> BudgetPlan
    product_group_id: FK -> ProductGroup
    allocated_budget: Decimal(15,2)
    is_locked: Boolean  # Lock ไม่ให้ปรับอัตโนมัติ
    default_content_style_allocate: JSON  # {"SALE": 100, "REVIEW": 0, ...}
    adgroup_budget_update_time: DateTime

# DailyBudget - งบประมาณรายวัน
class DailyBudget:
    id: Integer (PK)
    budget_allocation_id: FK -> BudgetAllocation
    date: Date
    planned_budget: Decimal(15,2)
    actual_budget: Decimal(15,2)  # ค่าใช้จ่ายจริง
    is_locked: Boolean
    is_ace_start_allocate: Boolean
    content_style_allocations: JSON
```

### 3.6 Ad Group (ABX)

```python
# ABXAdgroup - Adgroup ที่สร้างในระบบ ABX
class ABXAdgroup:
    id: Integer (PK)
    adgroup_id: String (unique)  # TikTok Adgroup ID
    adgroup_name: String (unique)
    targeting_id: String  # FK ไปหา Targeting
    group_style: String  # SALE, REVIEW, BRANDING, ECOM
    product_group: String
    product_group_json: JSON
    pfm_score: Decimal(5,2)
    
    # TikTok Info
    campaign_id: String
    advertiser_id: String
    ad_count: Integer
    
    # Budget Plan
    plan_adgroup_budget: Decimal(10,2)
    plan_adgroup_status: String
    
    # Tracking
    create_time: DateTime
    created_by: String
    update_time: DateTime
    update_by: String
    budget_update_time: DateTime
    is_active: Boolean
    is_currentplan: Boolean
```

### 3.7 System Tables

```python
# TiktokAdsAccount - บัญชีโฆษณา TikTok
class TiktokAdsAccount:
    acc_id: String (PK)
    acc_name: String
    status: Integer  # 1 = active
    advertiser_start_date: Date

# ContentType - ประเภท Content
class ContentType:
    id: String (PK)  # SALE, REVIEW, etc.
    plan_pfm: Integer
    group_style: String

# ContentStatus - สถานะ Content
class ContentStatus:
    id: String (PK)  # ACE_AD, DELETED, etc.

# Notification - การแจ้งเตือน
class Notification:
    id: Integer (PK)
    user_id: FK -> Users
    title: String
    message: String
    timestamp: DateTime
    read: Boolean

# Task - Log การทำงาน Background
class Task:
    id: Integer (PK)
    name: String
    status: String  # running, completed, failed
    start_time: DateTime
    end_time: DateTime
    message: String
```

---

## 4. Features & Modules

### 4.1 🔐 Authentication Module

| Feature | Description |
|---------|-------------|
| Login/Logout | Email + Password authentication |
| Register | สมัครสมาชิกใหม่ (ต้องรอ Admin approve) |
| Forgot Password | Reset password via email (placeholder) |
| User Approval | Admin approve ผู้ใช้ใหม่ |
| Role-based Access | admin, user, viewer |

### 4.2 📊 Dashboard Module

| Feature | Description |
|---------|-------------|
| Summary Stats | Active campaigns, Today's spend, MTD spend |
| Content Status | แสดงจำนวน content แยกตามสถานะ |
| Product Group Performance | PFM เฉลี่ย, จำนวน content ต่อกลุ่ม |
| Campaign Performance | Top campaigns by adgroups |
| Content Performance | Top content by PFM score |
| Date Range Filter | กรองข้อมูลตามช่วงเวลา |

### 4.3 📝 TikTok Content Module

| Feature | Description |
|---------|-------------|
| Content List | แสดง TikTok Posts ทั้งหมด |
| Content Details | ดู stats, PFM, ads info |
| Content Type Assignment | กำหนดประเภท content (SALE, REVIEW, etc.) |
| Product Assignment | กำหนดสินค้าให้ content |
| Status Management | จัดการสถานะ content |
| Boost Feature | เพิ่ม priority ให้ content บางตัว |
| Expire Date | กำหนดวันหมดอายุ content |

### 4.4 🎯 TikTok Targeting Module

| Feature | Description |
|---------|-------------|
| Create Targeting | สร้าง targeting template ใหม่ |
| Edit Targeting | แก้ไข targeting |
| Targeting List | แสดง targeting ทั้งหมด |
| Audience Estimation | ประมาณขนาด audience |
| Approval Workflow | Admin approve targeting ก่อนใช้งาน |
| Interest Categories | เลือก interest หลายระดับ |
| Action Categories | Video/Creator/Hashtag related |

### 4.5 📦 Product Management Module

| Feature | Description |
|---------|-------------|
| Product Manager | CRUD สินค้า |
| Product Groups | จัดกลุ่มสินค้า |
| Group Content Count | นับ content ในแต่ละกลุ่ม |
| Allocate Status | เปิด/ปิดการจัดสรร budget |

### 4.6 💰 Budget Management Module (V1 & V2)

| Feature | Description |
|---------|-------------|
| Budget Plans | สร้างแผนงบประมาณรายเดือน |
| Budget Allocation | จัดสรร budget ให้ Product Groups |
| Daily Budget | วางแผนงบประมาณรายวัน |
| Lock/Unlock | Lock budget ไม่ให้ปรับอัตโนมัติ |
| Content Style Allocation | กำหนดสัดส่วน SALE/REVIEW/BRANDING/ECOM |
| PFM Tracking | แสดงจำนวน good PFM content & ads |
| Auto Optimization (V2) | ปรับ budget อัตโนมัติตาม performance |
| Budget Reports | รายงานการใช้งบประมาณ |

### 4.7 📢 Ads Automation Module

#### ACE (Content-based Ads)
| Feature | Description |
|---------|-------------|
| Auto Create Ads | สร้าง ads จาก content ที่มี good PFM |
| Budget Distribution | กระจาย budget ตาม content performance |
| Content Style Based | แยกตาม SALE, REVIEW, etc. |

#### ABX (Adgroup-based Ads)
| Feature | Description |
|---------|-------------|
| Adgroup Management | จัดการ Adgroups ที่สร้างในระบบ |
| Create Adgroup | สร้าง Adgroup ใหม่บน TikTok |
| Add Ads to Adgroup | เพิ่ม ads เข้า adgroup |
| Budget Adjustment | ปรับ budget adgroup อัตโนมัติ |
| PFM Scoring | คำนวณ PFM ของ adgroup |

#### Auto Budget Adjustment
| Feature | Description |
|---------|-------------|
| Auto Run ABX/ACE | รันปรับ budget ทั้งระบบ |
| Preview Mode | ดูตัวอย่างก่อนปรับจริง |
| V2 Optimization | ใช้ algorithm ขั้นสูงในการปรับ |

### 4.8 📈 Monitoring Module

| Feature | Description |
|---------|-------------|
| Monitor Dashboard | ภาพรวมสถานะระบบ |
| Adgroups without PFM | แสดง adgroups ที่ไม่มี good PFM |
| Alert System | แจ้งเตือนเมื่อมีปัญหา |

### 4.9 💡 Content Suggestion Module (NEW)

| Feature | Description |
|---------|-------------|
| PFM Analysis | วิเคราะห์ PFM ของทุก Product Group |
| Suggestion Level | Critical / High / Medium / Low / None |
| Priority Score | คะแนน 0-100 สำหรับเรียงลำดับ |
| Content Metrics | Good PFM count, ACE/ABX ads count |
| Expiring Alert | แจ้งเตือน content ใกล้หมดอายุ |
| Recent Activity | ตรวจสอบ content ใหม่ใน 30 วัน |

### 4.10 🔔 Notification Module

| Feature | Description |
|---------|-------------|
| In-app Notifications | แจ้งเตือนภายใน app |
| Mark as Read | อ่านแล้ว/ยังไม่อ่าน |
| Clear All | ลบ notification ทั้งหมด |

---

## 5. API Endpoints

### 5.1 Authentication APIs
```
POST /login          - Login
POST /logout         - Logout
POST /register       - Register new user
GET  /pending_users  - List pending users (admin)
POST /approve_user   - Approve user (admin)
```

### 5.2 Dashboard APIs
```
GET /api/dashboard/summary              - Summary stats
GET /api/dashboard/campaign_performance - Campaign performance
GET /api/dashboard/content_performance  - Content performance
```

### 5.3 Content APIs
```
GET  /tiktok                  - Content list
GET  /tiktok/content/<id>     - Content detail
POST /tiktok/update_content   - Update content
POST /api/boost/content       - Boost content
```

### 5.4 Budget APIs (V1 & V2)
```
# V1
GET  /budget_manager_list           - List budget plans
GET  /budget_monthly_detail/<id>    - Budget plan detail
POST /create_budget_plan            - Create budget plan
POST /api/update_budget_plan/<id>   - Update budget
POST /api/delete_budget_plan/<id>   - Delete budget plan

# V2 (Enhanced)
GET  /budget_manager_list_v2              - Enhanced list
GET  /budget_monthly_detail_v2/<id>       - Enhanced detail
POST /api/v2/budget/optimize              - Optimize single budget
POST /api/v2/budget/auto-optimize-all     - Auto optimize all
POST /api/v2/budget/batch-update          - Batch update
GET  /api/v2/budget/report                - Generate report
```

### 5.5 Daily Budget APIs
```
GET  /api/daily_budget/<allocation_id>              - Get daily budgets
POST /api/daily_budget/<allocation_id>/update       - Update daily budget
POST /api/v2/daily-budget/<allocation_id>/batch     - Batch update
```

### 5.6 Product APIs
```
GET  /product_manager            - Product list
POST /add_product                - Add product
POST /update_product_status      - Update product
GET  /product_groups             - Product groups
POST /product_groups/create      - Create group
POST /product_groups/update/<id> - Update group
DELETE /product_groups/<id>      - Delete group
```

### 5.7 Targeting APIs
```
GET  /tiktok_targeting_list          - Targeting list
GET  /tiktok_targeting/create        - Create form
POST /tiktok_targeting/create        - Create targeting
GET  /tiktok_targeting/detail/<id>   - Targeting detail
POST /tiktok_targeting/update/<id>   - Update targeting
```

### 5.8 Ads Automation APIs
```
# ACE
POST /api/v2/ace/auto-adjust/<plan_id>/<group_id>  - Auto adjust ACE

# ABX
GET  /abx_adgroup/<group_id>                        - Adgroup detail
POST /abx_adgroup/create                            - Create adgroup
POST /abx_adgroup/<id>/add_ads                      - Add ads to adgroup
POST /api/v2/abx/auto-budget/<plan_id>/<group_id>   - Auto adjust ABX

# Combined
GET  /run_all_task               - Run all tasks page
POST /auto_run_adjust_abx_ace    - Auto run V1
POST /auto_run_adjust_abx_ace_v2 - Auto run V2
```

### 5.9 Content Suggestion APIs
```
GET /content_suggestion                        - Dashboard
GET /api/content_suggestion/group/<id>        - Group detail
GET /api/content_suggestion/refresh           - Refresh data
```

### 5.10 Task APIs
```
GET  /run_all                      - Run all tasks
POST /sync_tiktok_posts            - Sync TikTok posts
POST /update_all_ads_total_cost    - Update ads costs
POST /update_pfm_all               - Update PFM scores
```

---

## 6. Background Jobs / Cron

### Daily Jobs
| Job | Time | Description |
|-----|------|-------------|
| `sync_daily_budgets` | 00:00 | Sync งบประมาณรายวัน |
| `auto_redistribute_budgets` | 02:00 | ปรับกระจาย budget อัตโนมัติ |

### Weekly Jobs
| Job | Time | Description |
|-----|------|-------------|
| `weekly_budget_report` | Monday 06:00 | สรุปรายงาน budget รายสัปดาห์ |

### Monthly Jobs
| Job | Time | Description |
|-----|------|-------------|
| `cleanup_old_budget_data` | Every 30 days 03:00 | ลบข้อมูลเก่า |

### Manual Tasks (Run via UI)
| Task | Description |
|------|-------------|
| Sync TikTok Posts | ดึง posts ใหม่จาก TikTok |
| Update Ads Costs | อัพเดทค่าใช้จ่าย ads |
| Update PFM Scores | คำนวณ PFM ใหม่ทั้งหมด |
| Sync ACE Details | ดึง ACE ads details |
| Sync ABX Details | ดึง ABX adgroup details |
| Auto Adjust Budget | ปรับ budget อัตโนมัติ |

---

## 7. External Integrations

### 7.1 TikTok Marketing API

**Base URL:** `https://business-api.tiktok.com/open_api/v1.3/`

| API | Purpose |
|-----|---------|
| `/ad/get/` | Get ads list |
| `/ad/create/` | Create new ad |
| `/ad/update/` | Update ad |
| `/adgroup/get/` | Get adgroups |
| `/adgroup/create/` | Create adgroup |
| `/adgroup/update/` | Update adgroup budget/status |
| `/campaign/get/` | Get campaigns |
| `/report/integrated/get/` | Get performance reports |
| `/tool/interest_category/` | Get interest categories |
| `/tool/action_category/` | Get action categories |
| `/tool/region/` | Get locations |
| `/tool/audience_size_status/get/` | Estimate audience size |

**Authentication:** Access Token in header

### 7.2 LINE Notify

| Function | Purpose |
|----------|---------|
| `linenotifyTojoe()` | ส่งแจ้งเตือนไปยัง developer |
| `linenotifyToAdsOnline()` | ส่งแจ้งเตือนไปยัง team |

---

## 8. User Roles & Authentication

### Roles
| Role | Permissions |
|------|-------------|
| **admin** | Full access ทุกฟีเจอร์, approve users, manage system |
| **user** | Access content, budget, ads automation |
| **viewer** | View only (placeholder, ยังไม่ implement) |

### Protected Routes
- ใช้ `@login_required` decorator
- Session-based authentication
- Redirect to login if not authenticated

---

## 9. Suggested Improvements

### 🏗️ Architecture
1. **แยก API Layer ชัดเจน** - ใช้ Flask-RESTful หรือ Flask-RESTX
2. **Service Layer** - แยก business logic ออกจาก routes
3. **Repository Pattern** - แยก database operations
4. **Config Management** - ใช้ different configs for dev/staging/prod
5. **Error Handling** - Centralized error handling

### 💾 Database
1. **Migrations** - ใช้ Flask-Migrate (Alembic)
2. **Indexes** - เพิ่ม indexes สำหรับ query ที่ใช้บ่อย
3. **Soft Delete** - เพิ่ม `deleted_at` แทนการลบจริง
4. **Audit Trail** - Log การเปลี่ยนแปลงข้อมูล

### 🔐 Security
1. **JWT Authentication** - เปลี่ยนจาก session เป็น JWT
2. **Rate Limiting** - ป้องกัน API abuse
3. **Input Validation** - ใช้ Marshmallow หรือ Pydantic
4. **CORS** - Configure properly

### 📊 Performance
1. **Caching** - Redis for frequent queries
2. **Async Tasks** - Celery for background jobs
3. **Database Connection Pool** - Configure properly
4. **Pagination** - ทุก list endpoint

### 🧪 Testing
1. **Unit Tests** - pytest
2. **Integration Tests** - API testing
3. **E2E Tests** - Selenium/Playwright

### 📝 Code Quality
1. **Type Hints** - เพิ่ม type annotations
2. **Docstrings** - Document ทุก function
3. **Linting** - flake8, black
4. **Pre-commit Hooks**

### 🚀 DevOps
1. **Docker Compose** - มีแล้ว แต่ปรับปรุงได้
2. **CI/CD** - GitHub Actions
3. **Monitoring** - Prometheus + Grafana
4. **Centralized Logging** - ELK Stack

---

## 📌 Quick Summary

| Module | Main Tables | Key Features |
|--------|-------------|--------------|
| Auth | Users | Login, Register, Approve |
| Content | TiktokPost | Manage, PFM, Boost |
| Product | Products, ProductGroup | CRUD, Grouping |
| Targeting | TikTokTargeting | Create, Approve |
| Budget | BudgetPlan, BudgetAllocation, DailyBudget | Plan, Allocate, Track |
| Ads | ABXAdgroup | Adgroup management |
| Automation | - | ACE/ABX auto adjust |
| Suggestion | - | PFM analysis & recommendations |

---

## 📎 Files Structure (Recommended New Structure)

```
project/
├── app/
│   ├── __init__.py           # App factory
│   ├── config.py             # Configuration
│   ├── extensions.py         # Flask extensions
│   │
│   ├── models/               # Database models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── product.py
│   │   ├── content.py
│   │   ├── budget.py
│   │   └── ads.py
│   │
│   ├── api/                  # API blueprints
│   │   ├── v1/
│   │   │   ├── auth.py
│   │   │   ├── content.py
│   │   │   ├── budget.py
│   │   │   └── ads.py
│   │   └── v2/
│   │       └── ...
│   │
│   ├── services/             # Business logic
│   │   ├── auth_service.py
│   │   ├── content_service.py
│   │   ├── budget_service.py
│   │   ├── ads_service.py
│   │   └── tiktok_service.py
│   │
│   ├── repositories/         # Database operations
│   │   └── ...
│   │
│   ├── schemas/              # Validation schemas
│   │   └── ...
│   │
│   ├── tasks/                # Background tasks
│   │   └── ...
│   │
│   ├── utils/                # Utilities
│   │   └── ...
│   │
│   └── templates/            # Jinja templates
│       └── ...
│
├── tests/                    # Tests
│   ├── unit/
│   └── integration/
│
├── migrations/               # Database migrations
├── static/                   # Static files
├── logs/                     # Log files
├── docker/                   # Docker configs
├── .env.example
├── requirements.txt
├── docker-compose.yml
└── README.md
```

---

**📝 Note:** Document นี้สรุปจาก codebase ปัจจุบัน เพื่อใช้เป็น reference ในการ redesign โปรเจคใหม่ให้มีโครงสร้างที่ดีขึ้น

