#!/usr/bin/env python3
"""
Media API Server for Database-Only Storage
Serves media files stored in PostgreSQL database

Features:
- REST API สำหรับดึงไฟล์ media จาก database
- รองรับ image และ video formats
- Proper MIME type headers
- Error handling และ caching headers
- Optional image resizing

Endpoints:
  GET /media/{media_id}           - ดึงไฟล์ต้นฉบับ
  GET /media/{media_id}/info      - ดึงข้อมูล metadata
  GET /health                     - Health check

Usage:
  python media_api_server.py
  # หรือ
  uvicorn media_api_server:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from typing import Optional, Dict

load_dotenv()

# Database Configuration - ใช้ค่าจริงแทน .env
DB_CONFIG = {
    'host': '13.215.197.134',
    'port': 5432,
    'database': 'social_media_db',
    'user': 'postgres',
    'password': 'AzCvBn2023!'
}

app = FastAPI(
    title="Facebook Media API",
    description="Enhanced API สำหรับดึงไฟล์ media จาก PostgreSQL database พร้อม source_post_id และ media_category support",
    version="2.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ปรับเป็น domain ที่ต้องการใน production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db_connection():
    """สร้าง database connection"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Facebook Media API",
        "version": "2.0.0",
        "status": "running",
        "description": "Enhanced API with source_post_id and media_category support",
        "endpoints": {
            "get_media": "/media/{media_id}",
            "get_media_info": "/media/{media_id}/info",
            "get_post_media": "/posts/{post_id}/media",
            "get_video_thumbnails": "/videos/{video_id}/thumbnails?quality=best",
            "search_media": "/media/search?source_type=&media_category=&source_post_id=&limit=50&offset=0",
            "get_categories": "/categories",
            "get_stats": "/stats",
            "health_check": "/health"
        },
        "new_features": [
            "source_post_id linking",
            "media_category classification", 
            "source_type tracking",
            "Enhanced video thumbnail support",
            "Multiple thumbnail quality options",
            "Thumbnail metadata storage",
            "Advanced search capabilities",
            "Enhanced statistics"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                "status": "healthy",
                "database": "connected",
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=503, detail="Database query failed")
            
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Health check failed: {e}")

