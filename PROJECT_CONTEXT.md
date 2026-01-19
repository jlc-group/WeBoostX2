# WeBoostX 2.0 - Project Context

## 🎯 Vision

WeBoostX 2.0 เป็นระบบจัดการโฆษณา Multi-Platform สำหรับ JLC Group
ออกแบบมาเพื่อจัดการ content และ campaigns บน TikTok, Facebook, Instagram
พร้อมระบบ Budget Optimization อัตโนมัติ

---

## 🏢 Business Context

**Company:** JLC Group (จุฬาเฮิร์บ)
**Industry:** E-commerce, Cosmetics, Health Products
**Users:** Marketing Team, Content Creators, Influencers

---

## 📋 Core Features

### 1. Content Management
- นำเข้า content จาก TikTok, Facebook, Instagram
- Spark Ad Authorization สำหรับ TikTok
- Content scoring (PFM Score)
- Content-Product mapping

### 2. Campaign Management
- สร้างและจัดการ campaigns
- Multi-platform targeting
- Ad group management
- Performance tracking

### 3. Budget Optimization
- Auto budget allocation
- ABX (Auto Budget eXecution)
- Daily budget planning
- ROI optimization

### 4. Analytics
- Ad performance daily
- Platform distribution
- Top performing content
- Spend tracking

### 5. Team Management
- Employees
- Influencers
- Content assignments

---

## 🗺️ Phases

### Phase 1: Foundation ✅
- Database schema design
- Core models (User, Content, Campaign, Ad)
- Authentication (JWT)
- Basic CRUD APIs

### Phase 2: Integration ✅
- TikTok Business API
- Facebook Marketing API
- Content sync
- Targeting templates

### Phase 3: Production 🔄 (Current)
- Production deployment
- PM2 integration
- Nginx reverse proxy
- SSL certificates

### Phase 4: Optimization (Planned)
- Budget optimization algorithms
- Scheduler tasks
- Performance tuning
- Monitoring & alerts

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12, FastAPI |
| Frontend | Jinja2, TailwindCSS, Alpine.js |
| Database | PostgreSQL 18 |
| ORM | SQLAlchemy 2.0 |
| Auth | JWT (python-jose) |
| Scheduler | APScheduler |
| HTTP Client | httpx |
| Process Manager | PM2 |
| Reverse Proxy | Nginx |

---

## 🗄️ Database

**Database:** `weboostx_dev_db`
**Host:** localhost:5432

### Key Tables
- `users` - System users
- `contents` - TikTok/FB/IG contents
- `campaigns` - Ad campaigns
- `ad_groups` - Campaign ad groups
- `ads` - Individual ads
- `ad_accounts` - Platform ad accounts
- `ad_performance_daily` - Daily performance metrics
- `budget_plans` - Budget planning
- `products` - Product catalog
- `employees` - Team members
- `influencers` - KOL/Influencers
- `spark_ad_auths` - TikTok Spark authorizations

---

## 🔗 API Integration

### TikTok Business API
- Content sync
- Campaign management
- Targeting options
- Performance data

### Facebook Marketing API
- Page content
- Ad management
- Audience targeting

---

## 📁 Folder Structure

```
D:\Server\apps\weboostx\
├── app/
│   ├── api/v1/           # FastAPI routers
│   │   ├── ads.py
│   │   ├── auth.py
│   │   ├── contents.py
│   │   ├── pages.py      # HTML pages
│   │   └── ...
│   ├── core/
│   │   ├── config.py     # Settings
│   │   ├── database.py   # DB connection
│   │   ├── deps.py       # Dependencies
│   │   └── security.py   # Auth helpers
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   ├── tasks/            # Background jobs
│   ├── templates/        # Jinja2 templates
│   └── static/           # CSS, JS, images
├── scripts/              # Utility scripts
├── docs/                 # Documentation
├── requirements.txt
├── .cursorrules
├── STATUS.md
├── PROJECT_CONTEXT.md
└── PROGRESS.md
```

---

## 🔒 Security

- JWT token authentication
- Password hashing (bcrypt)
- CORS middleware
- Rate limiting (planned)
- API key protection for external APIs

---

## 📊 Metrics

| Metric | Current Value |
|--------|--------------|
| Contents | 8,391 |
| Campaigns | 250 |
| Ad Accounts | 15 |
| Daily Ads | 11,000+ |

---

*WeBoostX 2.0 | JLC Group IT | 2026*
