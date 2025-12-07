# Content, Targeting & Budget Allocation Flow

## 📋 Overview

เอกสารนี้สรุปแนวทางการจัดการ Content, Targeting และ Budget Allocation ในระบบ WeBoostX 2.0

---

## 🎯 หลักการสำคัญ

### 1. แยกความรับผิดชอบชัดเจน

| Level | ความรับผิดชอบ | ใครกำหนด |
|-------|--------------|----------|
| **Content** | กำหนด "เหมาะกับ targeting ไหน" | Content Creator |
| **Ad Creation** | เลือก Objective + Targeting (จากที่กำหนดไว้) | Ad Manager |
| **Budget Plan** | กำหนด % allocation ต่อ Style/Targeting | Budget Manager |

### 2. Content Level ไม่มี % Allocation

- Content แค่บอกว่า "ยิงได้กับ targeting ไหนบ้าง" (multi-select)
- ไม่ต้องกำหนด % ที่ Content level
- % Allocation ทำที่ Budget Plan level

### 3. บังคับ Targeting ก่อนสร้าง Ad

- ถ้า Content ไม่มี `preferred_targeting_ids` → ไม่ให้สร้าง Ad
- ต้องไปกำหนด targeting ที่หน้า Edit Content ก่อน

---

## 📝 Content Model

### Fields ที่เกี่ยวข้อง

```python
class Content(BaseModel):
    # Products
    product_codes = Column(JSON, nullable=True)  # ["S1", "S2", "J3"]
    
    # Targeting (ใหม่)
    preferred_targeting_ids = Column(JSON, nullable=True)  # [1, 3, 5] - TargetingTemplate IDs
    
    # Legacy (เดิม - อาจจะ deprecate)
    targeting_template_id = Column(Integer, ForeignKey("targeting_templates.id"), nullable=True)
    targeting_override = Column(JSON, nullable=True)
```

### ความหมาย

- `preferred_targeting_ids`: List ของ TargetingTemplate IDs ที่ Content นี้เหมาะสม
- ถ้า Content ไม่มี `preferred_targeting_ids` → ถือว่ายังไม่พร้อมสร้าง Ad

---

## 🔄 Flow ต่างๆ

### 1. Edit Content Flow

```
┌─────────────────────────────────────────────────────────┐
│  แก้ไข Content                                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Products: [J3] [A1] [D1]          ← Multi-select      │
│                                                         │
│  Preferred Targeting:               ← Multi-select     │
│  [✓] F_RETAIL_18_54                                    │
│  [✓] MF_OILCONTROL_18_44                               │
│  [ ] MF_ORAL_35_99                                     │
│  [ ] MF_ACNE_18_34                                     │
│                                                         │
│  Content Type: [SALE ▼]                                │
│  Content Status: [Ready ▼]                             │
│  Content Source: [Influencer ▼]                        │
│  Expire Date: [____-__-__]                             │
│                                                         │
│                            [ยกเลิก] [บันทึก]            │
└─────────────────────────────────────────────────────────┘
```

### 2. Create Ad Flow (ACE)

```
Step 1: เลือก Objective
        → VV / RCH / TRF / CVN

Step 2: เลือก Ad Type
        → ACE (1:1) / ABX (1:N)

Step 3: เลือก Advertiser
        → [Dropdown]

Step 4: เลือก Campaign
        → Filter ตาม Objective ที่เลือก

Step 5: เลือก Targeting
        → แสดงเฉพาะ targeting ที่ Content กำหนดไว้
        → ถ้า Content ไม่มี preferred_targeting_ids → ไม่ให้สร้าง (แสดง error)

Step 6: ตั้งชื่อ + สร้าง
```

### 3. Create ABX Adgroups Flow (Product Group Level)