@app.get("/media/{media_id}")
async def get_media(media_id: str):
    """
    ดึงไฟล์ media จาก database
    
    Args:
        media_id: UUID ของ media record
        
    Returns:
        Binary content ของไฟล์พร้อม proper headers
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT file_data, content_type, file_size, original_url, 
                       source_post_id, source_type, media_category
                FROM media_storage 
                WHERE id = %s AND is_stored_in_db = TRUE AND download_status = 'success'
            """, (media_id,))
            
            result = cursor.fetchone()
        conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="Media not found")
            
        file_data, content_type, file_size, original_url, source_post_id, source_type, media_category = result
        
        if not file_data:
            raise HTTPException(status_code=404, detail="Media binary data not found")
        
        # สร้าง response headers
        headers = {
            "Content-Type": content_type or "application/octet-stream",
            "Content-Length": str(len(file_data)),
            "Cache-Control": "public, max-age=31536000",  # Cache 1 year
            "ETag": f'"{media_id}"',
            "X-Original-URL": original_url or "",
            "X-Media-ID": media_id,
            "X-Source-Post-ID": source_post_id or "",
            "X-Source-Type": source_type or "",
            "X-Media-Category": media_category or ""
        }
        
        # สร้าง streaming response
        return Response(
            content=file_data,
            media_type=content_type or "application/octet-stream",
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving media: {e}")

@app.get("/media/{media_id}/info")
async def get_media_info(media_id: str) -> Dict:
    """
    ดึงข้อมูล metadata ของ media
    
    Args:
        media_id: UUID ของ media record
        
    Returns:
        Dictionary ของ metadata
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, original_url, content_type, file_size,
                       download_status, is_stored_in_db, downloaded_at,
                       created_at, updated_at, error_message,
                       source_post_id, source_type, media_category
                FROM media_storage 
                WHERE id = %s
            """, (media_id,))
            
            result = cursor.fetchone()
        conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="Media not found")
            
        (id, original_url, content_type, file_size, download_status, 
         is_stored_in_db, downloaded_at, created_at, updated_at, error_message,
         source_post_id, source_type, media_category) = result
        
        return {
            "id": id,
            "original_url": original_url,
            "content_type": content_type,
            "file_size": file_size,
            "download_status": download_status,
            "is_stored_in_db": is_stored_in_db,
            "downloaded_at": downloaded_at.isoformat() if downloaded_at else None,
            "created_at": created_at.isoformat() if created_at else None,
            "updated_at": updated_at.isoformat() if updated_at else None,
            "error_message": error_message,
            "source_post_id": source_post_id,
            "source_type": source_type,
            "media_category": media_category,
            "media_url": f"/media/{id}",
            "has_binary_data": is_stored_in_db and download_status == 'success'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving media info: {e}")

@app.get("/posts/{post_id}/media")
async def get_post_media(post_id: str):
    """
    ดึง media URLs สำหรับ post_id ที่กำหนด (รองรับทั้ง database และ file storage)
    
    Args:
        post_id: Facebook post ID
        
    Returns:
        List ของ media URLs พร้อม metadata
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id, 
                    original_url,
                    public_url,
                    is_stored_in_db,
                    download_status,
                    media_category,
                    content_type,
                    file_size
                FROM media_storage 
                WHERE source_post_id = %s 
                AND download_status = 'success'
                ORDER BY created_at DESC
            """, (post_id,))
            
            results = cursor.fetchall()
        conn.close()
        
        if not results:
            return {"post_id": post_id, "media": []}
        
        media_list = []
        for row in results:
            (id, original_url, public_url, is_stored_in_db, 
             download_status, media_category, content_type, file_size) = row
            
            # สร้าง URL ตาม storage type
            if is_stored_in_db:
                media_url = f"/media/{id}"
            elif public_url:
                media_url = public_url
            else:
                media_url = original_url  # fallback
            
            media_list.append({
                "id": id,
                "url": media_url,
                "original_url": original_url,
                "category": media_category,
                "content_type": content_type,
                "file_size": file_size,
                "storage_type": "database" if is_stored_in_db else "file"
            })
        
        return {
            "post_id": post_id,
            "media": media_list,
            "count": len(media_list)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving post media: {e}")

@app.get("/stats")
async def get_storage_stats():
    """ดึงสถิติการใช้งาน storage พร้อมข้อมูลใหม่"""
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # สถิติพื้นฐาน
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_records,
                    COUNT(CASE WHEN is_stored_in_db = TRUE THEN 1 END) as stored_in_db,
                    COUNT(CASE WHEN download_status = 'success' THEN 1 END) as successful_downloads,
                    COUNT(CASE WHEN download_status = 'failed' THEN 1 END) as failed_downloads,
                    COALESCE(SUM(CASE WHEN is_stored_in_db = TRUE THEN file_size END), 0) as total_db_size,
                    COALESCE(AVG(CASE WHEN is_stored_in_db = TRUE THEN file_size END), 0) as avg_file_size,
                    MIN(created_at) as oldest_record,
                    MAX(created_at) as newest_record
                FROM media_storage
            """)
            basic_stats = cursor.fetchone()
            
            # สถิติตาม media_category
            cursor.execute("""
                SELECT 
                    COALESCE(media_category, 'uncategorized') as category,
                    COUNT(*) as count,
                    COUNT(CASE WHEN download_status = 'success' THEN 1 END) as successful,
                    COALESCE(SUM(CASE WHEN download_status = 'success' THEN file_size END), 0) as total_size
                FROM media_storage
                GROUP BY media_category
                ORDER BY count DESC
            """)
            category_stats = cursor.fetchall()
            
            # สถิติตาม source_type
            cursor.execute("""
                SELECT 
                    COALESCE(source_type, 'unknown') as source_type,
                    COUNT(*) as count,
                    COUNT(CASE WHEN download_status = 'success' THEN 1 END) as successful,
                    COALESCE(SUM(CASE WHEN download_status = 'success' THEN file_size END), 0) as total_size
                FROM media_storage
                GROUP BY source_type
                ORDER BY count DESC
            """)
            source_type_stats = cursor.fetchall()
            
            # สถิติ posts ที่มี media
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT source_post_id) as posts_with_media,
                    COUNT(*) as total_media_files,
                    AVG(media_per_post) as avg_media_per_post
                FROM (
                    SELECT 
                        source_post_id,
                        COUNT(*) as media_per_post
                    FROM media_storage 
                    WHERE source_post_id IS NOT NULL
                    GROUP BY source_post_id
                ) post_counts
            """)
            post_stats = cursor.fetchone()
            
        conn.close()
        
        if basic_stats:
            (total, stored_db, success, failed, total_size, avg_size, oldest, newest) = basic_stats
            
            # แปลง category stats
            categories = {}
            for cat_stat in category_stats:
                categories[cat_stat[0]] = {
                    "count": cat_stat[1],
                    "successful": cat_stat[2],
                    "total_size_mb": round(cat_stat[3] / 1024 / 1024, 2),
                    "success_rate": round((cat_stat[2] / cat_stat[1] * 100), 2) if cat_stat[1] > 0 else 0
                }
            
            # แปลง source type stats
            source_types = {}
            for source_stat in source_type_stats:
                source_types[source_stat[0]] = {
                    "count": source_stat[1],
                    "successful": source_stat[2],
                    "total_size_mb": round(source_stat[3] / 1024 / 1024, 2),
                    "success_rate": round((source_stat[2] / source_stat[1] * 100), 2) if source_stat[1] > 0 else 0
                }
            
            return {
                "basic_stats": {
                    "total_records": total,
                    "stored_in_database": stored_db,
                    "successful_downloads": success,
                    "failed_downloads": failed,
                    "total_database_size_bytes": int(total_size),
                    "total_database_size_mb": round(total_size / 1024 / 1024, 2),
                    "average_file_size_bytes": int(avg_size),
                    "average_file_size_kb": round(avg_size / 1024, 2),
                    "success_rate_percent": round((success / total * 100), 2) if total > 0 else 0,
                    "oldest_record": oldest.isoformat() if oldest else None,
                    "newest_record": newest.isoformat() if newest else None
                },
                "post_stats": {
                    "posts_with_media": post_stats[0] if post_stats else 0,
                    "total_media_files": post_stats[1] if post_stats else 0,
                    "average_media_per_post": round(post_stats[2], 2) if post_stats and post_stats[2] else 0
                },
                "categories": categories,
                "source_types": source_types
            }
        else:
            return {"error": "No data found"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving stats: {e}")

@app.get("/videos/{video_id}/thumbnails")
async def get_video_thumbnails(video_id: str, quality: Optional[str] = "best"):
    """
    ดึง thumbnail URLs สำหรับ video โดยเฉพาะ - รองรับหลายคุณภาพ
    
    Args:
        video_id: Facebook video ID หรือ post ID
        quality: คุณภาพที่ต้องการ ('best', 'high', 'medium', 'low', 'all')
        
    Returns:
        List ของ thumbnail URLs พร้อม metadata
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    id, 
                    original_url,
                    public_url,
                    is_stored_in_db,
                    content_type,
                    file_size,
                    media_category,
                    metadata,
                    created_at
                FROM media_storage 
                WHERE source_post_id = %s 
                AND source_type = 'facebook_video'
                AND download_status = 'success'
                AND (media_category LIKE 'videos%' OR media_category = 'videos')
                ORDER BY 
                    CASE 
                        WHEN metadata->>'is_preferred' = 'true' THEN 1
                        ELSE 2
                    END,
                    (COALESCE(metadata->>'width', '0')::int * COALESCE(metadata->>'height', '0')::int) DESC
            """, (video_id,))
            
            results = cursor.fetchall()
        conn.close()
        
        if not results:
            raise HTTPException(status_code=404, detail="No thumbnails found for this video")
        
        thumbnails = []
        for row in results:
            media_id, original_url, public_url, is_stored_in_db, content_type, file_size, media_category, metadata_json, created_at = row
            
            # Parse metadata
            metadata = {}
            if metadata_json:
                try:
                    metadata = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                except:
                    pass
            
            # สร้าง URL สำหรับเข้าถึง
            if is_stored_in_db:
                thumbnail_url = f"http://localhost:8000/media/{media_id}"
            else:
                thumbnail_url = public_url or original_url
            
            thumbnail_info = {
                "id": media_id,
                "url": thumbnail_url,
                "original_url": original_url,
                "width": metadata.get('width'),
                "height": metadata.get('height'),
                "is_preferred": metadata.get('is_preferred', False),
                "quality": _get_quality_label(metadata.get('width', 0), metadata.get('height', 0)),
                "file_size": file_size,
                "content_type": content_type,
                "created_at": created_at.isoformat() if created_at else None
            }
            
            thumbnails.append(thumbnail_info)
        
        # Filter by quality if specified
        if quality != "all":
            thumbnails = _filter_by_quality(thumbnails, quality)
        
        return {
            "video_id": video_id,
            "total_thumbnails": len(thumbnails),
            "thumbnails": thumbnails,
            "best_thumbnail": thumbnails[0] if thumbnails else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving thumbnails: {e}")

def _get_quality_label(width: int, height: int) -> str:
    """กำหนด quality label ตามขนาด"""
    if not width or not height:
        return "unknown"
    
    pixels = width * height
    if pixels >= 1920 * 1080:
        return "high"
    elif pixels >= 1280 * 720:
        return "medium" 
    elif pixels >= 640 * 360:
        return "low"
    else:
        return "thumbnail"

def _filter_by_quality(thumbnails: list, quality: str) -> list:
    """Filter thumbnails ตาม quality ที่ต้องการ"""
    if quality == "best":
        return thumbnails[:1]  # Return only the best one
    elif quality == "high":
        return [t for t in thumbnails if t["quality"] in ["high", "medium"]]
    elif quality == "medium":
        return [t for t in thumbnails if t["quality"] == "medium"]
    elif quality == "low":
        return [t for t in thumbnails if t["quality"] in ["low", "thumbnail"]]
    else:
        return thumbnails

@app.get("/media/search")
async def search_media(
    source_type: Optional[str] = None,
    media_category: Optional[str] = None,
    source_post_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """
    ค้นหา media ตามเงื่อนไขต่างๆ
    
    Args:
        source_type: ประเภทของแหล่งที่มา (facebook_post, facebook_video)
        media_category: ประเภทของ media (videos, thumbnails, attachments)
        source_post_id: Facebook post ID
        limit: จำนวนผลลัพธ์สูงสุด (default: 50)
        offset: ข้าม records (default: 0)
        
    Returns:
        List ของ media records
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # สร้าง WHERE clause แบบ dynamic
            where_conditions = ["download_status = 'success'"]
            params = []
            
            if source_type:
                where_conditions.append("source_type = %s")
                params.append(source_type)
                
            if media_category:
                where_conditions.append("media_category = %s")
                params.append(media_category)
                
            if source_post_id:
                where_conditions.append("source_post_id = %s")
                params.append(source_post_id)
            
            where_clause = " AND ".join(where_conditions)
            params.extend([limit, offset])
            
            # Query หลัก
            cursor.execute(f"""
                SELECT 
                    id, original_url, content_type, file_size,
                    source_post_id, source_type, media_category,
                    is_stored_in_db, created_at, public_url
                FROM media_storage 
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, params)
            
            results = cursor.fetchall()
            
            # นับจำนวนทั้งหมด
            count_params = params[:-2]  # ไม่รวม limit และ offset
            cursor.execute(f"""
                SELECT COUNT(*) FROM media_storage WHERE {where_clause}
            """, count_params)
            
            total_count = cursor.fetchone()[0]
            
        conn.close()
        
        media_list = []
        for row in results:
            (id, original_url, content_type, file_size, source_post_id, 
             source_type, media_category, is_stored_in_db, created_at, public_url) = row
            
            # สร้าง URL ตาม storage type
            if is_stored_in_db:
                media_url = f"/media/{id}"
            elif public_url:
                media_url = public_url
            else:
                media_url = original_url
            
            media_list.append({
                "id": id,
                "url": media_url,
                "original_url": original_url,
                "content_type": content_type,
                "file_size": file_size,
                "source_post_id": source_post_id,
                "source_type": source_type,
                "media_category": media_category,
                "storage_type": "database" if is_stored_in_db else "file",
                "created_at": created_at.isoformat() if created_at else None
            })
        
        return {
            "results": media_list,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching media: {e}")

@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    """
    ดึงสถิติสำหรับ dashboard - รวมข้อมูล posts, videos, engagement
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # สถิติพื้นฐานจาก facebook_posts_performance
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_posts,
                    COUNT(CASE WHEN video_duration IS NOT NULL AND video_duration > 0 THEN 1 END) as total_videos,
                    COALESCE(SUM(likes + comments + shares), 0) as total_engagement,
                    COALESCE(AVG(video_views), 0) as avg_video_views,
                    COALESCE(SUM(reach), 0) as total_reach,
                    COALESCE(SUM(impressions), 0) as total_impressions
                FROM facebook_posts_performance
                WHERE created_time >= NOW() - INTERVAL '30 days'
            """)
            dashboard_stats = cursor.fetchone()
            
            # Top performing posts
            cursor.execute("""
                SELECT 
                    post_id,
                    message,
                    video_title,
                    (likes + comments + shares) as total_engagement,
                    video_views,
                    reach
                FROM facebook_posts_performance
                WHERE created_time >= NOW() - INTERVAL '30 days'
                ORDER BY (likes + comments + shares) DESC
                LIMIT 5
            """)
            top_posts = cursor.fetchall()
        
        conn.close()
        
        if dashboard_stats:
            total_posts, total_videos, total_engagement, avg_video_views, total_reach, total_impressions = dashboard_stats
            
            # Format top performing posts
            top_performing_posts = []
            for post in top_posts:
                top_performing_posts.append({
                    "post_id": post[0],
                    "message": post[1],
                    "video_title": post[2],
                    "total_engagement": int(post[3]) if post[3] else 0,
                    "video_views": int(post[4]) if post[4] else 0,
                    "reach": int(post[5]) if post[5] else 0
                })
            
            return {
                "total_posts": int(total_posts) if total_posts else 0,
                "total_videos": int(total_videos) if total_videos else 0,
                "total_engagement": int(total_engagement) if total_engagement else 0,
                "avg_video_views": int(avg_video_views) if avg_video_views else 0,
                "total_reach": int(total_reach) if total_reach else 0,
                "total_impressions": int(total_impressions) if total_impressions else 0,
                "top_performing_posts": top_performing_posts
            }
        else:
            return {
                "total_posts": 0,
                "total_videos": 0,
                "total_engagement": 0,
                "avg_video_views": 0,
                "total_reach": 0,
                "total_impressions": 0,
                "top_performing_posts": []
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving dashboard stats: {e}")

@app.get("/categories")
async def get_categories():
    """
    ดึงรายการ categories และ source types ที่มีอยู่
    
    Returns:
        Dictionary ของ categories และ source types พร้อมจำนวน
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # ดึง media categories
            cursor.execute("""
                SELECT 
                    COALESCE(media_category, 'uncategorized') as category,
                    COUNT(*) as count
                FROM media_storage
                WHERE download_status = 'success'
                GROUP BY media_category
                ORDER BY count DESC
            """)
            categories = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]
            
            # ดึง source types
            cursor.execute("""
                SELECT 
                    COALESCE(source_type, 'unknown') as source_type,
                    COUNT(*) as count
                FROM media_storage
                WHERE download_status = 'success'
                GROUP BY source_type
                ORDER BY count DESC
            """)
            source_types = [{"name": row[0], "count": row[1]} for row in cursor.fetchall()]
            
        conn.close()
        
        return {
            "media_categories": categories,
            "source_types": source_types
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving categories: {e}")

if __name__ == "__main__":
    import uvicorn
    
    # Fix Windows Unicode encoding
    import sys
    if sys.platform.startswith('win'):
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    print("🚀 Starting Facebook Media API Server v2.0...")
    print("📊 Enhanced Database-Only Media Storage")
    print("🌐 API Endpoints:")
    print("   GET /media/{media_id}         - Get media file")
    print("   GET /media/{media_id}/info    - Get media info")
    print("   GET /posts/{post_id}/media    - Get all media for a post")
    print("   GET /media/search             - Search media by filters")
    print("   GET /categories               - Get available categories")
    print("   GET /stats                    - Get enhanced storage stats")
    print("   GET /health                   - Health check")
    print("🆕 New Features:")
    print("   • source_post_id linking")
    print("   • media_category classification")
    print("   • source_type tracking")
    print("   • Advanced search & filtering")
    print("=" * 60)
    
    uvicorn.run(
        "media_api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )