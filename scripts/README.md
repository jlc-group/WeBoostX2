# Facebook Data Sync & Database Management

This repository contains scripts for Facebook API data synchronization and PostgreSQL database management following Facebook Graph API v23.0 documentation.

## 📁 Project Structure

### 🔄 Root Folder - Facebook API Sync Scripts

Scripts for syncing data **FROM** Facebook API **TO** database:

- **`sync_facebook_complete.py`** - Complete Facebook posts sync (non-video posts)
- **`sync_fb_video_posts_to_db.py`** - Facebook video posts and insights sync
- **`sync_facebook_ads_insights_complete.py`** - Facebook ads insights sync (production-ready)
- **`sync_fb_ads_account_to_db.py`** - Facebook ad accounts sync
- **`sync_fb_campaigns_adsets_to_db_fixed.py`** - Campaigns and adsets sync
- **`facebook_media_manager.py`** - Media file management utility
- **`dashboard_utility.py`** - Dashboard data utility functions

### 🗄️ DB_work Folder - Database Management Scripts

Scripts for database operations, schema management, and testing:

- **`create_tables.py`** - Create new database tables
- **`db_health_check.py`** - Comprehensive database health check
- **`check_db_schema.py`** - Schema validation and checking
- **`analyze_query.py`** - SQL query analysis and optimization
- **`debug_sql.py`** - SQL debugging utilities
- **`dashboard_diagnostic.py`** - Dashboard database diagnostics
- **`test_dashboard_method.py`** - Database method testing
- **`test_fixed_dashboard.py`** - Database fix testing

### 📊 Dashboard & Analytics

- **`dashboard_preview.py`** - Dashboard preview utility
- **`dashboard_usage_example.py`** - Dashboard usage examples
- **`collect_dashboard_data.py`** - Dashboard data collection
- **`prepare_dashboard_data.py`** - Dashboard data preparation

### 📁 Other Folders

- **`media/`** - Downloaded Facebook media files
- **`static/`** - Static web assets
- **`templates/`** - HTML templates

## Database Schema

The scripts work with these PostgreSQL tables:

### facebook_posts

```sql
CREATE TABLE facebook_posts (
    id VARCHAR PRIMARY KEY,
    page_id VARCHAR,
    message TEXT,
    story TEXT,
    type VARCHAR,
    permalink_url VARCHAR,
    picture_url VARCHAR,
    full_picture_url VARCHAR,
    video_url VARCHAR,
    source VARCHAR,
    status_type VARCHAR,
    created_time TIMESTAMP,
    updated_time TIMESTAMP,
    is_published BOOLEAN,
    is_hidden BOOLEAN,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### facebook_video_posts

```sql
CREATE TABLE facebook_video_posts (
    id VARCHAR PRIMARY KEY,
    page_id VARCHAR,
    title VARCHAR,
    description TEXT,
    embed_html TEXT,
    format VARCHAR,
    length DECIMAL,
    picture VARCHAR,
    source VARCHAR,
    status VARCHAR,
    created_time TIMESTAMP,
    updated_time TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### facebook_video_post_insights

```sql
CREATE TABLE facebook_video_post_insights (
    id SERIAL PRIMARY KEY,
    post_id VARCHAR,
    metric_name VARCHAR,
    metric_value INTEGER,
    period VARCHAR,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(post_id, metric_name, period)
);
```

### facebook_pages

```sql
CREATE TABLE facebook_pages (
    id VARCHAR PRIMARY KEY,
    name VARCHAR,
    username VARCHAR,
    category VARCHAR,
    about TEXT,
    website VARCHAR,
    phone VARCHAR,
    email VARCHAR,
    fan_count INTEGER,
    talking_about_count INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Setup Instructions

1. **Clone and Install Dependencies**

   ```bash
   pip install flask flask-cors psycopg2-binary python-dotenv requests
   ```

2. **Configure Environment**

   ```bash
   cp .env.example .env
   # Edit .env with your Facebook API tokens and database credentials
   ```

3. **Run Scripts**

   ```bash
   # Sync video posts
   python sync_fb_video_posts_to_db.py

   # Sync image/text posts
   python sync_fb_posts_images_to_db.py

   # Start API server
   python facebook_dashboard_api.py
   ```

## Facebook API Compliance

All scripts follow Facebook Graph API v23.0 documentation:

- **Rate Limiting**: Built-in delays between API calls
- **Error Handling**: Proper error handling for API failures
- **Field Selection**: Only requests necessary fields
- **Pagination**: Handles API pagination correctly
- **Token Management**: Supports multiple page tokens

## Features

### Video Posts Sync (`sync_fb_video_posts_to_db.py`)

- ✅ Fetches video posts from `/videos` and `/posts` endpoints
- ✅ Collects video insights (views, engagement metrics)
- ✅ Handles video metadata (duration, format, thumbnails)
- ✅ Database upsert with conflict resolution

### Image/Text Posts Sync (`sync_fb_posts_images_to_db.py`)

- ✅ Fetches non-video posts (photos, status, links)
- ✅ Excludes video posts (handled separately)
- ✅ Processes post metadata and engagement
- ✅ Database upsert with conflict resolution

### API Dashboard (`facebook_dashboard_api.py`)

- ✅ REST API endpoints for all data types
- ✅ Interactive web dashboard
- ✅ Real-time data visualization
- ✅ CORS support for frontend integration

## Data Flow

1. **Facebook API** → Scripts fetch data using Graph API v23.0
2. **Data Processing** → Scripts clean and validate data
3. **PostgreSQL** → Data stored in normalized tables
4. **API Server** → Flask provides REST endpoints
5. **Dashboard** → Web interface displays data

## Error Handling

- API rate limiting with automatic delays
- Database transaction rollback on errors
- Detailed logging for debugging
- Graceful handling of missing data
- Network timeout and retry logic

## Monitoring

Each script provides detailed logging:

- ✅ Success/failure counts
- ⏱️ Processing duration
- 📊 Data statistics
- ❌ Error details

## Support

For issues or questions, check:

1. Facebook Graph API v23.0 documentation
2. PostgreSQL connection settings
3. Environment variable configuration
4. Script logs for error details