```
หน้า Product Groups → ปุ่ม "ABX"
        ↓
┌─────────────────────────────────────────────────────────┐
│  Auto Create ABX Adgroups                               │
├─────────────────────────────────────────────────────────┤
│  Step 1: เลือก Objective (VV/RCH/TRF/CVN)              │
│  Step 2: เลือก Advertiser                               │
│  Step 3: เลือก Campaign                                 │
│  Step 4: เลือก Targeting Templates (multi-select)       │
│  Step 5: เลือก Content Styles (SALE/ECOM/REVIEW/...)   │
│  Step 6: จำนวน AdGroup ต่อ Style                        │
│  Step 7: Budget ต่อ AdGroup                             │
│                                                         │
│  → Preview → สร้าง                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 💰 Budget Allocation

### ABX Budget Flow

```
Product Group
    │
    ├── Total Budget (จาก Budget Plan)
    │
    ├── Content Style Allocation (%)
    │   ├── SALE: 60%
    │   ├── ECOM: 30%
    │   └── BRANDING: 10%
    │
    └── กระจายให้ Adgroups ตาม Style
        ├── [S2]_ABX_VV_(F_RETAIL)_SALE#01 → Budget X
        ├── [S2]_ABX_VV_(F_RETAIL)_SALE#02 → Budget X
        └── [S2]_ABX_VV_(F_RETAIL)_ECOM#01 → Budget Y
```

**หมายเหตุ**: ABX ไม่ใช้ % targeting ของ Content โดยตรง

### ACE Budget Flow

```
Product Group
    │
    ├── Total Budget (จาก Budget Plan)
    │
    ├── หาร/กระจายให้ Contents ที่ active
    │
    └── แต่ละ Content อาจมีหลาย Ad (หลาย targeting)
        ├── Content A + F_RETAIL → Adgroup 1 → Budget
        └── Content A + MF_OILCONTROL → Adgroup 2 → Budget
```

**Targeting % Allocation สำหรับ ACE**:
- ทำที่ Budget Plan level (ไม่ใช่ Content level)
- กำหนดว่า Product Group นี้จะจัดสรรงบให้แต่ละ targeting กี่ %

---

## 📐 Naming Convention

### Campaign
```
[Products]_<OBJ>_BOOSTX_<Date>
เช่น: [J3]_VV_BOOSTX_2025-12-06
```

### AdGroup
```
[Products]_<STRUCT>_<OBJ>_(<Targeting>)_<Style>#<Num>
เช่น: [J3]_ABX_VV_(F_RETAIL_18_54)_SALE#01
```

### Ad
```
[Products]_<STRUCT>_<OBJ>_(<Targeting>)_<ItemID>
เช่น: [J3]_ABX_VV_(F_RETAIL_18_54)_7579992882990615826
```

### Objective Codes
| Code | TikTok Objective | Billing |
|------|-----------------|---------|
| VV | VIDEO_VIEWS | CPV |
| RCH | REACH | CPM |
| TRF | TRAFFIC | CPC |
| CVN | CONVERSIONS | OCPM |

---

## 🗄️ Database Schema

### TargetingTemplate
```sql
CREATE TABLE targeting_templates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,      -- e.g. "F_RETAIL_18_54"
    description TEXT,
    settings JSON,                    -- TikTok targeting settings
    is_active BOOLEAN DEFAULT TRUE
);
```

### Content (updated fields)
```sql
-- เพิ่ม field ใหม่
preferred_targeting_ids JSON;  -- [1, 3, 5]
```

---

## 📅 Implementation Status

- [x] ObjectiveCode enum + mapping
- [x] NamingService with objective code
- [x] Create Ad page with objective selection
- [x] Auto Create ABX Adgroups API
- [ ] Content model - add `preferred_targeting_ids`
- [ ] Edit Content modal - Products multi-select
- [ ] Edit Content modal - Targeting multi-select
- [ ] Create Ad - enforce targeting requirement
- [ ] Budget Allocation for ACE (future)
- [ ] Budget Allocation for ABX (future)

---

## 📝 Notes

1. **ระบบเก่า vs ใหม่**:
   - เก่า: Content มี `targeting_details` พร้อม % allocation
   - ใหม่: Content มี `preferred_targeting_ids` (แค่ list, ไม่มี %)

2. **Migration**:
   - ถ้ามี content เก่าที่มี `targeting_details` → อาจต้อง migrate เป็น `preferred_targeting_ids`

3. **Backward Compatibility**:
   - `targeting_template_id` (single) ยังคงใช้ได้
   - `preferred_targeting_ids` (multi) เป็น option ใหม่

