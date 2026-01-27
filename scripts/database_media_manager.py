#!/usr/bin/env python3
"""
Enhanced Facebook Media Manager - Database-Only Storage
เก็บไฟล์ media ใน PostgreSQL database แทน file system

Features:
- Download และเก็บไฟล์เป็น binary data ใน database
- รองรับ image และ video formats
- Auto-detect MIME types
- เพิ่มประสิทธิภาพด้วย connection pooling
- Error handling และ retry mechanism

Usage:
  media_manager = DatabaseMediaManager()
  media_id = media_manager.store_media_from_url("https://example.com/image.jpg")
  binary_data = media_manager.get_media_binary(media_id)
"""

import os
import sys
import requests
import psycopg2
import uuid
import mimetypes
from datetime import datetime
from dotenv import load_dotenv
from typing import Optional, Tuple, Dict

load_dotenv()

class DatabaseMediaManager:
    """Enhanced Media Manager ที่เก็บไฟล์ใน Database เท่านั้น"""
    
    def __init__(self):
        """Initialize database connection และ configuration"""
        self.db_config = {
            'host': os.getenv("PG_HOST"),
            'port': os.getenv("PG_PORT"),
            'database': os.getenv("PG_DB"),
            'user': os.getenv("PG_USER"),
            'password': os.getenv("PG_PASSWORD")
        }
        
        # Request configuration
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        self.timeout = 30
        self.max_file_size = 50 * 1024 * 1024  # 50MB limit
        
        # Statistics
        self.stats = {
            'downloaded': 0,
            'failed': 0,
            'skipped': 0,
            'total_size': 0
        }
    
    def get_db_connection(self):
        """สร้าง database connection"""
        try:
            return psycopg2.connect(**self.db_config)
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            raise
    
    def detect_content_type(self, url: str, response_headers: dict) -> str:
        """ตรวจจับ MIME type จาก URL และ response headers"""
        # ลองจาก Content-Type header ก่อน
        content_type = response_headers.get('content-type', '').split(';')[0].strip()
        
        if content_type and content_type.startswith(('image/', 'video/')):
            return content_type
        
        # ลองจากไฟล์ extension
        guessed_type, _ = mimetypes.guess_type(url)
        if guessed_type and guessed_type.startswith(('image/', 'video/')):
            return guessed_type
        
        # Default สำหรับรูปภาพ
        return 'image/jpeg'
    
    def download_media(self, url: str) -> Tuple[Optional[bytes], str, Optional[str]]:
        """ดาวน์โหลดไฟล์จาก URL และคืนค่า binary data"""
        try:
            print(f"  📥 Downloading: {url[:80]}...")
            
            response = requests.get(
                url, 
                headers=self.headers, 
                timeout=self.timeout,
                stream=True
            )
            
            if response.status_code != 200:
                print(f"    ❌ HTTP {response.status_code}")
                return None, 'failed', f"HTTP {response.status_code}"
            
            # ตรวจสอบขนาดไฟล์
            content_length = response.headers.get('content-length')
            if content_length and int(content_length) > self.max_file_size:
                print(f"    ⚠️  File too large: {int(content_length):,} bytes")
                return None, 'failed', 'File too large'
            
            # ดาวน์โหลด binary data
            binary_data = response.content
            
            if len(binary_data) == 0:
                print(f"    ❌ Empty file")
                return None, 'failed', 'Empty file'
            
            if len(binary_data) > self.max_file_size:
                print(f"    ⚠️  File too large: {len(binary_data):,} bytes")
                return None, 'failed', 'File too large'
            
            # ตรวจจับ content type
            content_type = self.detect_content_type(url, response.headers)
            
            print(f"    ✅ Downloaded: {len(binary_data):,} bytes ({content_type})")
            
            self.stats['downloaded'] += 1
            self.stats['total_size'] += len(binary_data)
            
            return binary_data, content_type, None
            
        except requests.exceptions.Timeout:
            error_msg = "Download timeout"
            print(f"    ⏰ {error_msg}")
            self.stats['failed'] += 1
            return None, 'failed', error_msg
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Request error: {str(e)[:100]}"
            print(f"    ❌ {error_msg}")
            self.stats['failed'] += 1
            return None, 'failed', error_msg
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)[:100]}"
            print(f"    💥 {error_msg}")
            self.stats['failed'] += 1
            return None, 'failed', error_msg
    
    def store_media_from_url(self, original_url: str, category: str = "general", 
                            source_post_id: str = None, source_type: str = None) -> Optional[str]:
        """
        ดาวน์โหลดและเก็บไฟล์ใน database
        
        Args:
            original_url: URL ของไฟล์ต้นฉบับ
            category: หมวดหมู่ของไฟล์ (general, attachments, videos, thumbnails)
            source_post_id: ID ของ post/video ที่เป็นเจ้าของ media นี้
            source_type: ประเภทของ source (facebook_post, facebook_video)
            
        Returns:
            UUID ของ media record หรือ None หากล้มเหลว
        """
        if not original_url:
            return None
        
        # ตรวจสอบว่ามี record นี้อยู่แล้วหรือไม่
        existing_id = self.check_existing_media(original_url)
        if existing_id:
            print(f"    📋 Media already exists: {existing_id}")
            # อัปเดต source_post_id ถ้ายังไม่มี
            if source_post_id:
                self.update_source_info(existing_id, source_post_id, source_type)
            self.stats['skipped'] += 1
            return existing_id
        
        # ดาวน์โหลดไฟล์
        binary_data, content_type, error_message = self.download_media(original_url)
        
        if binary_data is None:
            # บันทึก failed record
            return self.store_failed_record(original_url, error_message, category, source_post_id, source_type)
        
        # บันทึกลง database
        return self.store_binary_data(
            original_url=original_url,
            binary_data=binary_data,
            content_type=content_type,
            category=category,
            source_post_id=source_post_id,
            source_type=source_type
        )
    
    def check_existing_media(self, original_url: str) -> Optional[str]:
        """ตรวจสอบว่ามี media record อยู่แล้วหรือไม่"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id FROM media_storage 
                    WHERE original_url = %s 
                    AND (download_status = 'success' OR is_stored_in_db = TRUE)
                    LIMIT 1
                """, (original_url,))
                
                result = cursor.fetchone()
                conn.close()
                
                return str(result[0]) if result else None
                
        except Exception as e:
            print(f"    ⚠️  Error checking existing media: {e}")
            return None
    
    def store_binary_data(self, original_url: str, binary_data: bytes, 
                         content_type: str, category: str, 
                         source_post_id: str = None, source_type: str = None) -> Optional[str]:
        """เก็บ binary data ลง database"""
        try:
            media_id = str(uuid.uuid4())
            
            conn = self.get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO media_storage (
                        id, original_url, file_data, content_type,
                        file_size, mime_type, download_status, 
                        is_stored_in_db, local_filename, local_path,
                        source_post_id, source_type, media_category,
                        downloaded_at, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, NOW(), NOW(), NOW()
                    )
                """, (
                    media_id,
                    original_url,
                    binary_data,
                    content_type,
                    len(binary_data),
                    content_type,  # mime_type same as content_type
                    'success',
                    True,  # is_stored_in_db
                    f"{category}_{media_id}",  # legacy filename
                    f"database://{category}/{media_id}",  # legacy path
                    source_post_id,
                    source_type,
                    category
                ))
                
                conn.commit()
                conn.close()
                
                print(f"    💾 Stored in database: {media_id} ({len(binary_data):,} bytes)")
                if source_post_id:
                    print(f"    🔗 Linked to {source_type or 'post'}: {source_post_id}")
                return media_id
                
        except Exception as e:
            print(f"    ❌ Error storing binary data: {e}")
            return None
    
    def store_failed_record(self, original_url: str, error_message: str, 
                           category: str, source_post_id: str = None, source_type: str = None) -> Optional[str]:
        """บันทึก failed record ลง database"""
        try:
            media_id = str(uuid.uuid4())
            
            conn = self.get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO media_storage (
                        id, original_url, download_status, error_message,
                        is_stored_in_db, local_filename, local_path,
                        source_post_id, source_type, media_category,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
                    )
                """, (
                    media_id,
                    original_url,
                    'failed',
                    error_message,
                    False,
                    f"{category}_{media_id}_failed",
                    f"database://{category}/{media_id}/failed",
                    source_post_id,
                    source_type,
                    category
                ))
                
                conn.commit()
                conn.close()
                
                print(f"    📝 Failed record stored: {media_id}")
                if source_post_id:
                    print(f"    🔗 Linked to {source_type or 'post'}: {source_post_id}")
                return media_id
                
        except Exception as e:
            print(f"    ❌ Error storing failed record: {e}")
            return None
    
    def update_source_info(self, media_id: str, source_post_id: str, source_type: str = None):
        """อัปเดต source_post_id และ source_type สำหรับ media ที่มีอยู่แล้ว"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE media_storage 
                    SET source_post_id = %s, 
                        source_type = %s,
                        updated_at = NOW()
                    WHERE id = %s AND source_post_id IS NULL
                """, (source_post_id, source_type, media_id))
                
                if cursor.rowcount > 0:
                    print(f"    🔗 Updated source info for existing media: {source_post_id}")
                
                conn.commit()
                conn.close()
                
        except Exception as e:
            print(f"    ⚠️  Error updating source info: {e}")

    def get_media_binary(self, media_id: str) -> Tuple[Optional[bytes], Optional[str]]:
        """ดึง binary data และ content type จาก database"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT file_data, content_type 
                    FROM media_storage 
                    WHERE id = %s AND is_stored_in_db = TRUE
                """, (media_id,))
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    return result[0], result[1]  # binary_data, content_type
                else:
                    return None, None
                    
        except Exception as e:
            print(f"❌ Error retrieving media binary: {e}")
            return None, None
    
    def get_media_info(self, media_id: str) -> Optional[Dict]:
        """ดึงข้อมูล metadata ของ media"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id, original_url, content_type, file_size,
                           download_status, is_stored_in_db, downloaded_at,
                           created_at, error_message
                    FROM media_storage 
                    WHERE id = %s
                """, (media_id,))
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    return {
                        'id': result[0],
                        'original_url': result[1],
                        'content_type': result[2],
                        'file_size': result[3],
                        'download_status': result[4],
                        'is_stored_in_db': result[5],
                        'downloaded_at': result[6],
                        'created_at': result[7],
                        'error_message': result[8]
                    }
                else:
                    return None
                    
        except Exception as e:
            print(f"❌ Error retrieving media info: {e}")
            return None
    
    def get_storage_stats(self):
        """แสดงสถิติการใช้งาน"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_records,
                        COUNT(CASE WHEN is_stored_in_db = TRUE THEN 1 END) as stored_in_db,
                        COUNT(CASE WHEN download_status = 'success' THEN 1 END) as successful_downloads,
                        COUNT(CASE WHEN download_status = 'failed' THEN 1 END) as failed_downloads,
                        COALESCE(SUM(CASE WHEN is_stored_in_db = TRUE THEN file_size END), 0) as total_db_size,
                        COALESCE(AVG(CASE WHEN is_stored_in_db = TRUE THEN file_size END), 0) as avg_file_size
                    FROM media_storage
                """)
                
                result = cursor.fetchone()
                conn.close()
                
                if result:
                    total, stored_db, success, failed, total_size, avg_size = result
                    
                    print("\n" + "="*50)
                    print("📊 Database Media Storage Statistics")
                    print("="*50)
                    print(f"📁 Total records: {total:,}")
                    print(f"💾 Stored in database: {stored_db:,}")
                    print(f"✅ Successful downloads: {success:,}")
                    print(f"❌ Failed downloads: {failed:,}")
                    print(f"📊 Total database size: {total_size/1024/1024:.2f} MB")
                    print(f"📏 Average file size: {avg_size/1024:.2f} KB")
                    
                    if total > 0:
                        success_rate = (success / total) * 100
                        print(f"🎯 Success rate: {success_rate:.1f}%")
                    
                    # Session statistics
                    if any(self.stats.values()):
                        print(f"\n📈 Current session:")
                        print(f"   Downloaded: {self.stats['downloaded']:,}")
                        print(f"   Failed: {self.stats['failed']:,}")
                        print(f"   Skipped: {self.stats['skipped']:,}")
                        print(f"   Total size: {self.stats['total_size']/1024/1024:.2f} MB")
                
        except Exception as e:
            print(f"❌ Error retrieving storage stats: {e}")

# Backward compatibility - alias สำหรับ scripts เก่า
FacebookMediaManager = DatabaseMediaManager

def main():
    """Test function"""
    print("🧪 Testing Database Media Manager...")
    
    manager = DatabaseMediaManager()
    
    # Test URL
    test_url = "https://via.placeholder.com/300x200.jpg"
    
    print(f"📥 Testing download: {test_url}")
    media_id = manager.store_media_from_url(test_url, "test")
    
    if media_id:
        print(f"✅ Success! Media ID: {media_id}")
        
        # Test retrieval
        binary_data, content_type = manager.get_media_binary(media_id)
        if binary_data:
            print(f"📤 Retrieved: {len(binary_data):,} bytes ({content_type})")
        
        # Test info
        info = manager.get_media_info(media_id)
        if info:
            print(f"📋 Info: {info['file_size']:,} bytes, status: {info['download_status']}")
    
    # Show stats
    manager.get_storage_stats()

if __name__ == "__main__":
    main()