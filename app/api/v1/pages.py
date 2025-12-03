"""
Page routes - serve HTML templates
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.core.deps import get_db, get_optional_user
from app.models.user import User
from app.models import Content, Campaign, AdGroup, Ad

router = APIRouter(tags=["Pages"])

# Setup Jinja2 templates
templates = Jinja2Templates(directory="app/templates")


def get_current_user_from_cookie(request: Request, db: Session) -> Optional[User]:
    """Get user from session/cookie (for page routes)"""
    # For now, we'll check localStorage token via JavaScript
    # In production, you might want to use HTTP-only cookies
    return None


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page - redirect to login or dashboard"""
    return RedirectResponse(url="/login")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("auth/login.html", {
        "request": request
    })


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Register page"""
    return templates.TemplateResponse("auth/register.html", {
        "request": request
    })


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Dashboard page"""
    
    # Get stats
    total_contents = db.query(Content).filter(Content.deleted_at.is_(None)).count()
    active_campaigns = db.query(Campaign).filter(Campaign.status == 'active').count()
    
    # Calculate average PFM
    from sqlalchemy import func
    avg_pfm_result = db.query(func.avg(Content.pfm_score)).filter(
        Content.pfm_score.isnot(None)
    ).scalar()
    avg_pfm = float(avg_pfm_result) if avg_pfm_result else 0.0
    
    # Get top contents
    top_contents = db.query(Content).filter(
        Content.deleted_at.is_(None),
        Content.pfm_score.isnot(None)
    ).order_by(Content.pfm_score.desc()).limit(5).all()
    
    # Mock data for charts (replace with real data)
    chart_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    chart_spend = [12500, 15000, 13200, 18500, 16800, 14200, 19500]
    chart_impressions = [45000, 52000, 48000, 62000, 58000, 51000, 68000]
    platform_data = [45, 35, 20]  # TikTok, Facebook, Instagram
    
    # Mock recent activities
    recent_activities = [
        {
            "title": "Budget Optimization Completed",
            "description": "Auto-adjusted 15 adgroups",
            "time": "5 min ago",
            "color": "green",
            "icon": "M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
        },
        {
            "title": "New Content Synced",
            "description": "12 new TikTok videos imported",
            "time": "1 hour ago",
            "color": "blue",
            "icon": "M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
        },
        {
            "title": "Campaign Created",
            "description": "Summer Sale 2024 campaign",
            "time": "3 hours ago",
            "color": "purple",
            "icon": "M12 6v6m0 0v6m0-6h6m-6 0H6"
        }
    ]
    
    # Mock user for template
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "dashboard",
        "stats": {
            "today_spend": 125000,
            "total_contents": total_contents,
            "active_campaigns": active_campaigns,
            "avg_pfm": avg_pfm
        },
        "top_contents": top_contents,
        "recent_activities": recent_activities,
        "chart_labels": chart_labels,
        "chart_spend": chart_spend,
        "chart_impressions": chart_impressions,
        "platform_data": platform_data
    })


@router.get("/contents", response_class=HTMLResponse)
async def contents_page(request: Request, db: Session = Depends(get_db)):
    """Contents list page (all platforms)"""
    
    # Mock user for template
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("contents/list.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "contents"
    })


@router.get("/contents/tiktok", response_class=HTMLResponse)
async def contents_tiktok_page(request: Request, db: Session = Depends(get_db)):
    """TikTok Contents page"""
    from app.models.enums import Platform
    from sqlalchemy import func
    
    # Get TikTok specific stats
    total_contents = db.query(Content).filter(
        Content.platform == Platform.TIKTOK,
        Content.deleted_at.is_(None)
    ).count()
    
    avg_pfm = db.query(func.avg(Content.pfm_score)).filter(
        Content.platform == Platform.TIKTOK,
        Content.pfm_score.isnot(None),
        Content.deleted_at.is_(None)
    ).scalar() or 0
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("contents/tiktok.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "contents_tiktok",
        "stats": {
            "total": total_contents,
            "avg_pfm": float(avg_pfm)
        }
    })


@router.get("/contents/facebook", response_class=HTMLResponse)
async def contents_facebook_page(request: Request, db: Session = Depends(get_db)):
    """Facebook Contents page"""
    from app.models.enums import Platform
    from sqlalchemy import func
    
    total_contents = db.query(Content).filter(
        Content.platform == Platform.FACEBOOK,
        Content.deleted_at.is_(None)
    ).count()
    
    avg_fb_score = db.query(func.avg(Content.fb_score)).filter(
        Content.platform == Platform.FACEBOOK,
        Content.fb_score.isnot(None),
        Content.deleted_at.is_(None)
    ).scalar() or 0
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("contents/facebook.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "contents_facebook",
        "stats": {
            "total": total_contents,
            "avg_score": float(avg_fb_score)
        }
    })


