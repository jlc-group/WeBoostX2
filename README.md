# 🚀 WeBoostX 2.0

Multi-Platform Ad Management System สำหรับ TikTok และ Facebook/Instagram

## 📋 Features

- **Multi-Platform Content Management** - จัดการ content จาก TikTok, Facebook, Instagram
- **Ad Automation** - ACE (Content-based) และ ABX (Adgroup-based) automation
- **Unified Scoring** - PFM Score, FB Score, และ Unified Content Impact Score
- **Budget Optimization** - ปรับงบประมาณอัตโนมัติตาม performance
- **Role-Based Access** - Admin, Ad Manager, Content Creator, Viewer

## 🏗️ Tech Stack

- **Backend**: Python 3.10+, FastAPI
- **Database**: PostgreSQL
- **ORM**: SQLAlchemy 2.0
- **Auth**: JWT (python-jose)
- **Scheduler**: APScheduler
- **API Clients**: httpx, aiohttp

## 📁 Project Structure

```
WeBoostX2/
├── app/
│   ├── api/              # API routes
│   │   └── v1/           # API version 1
│   ├── core/             # Core modules (config, security, database)
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   └── tasks/            # Background tasks & scheduler
├── scripts/              # Utility scripts
├── requirements.txt
├── run.py                # Application entry point
└── README.md
```

## 🚀 Quick Start

### 1. Setup Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Create `.env` file:

```env
# Database
POSTGRES_USER=postgres
POSTGRES_PWD=your_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=weboostx
DATABASE_URL=postgresql://postgres:your_password@localhost:5432/weboostx

# Security
SECRET_KEY=your-secret-key

# Debug
DEBUG=true
```

### 3. Initialize Database

```bash
python scripts/init_db.py
```

### 4. Run Application

```bash
python run.py
```

Application will be available at: http://localhost:8000

- API Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 👥 User Roles

| Role | Description | Permissions |
|------|-------------|-------------|
| **Admin** | ผู้ดูแลระบบ | Full access ทุกฟีเจอร์ |
| **Ad Manager** | ผู้จัดการโฆษณา | จัดการ ads, budgets, optimization |
| **Content Creator** | ผู้สร้างคอนเทนต์ | จัดการ content, ดู performance |
| **Viewer** | ผู้ดู (ผู้บริหาร) | View-only, ดู reports |

## 📊 Database Models

### Core Models
- `User` - ผู้ใช้งานระบบ
- `AdAccount` - บัญชีโฆษณา (TikTok/Facebook)
- `Content` - Content จากทุก platform
- `Campaign` / `AdGroup` / `Ad` - โครงสร้างโฆษณา

### Budget Models
- `BudgetPlan` - แผนงบประมาณ
- `BudgetAllocation` - การจัดสรรงบ
- `DailyBudget` - งบรายวัน

### ABX Models
- `ABXAdgroup` - Adgroup สำหรับ ABX automation

## ⏰ Scheduled Tasks

| Task | Interval | Description |
|------|----------|-------------|
| Content Sync | 60 min | Sync content จากทุก platform |
| Ad Sync | 30 min | Sync ads และ performance |
| Score Calculation | 30 min | คำนวณ PFM และ Unified Score |
| Budget Optimization | 2-3 hours | ปรับงบอัตโนมัติ |
| Saversure Sync | Daily 6 AM | Sync ข้อมูล scan |
| Offline Sales Sync | Weekly Mon 7 AM | Sync ยอดขาย offline |

## 🔐 API Authentication

ใช้ JWT Bearer Token:

```bash
# Login
POST /api/v1/auth/login
{
  "email": "admin@weboostx.com",
  "password": "admin123"
}

# Use token
Authorization: Bearer <access_token>
```

## 📝 License

Private - Internal Use Only

