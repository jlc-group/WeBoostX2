# 🗄️ Database-Only Media Storage Setup Guide

## 📋 ภาพรวม

คู่มือนี้จะช่วยให้คุณปรับปรุงระบบจาก Hybrid Storage (Database + File System) เป็น Database-Only Storage

## 🎯 ประโยชน์ของ Database-Only Storage

- ✅ **ความสม่ำเสมอ**: ไม่มีปัญหาไฟล์หาย
- ✅ **ความปลอดภัย**: ไฟล์อยู่ใน Database transaction
- ✅ **ง่ายต่อการจัดการ**: Backup/Restore ทุกอย่างที่เดียว
- ✅ **ไม่ต้องจัดการ File Permissions**

## ⚠️ ข้อควรระวัง

- 💾 **Database ขนาดใหญ่ขึ้น**: จาก 377MB metadata เป็น ~500-1000MB รวมไฟล์
- ⚡ **ประสิทธิภาพ**: การดึงรูปจาก DB ช้ากว่า static files เล็กน้อย
- 💰 **ค่าใช้จ่าย**: PostgreSQL storage อาจแพงกว่า file system

---

## 🚀 ขั้นตอนการติดตั้ง

### **Step 1: อัปเดต Database Schema**

```bash
# รัน SQL script เพื่อเพิ่ม columns สำหรับ binary data
psql -h localhost -U postgres -d facebook_data -f update_media_storage_schema.sql
```

### **Step 2: ติดตั้ง Dependencies**

```bash
# ติดตั้ง FastAPI สำหรับ Media API Server
pip install fastapi uvicorn python-multipart
```

### **Step 3: ทดสอบ Database Media Manager**

```bash
# ทดสอบการดาวน์โหลดและเก็บใน database
python database_media_manager.py
```

### **Step 4: Migration ไฟล์เก่า (Optional)**

```bash
# ดูว่าจะ migrate อะไรบ้าง (ไม่ทำจริง)
python migrate_to_database_storage.py --dry-run

# Migrate ไฟล์จาก media/ folder ไป database
python migrate_to_database_storage.py

# Migrate และลบไฟล์เก่า (ระวัง!)
python migrate_to_database_storage.py --cleanup
```

### **Step 5: เริ่ม Media API Server**

```bash
# เริ่ม API server สำหรับ serve media files
python media_api_server.py

# หรือใช้ uvicorn
uvicorn media_api_server:app --host 0.0.0.0 --port 8000
```

### **Step 6: ทดสอบระบบใหม่**

```bash
# ทดสอบ sync script ใหม่
python sync_facebook_complete.py --days-back 7

# ทดสอบ video sync
python sync_fb_video_posts_to_db.py --days-back 7
```

---

## 🔧 การใช้งาน

### **API Endpoints**

- `GET /media/{media_id}` - ดึงไฟล์ media
- `GET /media/{media_id}/info` - ดึงข้อมูล metadata
- `GET /stats` - ดูสถิติการใช้งาน
- `GET /health` - Health check

### **ตัวอย่างการใช้งาน**

```python
# ในระบบใหม่
from database_media_manager import DatabaseMediaManager

manager = DatabaseMediaManager()

# เก็บรูปภาพจาก URL
media_id = manager.store_media_from_url("https://example.com/image.jpg")

# ดึงไฟล์กลับมา
binary_data, content_type = manager.get_media_binary(media_id)

# ดูข้อมูล
info = manager.get_media_info(media_id)
```

### **ใน Dashboard/Frontend**

```html
<!-- ใช้ API endpoint แทน file path -->
<img
  src="http://localhost:8000/media/12345678-1234-1234-1234-123456789abc"
  alt="Facebook Post"
/>

<!-- แทนการใช้ -->
<img src="/media/fb_post_123456_abcdef.jpg" alt="Facebook Post" />
```

---

## 📊 การตรวจสอบ

### **ดูสถิติ Database**

```bash
# ผ่าน Python
python -c "from database_media_manager import DatabaseMediaManager; DatabaseMediaManager().get_storage_stats()"

# ผ่าน API
curl http://localhost:8000/stats
```

### **ตรวจสอบ API**

```bash
# Health check
curl http://localhost:8000/health

# ดูข้อมูล media
curl http://localhost:8000/media/12345678-1234-1234-1234-123456789abc/info

# ดาวน์โหลดไฟล์
curl -o test.jpg http://localhost:8000/media/12345678-1234-1234-1234-123456789abc
```

---

## 🔄 Rollback Plan

หากต้องการย้อนกลับไปใช้ระบบเก่า:

### **Step 1: เปลี่ยน Import กลับ**

```python
# ใน sync scripts
from facebook_media_manager import FacebookMediaManager  # ระบบเก่า
# แทน
from database_media_manager import DatabaseMediaManager  # ระบบใหม่
```

### **Step 2: เปลี่ยนการเรียกใช้ฟังก์ชัน**

```python
# ระบบเก่า
local_media_id = self.media_manager.download_image(url, category="attachments")

# ระบบใหม่
local_media_id = self.media_manager.store_media_from_url(url, category="attachments")
```

### **Step 3: Restore ไฟล์ (ถ้าได้ backup)**

```bash
# คืนไฟล์จาก backup
cp -r media_backup/* media/
```

---

## 🎯 Next Steps

1. **🧪 ทดสอบในระบบ Development ก่อน**
2. **📊 Monitor ประสิทธิภาพ Database**
3. **🔧 ปรับแต่ง Database settings สำหรับ large binary data**
4. **🌐 Deploy Media API Server ใน Production**
5. **📈 ติดตาม Database size growth**

---

## 📞 Support

หากพบปัญหาหรือต้องการความช่วยเหลือ:

- ตรวจสอบ logs ของ Media API Server
- ดู database logs สำหรับ performance issues
- ใช้ health check endpoints เพื่อ monitor ระบบ

---

## 📝 การเปรียบเทียบ

| ฟีเจอร์       | Hybrid Storage | Database-Only  |
| ------------- | -------------- | -------------- |
| ความสม่ำเสมอ  | ⚠️ มีไฟล์หาย   | ✅ สม่ำเสมอ    |
| ประสิทธิภาพ   | ✅ เร็ว        | ⚡ ช้าเล็กน้อย |
| การจัดการ     | ⚠️ ซับซ้อน     | ✅ ง่าย        |
| Backup        | ⚠️ แยกส่วน     | ✅ รวมเดียว    |
| Database Size | ✅ เล็ก        | 💾 ใหญ่ขึ้น    |

ระบบใหม่จะช่วยแก้ปัญหาไฟล์หายและทำให้การจัดการง่ายขึ้น! 🎉