@router.get("/contents/instagram", response_class=HTMLResponse)
async def contents_instagram_page(request: Request, db: Session = Depends(get_db)):
    """Instagram Contents page"""
    from app.models.enums import Platform
    from sqlalchemy import func
    
    total_contents = db.query(Content).filter(
        Content.platform == Platform.INSTAGRAM,
        Content.deleted_at.is_(None)
    ).count()
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("contents/instagram.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "contents_instagram",
        "stats": {
            "total": total_contents
        }
    })


@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_page(request: Request):
    """Campaigns page"""
    # TODO: Create campaigns template
    return RedirectResponse(url="/dashboard")


@router.get("/budgets", response_class=HTMLResponse)
async def budgets_page(request: Request):
    """Budgets page"""
    # TODO: Create budgets template
    return RedirectResponse(url="/dashboard")


@router.get("/products", response_class=HTMLResponse)
async def products_page(request: Request):
    """Products page"""
    # TODO: Create products template
    return RedirectResponse(url="/dashboard")


@router.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    """Analytics page"""
    # TODO: Create analytics template
    return RedirectResponse(url="/dashboard")


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request, db: Session = Depends(get_db)):
    """Tasks / Jobs status page"""

    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "tasks/index.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "tasks",
        },
    )


@router.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request, db: Session = Depends(get_db)):
    """Admin users management page"""
    
    # Mock user for now (later will use real auth)
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "admin_users",
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, db: Session = Depends(get_db)):
    """Settings page - platform & ad account settings"""
    
    # Temporary mock user until real auth integration
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/index.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "settings",
        },
    )


@router.get("/settings/employees", response_class=HTMLResponse)
async def settings_employees_page(request: Request, db: Session = Depends(get_db)):
    """Employees management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/employees.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "settings_employees",
        },
    )


@router.get("/settings/influencers", response_class=HTMLResponse)
async def settings_influencers_page(request: Request, db: Session = Depends(get_db)):
    """Influencers management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/influencers.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "settings_influencers",
        },
    )


@router.get("/settings/content-types", response_class=HTMLResponse)
async def settings_content_types_page(request: Request, db: Session = Depends(get_db)):
    """Content Types management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/content_types.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "settings_content_types",
        },
    )


@router.get("/settings/targeting", response_class=HTMLResponse)
async def settings_targeting_page(request: Request, db: Session = Depends(get_db)):
    """Targeting Templates management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/targeting.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "settings_targeting",
        },
    )


@router.get("/settings/products", response_class=HTMLResponse)
async def settings_products_page(request: Request, db: Session = Depends(get_db)):
    """Products management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/products.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "settings_products",
        },
    )


@router.get("/settings/product-groups", response_class=HTMLResponse)
async def settings_product_groups_page(request: Request, db: Session = Depends(get_db)):
    """Product Groups management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/product_groups.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "settings_product_groups",
        },
    )


# ============================================
# Master Data Routes (Marketing)
# ============================================

@router.get("/master/products", response_class=HTMLResponse)
async def master_products_page(request: Request, db: Session = Depends(get_db)):
    """Products management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/products.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "master_products",
        },
    )


@router.get("/master/product-groups", response_class=HTMLResponse)
async def master_product_groups_page(request: Request, db: Session = Depends(get_db)):
    """Product Groups management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/product_groups.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "master_product_groups",
        },
    )


@router.get("/master/targeting", response_class=HTMLResponse)
async def master_targeting_page(request: Request, db: Session = Depends(get_db)):
    """Targeting Templates management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/targeting.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "master_targeting",
        },
    )


# ============================================
# Team Routes (Marketing)
# ============================================

@router.get("/team/employees", response_class=HTMLResponse)
async def team_employees_page(request: Request, db: Session = Depends(get_db)):
    """Employees management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/employees.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "team_employees",
        },
    )


@router.get("/team/influencers", response_class=HTMLResponse)
async def team_influencers_page(request: Request, db: Session = Depends(get_db)):
    """Influencers management page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/influencers.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "team_influencers",
        },
    )


# ============================================
# Admin Routes
# ============================================

@router.get("/admin/content-types", response_class=HTMLResponse)
async def admin_content_types_page(request: Request, db: Session = Depends(get_db)):
    """Content Types management page (Admin only)"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type("obj", (object,), {"value": "admin"})()

    return templates.TemplateResponse(
        "settings/content_types.html",
        {
            "request": request,
            "current_user": MockUser(),
            "active_page": "admin_content_types",
        },
    )


# ============================================
# Legacy Redirects (Backward Compatibility)
# ============================================

@router.get("/platforms/tiktok", response_class=HTMLResponse)
async def tiktok_page(request: Request):
    """TikTok platform page - redirect to contents"""
    return RedirectResponse(url="/contents/tiktok")


@router.get("/platforms/facebook", response_class=HTMLResponse)
async def facebook_page(request: Request):
    """Facebook platform page - redirect to contents"""
    return RedirectResponse(url="/contents/facebook")

