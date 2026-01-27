# Facebook Media Storage Solution

## 🎯 วัตถุประสงค์

แก้ปัญหา Facebook CDN links ที่หมดอายุ ทำให้ dashboard สามารถแสดงรูปภาพได้ตลอดเวลาแม้ในอนาคต

## 🗄️ Database Schema ที่เพิ่มเติม

### 1. `media_storage` Table (ใหม่)

```sql
CREATE TABLE media_storage (
    id UUID PRIMARY KEY,
    original_url TEXT NOT NULL,           -- URL เดิมจาก Facebook
    local_filename TEXT NOT NULL,         -- ชื่อไฟล์ที่เก็บไว้
    local_path TEXT NOT NULL,             -- path เต็มของไฟล์
    public_url TEXT,                      -- URL สำหรับ web server
    file_size BIGINT,                     -- ขนาดไฟล์ (bytes)
    mime_type TEXT,                       -- image/jpeg, image/png
    width INTEGER,                        -- ความกว้างรูป
    height INTEGER,                       -- ความสูงรูป
    download_status TEXT DEFAULT 'pending', -- pending, success, failed
    error_message TEXT,                   -- error หากดาวน์โหลดไม่สำเร็จ
    downloaded_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Columns เพิ่มเติม

**facebook_posts:**

- `local_picture_id` UUID → อ้างอิง media_storage
- `local_full_picture_id` UUID → อ้างอิง media_storage

**facebook_post_attachments:**

- `local_media_id` UUID → อ้างอิง media_storage
- `local_thumbnail_id` UUID → อ้างอิง media_storage

**facebook_video_posts:**

- `local_picture_id` UUID → อ้างอิง media_storage

## 🚀 Components ที่สร้าง

### 1. `facebook_media_manager.py`

- **FacebookMediaManager Class**
- ดาวน์โหลดรูปภาพจาก Facebook CDN
- เก็บไว้ใน local storage (`media/facebook/`)
- บันทึกข้อมูลลง `media_storage` table
- จัดการ error และ retry logic

### 2. `sync_facebook_complete.py` (ปรับปรุง)

- เพิ่ม Media Manager integration
- ดาวน์โหลดรูป attachments อัตโนมัติ
- อัปเดต database ด้วย local media IDs
- แสดงสถิติ storage หลัง sync

### 3. `dashboard_utility.py`

- **DashboardDataProvider Class**
- ดึงข้อมูลโพสต์พร้อม local image URLs
- เลือก URL ที่ดีที่สุด (local → original)
- สร้างข้อมูลสำหรับ dashboard

### 4. `setup_media_storage.py`

- สร้าง database schema
- เพิ่ม columns ที่จำเป็น
- สร้าง indexes และ triggers

## 📁 File Structure

```
media/
└── facebook/
    ├── posts/       # รูปภาพหลักของโพสต์
    ├── attachments/ # ไฟล์แนบ
    └── thumbnails/  # รูปย่อ
```

## 🔄 Workflow

### 1. Sync Process:

```
Facebook API → Download Images → Local Storage → Database → Dashboard
```

### 2. Dashboard Usage:

```python
from dashboard_utility import DashboardDataProvider

provider = DashboardDataProvider()

# ดึงโพสต์พร้อมรูปภาพ
posts = provider.get_posts_with_media(limit=20)

for post in posts:
    image_url = post['display_image_url']  # local หรือ original
    has_local = post['has_local_image']    # True/False
```

## 📊 URL Priority Logic

สำหรับการแสดงรูปใน dashboard:

1. **local_picture_url** (ความปลอดภัยสูงสุด)
2. **local_full_picture_url**
3. **original_picture_url** (Facebook CDN)
4. **original_full_picture_url**

## ⚙️ การใช้งาน

### 1. Setup Database:

```bash
python setup_media_storage.py
```

### 2. Install Dependencies:

```bash
pip install Pillow
```

### 3. Run Sync (ดาวน์โหลดรูปอัตโนมัติ):

```bash
python sync_facebook_complete.py
```

### 4. Check Storage Stats:

```bash
python facebook_media_manager.py
```

### 5. Test Dashboard Data:

```bash
python dashboard_utility.py
```

## 🎯 ผลประโยชน์

### ✅ ข้อดี:

- **รูปภาพแสดงได้ตลอดเวลา** (ไม่ขึ้นกับ Facebook CDN)
- **Performance ดี** (serve จาก local server)
- **Backup อัตโนมัติ** (รูปไม่หายแม้ Facebook ลบโพสต์)
- **Flexible** (สามารถใช้ original URL หากจำเป็น)

### 📈 สถิติตัวอย่าง:

- **Posts**: 3,111 total, 0 with local images (ยังไม่ sync)
- **Attachments**: 5,600 total, 0 with local media (ยังไม่ sync)
- **Media Storage**: 0 files, 0.0 MB (พร้อมใช้งาน)

## 🔧 Web Server Configuration

สำหรับการ serve รูปภาพใน production:

### Nginx Example:

```nginx
location /media/facebook/ {
    alias /path/to/your/project/media/facebook/;
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

### Flask Example:

```python
from flask import Flask, send_from_directory

@app.route('/media/facebook/<path:filename>')
def serve_media(filename):
    return send_from_directory('media/facebook', filename)
```

## 🛡️ Security Notes:

- รูปภาพจะถูกเก็บใน `media/facebook/` directory
- URL pattern: `/media/facebook/{category}/{filename}`
- ตรวจสอบ file types (เฉพาะ image/\*)
- จำกัดขนาดไฟล์ (default: 10MB)

## 🎉 Ready for Dashboard!

ตอนนี้ database พร้อมสำหรับการสร้าง dashboard ที่แสดงรูปภาพได้อย่างเสถียร และไม่ต้องกังวลเรื่องรูปหายใน Facebook CDN!
