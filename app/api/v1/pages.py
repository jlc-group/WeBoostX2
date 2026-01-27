"""
Page routes - serve HTML templates
"""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
from starlette.responses import Response

from app.core.deps import get_db, get_optional_user
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from app.models.enums import AdAccountStatus, UserStatus, UserRole
from app.models import Content, Campaign, AdGroup, Ad
from app.services.sso_service import sso_service

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
        "request": request,
        "sso_enabled": settings.SSO_ENABLED,
    })


# ============================================
# SSO Authentication Routes
# ============================================

@router.get("/auth/sso")
async def sso_redirect(request: Request):
    """Redirect to JLC SSO for login"""
    if not settings.SSO_ENABLED:
        return RedirectResponse(url="/login?error=sso_disabled")
    
    # Generate state for CSRF protection
    state = sso_service.generate_state()
    
    # Store state in session (using cookies for simplicity)
    auth_url = sso_service.get_authorization_url(state)
    
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        max_age=600,  # 10 minutes
        samesite="lax"
    )
    
    return response


@router.get("/auth/callback")
async def sso_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Handle OAuth2 callback from JLC SSO"""
    
    # Check for errors
    if error:
        return RedirectResponse(url=f"/login?error={error}")
    
    if not code:
        return RedirectResponse(url="/login?error=no_code")
    
    # Verify state
    stored_state = request.cookies.get("oauth_state")
    if not state or state != stored_state:
        return RedirectResponse(url="/login?error=invalid_state")
    
    # Exchange code for token
    token_data = await sso_service.exchange_code_for_token(code)
    if not token_data:
        return RedirectResponse(url="/login?error=token_failed")
    
    access_token = token_data.get("access_token")
    if not access_token:
        return RedirectResponse(url="/login?error=no_token")
    
    # Get user info from SSO
    user_info = await sso_service.get_user_info(access_token)
    if not user_info:
        return RedirectResponse(url="/login?error=userinfo_failed")
    
    # Find or create user
    email = user_info.get("email")
    if not email:
        return RedirectResponse(url="/login?error=no_email")
    
    user = db.query(User).filter(User.email == email).first()
    
    if not user:
        # Auto-create user from SSO
        from app.core.security import get_password_hash
        import secrets
        
        user = User(
            email=email,
            password_hash=get_password_hash(secrets.token_urlsafe(32)),  # Random password
            first_name=user_info.get("given_name", ""),
            last_name=user_info.get("family_name", ""),
            display_name=user_info.get("name", email.split("@")[0]),
            role=UserRole.ADMIN if user_info.get("is_admin") else UserRole.VIEWER,
            status=UserStatus.ACTIVE,  # Auto-approved from SSO
            sso_id=user_info.get("sub"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update SSO ID if not set
        if not user.sso_id:
            user.sso_id = user_info.get("sub")
            db.commit()
    
    # Create local JWT tokens
    local_access_token = create_access_token(
        subject=user.id,
        additional_claims={"role": user.role.value}
    )
    local_refresh_token = create_refresh_token(subject=user.id)
    
    # Redirect to dashboard with tokens
    # We'll set tokens via JavaScript on the client side
    response = RedirectResponse(url="/dashboard")
    response.delete_cookie("oauth_state")
    
    # Set tokens in cookies for the frontend to pick up
    response.set_cookie(
        key="sso_access_token",
        value=local_access_token,
        httponly=False,  # Allow JS access
        max_age=86400,
        samesite="lax"
    )
    response.set_cookie(
        key="sso_refresh_token", 
        value=local_refresh_token,
        httponly=False,
        max_age=604800,
        samesite="lax"
    )
    
    return response


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


@router.get("/fb-dashboard", response_class=HTMLResponse)
async def fb_dashboard_page(request: Request):
    """Facebook Dashboard - Legacy DB"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("fb_dashboard.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "fb_dashboard"
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
        },
        "special_mode": None
    })


@router.get("/contents/tiktok/best-each-product", response_class=HTMLResponse)
async def contents_tiktok_best_each_product_page(request: Request, db: Session = Depends(get_db)):
    """TikTok Best Content Each Product page"""
    from app.models.enums import Platform
    from sqlalchemy import func
    
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
        },
        "special_mode": "best_each_product"
    })


@router.get("/contents/facebook", response_class=HTMLResponse)
async def contents_facebook_page(request: Request, db: Session = Depends(get_db)):
    """Facebook Contents page - reads from legacy facebook_posts_performance"""
    # Import legacy mapper for reading from localhost:5433/postgres
    try:
        from app.services.facebook.fb_legacy_mapper import get_legacy_mapper
        mapper = get_legacy_mapper()
        summary = mapper.get_dashboard_summary()
        
        total_contents = summary.get('posts_count', 0)
        avg_fb_score = 0  # Legacy DB doesn't have fb_score, we use pfm_score
        
        # Get average pfm_score from legacy DB
        try:
            avg_result = mapper.db.query_one("""
                SELECT AVG(pfm_score) as avg_score 
                FROM facebook_posts_performance 
                WHERE pfm_score > 0
            """)
            avg_fb_score = float(avg_result['avg_score']) if avg_result and avg_result['avg_score'] else 0
        except Exception:
            avg_fb_score = 0
            
    except Exception as e:
        print(f"[contents_facebook_page] Error loading from legacy DB: {e}")
        total_contents = 0
        avg_fb_score = 0
    
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
async def campaigns_page(
    request: Request,
    db: Session = Depends(get_db)
):
    """Campaigns page - แสดงรายการ Campaigns ทั้งหมด"""
    from app.models import Campaign, AdAccount
    from app.models.enums import Platform
    from sqlalchemy import func
    
    # Get all campaigns with stats
    campaigns = db.query(Campaign).filter(
        Campaign.deleted_at.is_(None)
    ).order_by(Campaign.created_at.desc()).all()
    
    # Get advertisers for filter
    advertisers = db.query(AdAccount).filter(
        AdAccount.platform == Platform.TIKTOK,
        AdAccount.is_active == True
    ).all()
    
    # Calculate stats
    total_campaigns = len(campaigns)
    active_campaigns = len([c for c in campaigns if c.status == 'active'])
    
    # Group by objective
    objective_counts = {}
    for c in campaigns:
        obj = c.objective or 'unknown'
        objective_counts[obj] = objective_counts.get(obj, 0) + 1
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    # Convert campaigns to dicts for JSON serialization
    campaigns_data = [
        {
            "id": c.id,
            "name": c.name,
            "external_campaign_id": c.external_campaign_id,
            "objective": c.objective,
            "status": c.status,
            "daily_budget": float(c.daily_budget) if c.daily_budget else None,
            "lifetime_budget": float(c.lifetime_budget) if c.lifetime_budget else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in campaigns
    ]
    
    return templates.TemplateResponse("campaigns/index.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "campaigns",
        "campaigns": campaigns_data,
        "advertisers": advertisers,
        "stats": {
            "total": total_campaigns,
            "active": active_campaigns,
            "objective_counts": objective_counts,
        }
    })


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


# ============================================
# Content Routes (Master Data)
# ============================================

@router.get("/master/contents/tiktok", response_class=HTMLResponse)
async def master_contents_tiktok_page(request: Request, db: Session = Depends(get_db)):
    """TikTok Contents page under Master Data menu"""
    from app.models.enums import Platform
    from sqlalchemy import func
    
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
        "active_page": "master_contents_tiktok",
        "stats": {
            "total": total_contents,
            "avg_pfm": float(avg_pfm)
        }
    })


# ============================================
# Ad Creation Pages
# ============================================

@router.get("/ads/create", response_class=HTMLResponse)
async def ad_create_page(
    request: Request,
    content_id: int,
    ad_type: Optional[str] = None,  # 'ACE' or 'ABX'
    targeting_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Unified Ad Creation page - supports both ACE and ABX"""
    from app.models.enums import Platform
    from app.models import AdAccount
    from app.models.platform import TargetingTemplate
    
    # Get content
    content = db.query(Content).filter(Content.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    # Get advertisers
    advertisers = db.query(AdAccount).filter(
        AdAccount.platform == Platform.TIKTOK,
        AdAccount.is_active == True
    ).all()
    
    # Get targeting template if provided
    targeting = None
    if targeting_id:
        targeting = db.query(TargetingTemplate).filter(
            TargetingTemplate.id == int(targeting_id)
        ).first()
    
    # Get all targeting templates for selection
    targeting_templates = db.query(TargetingTemplate).filter(
        TargetingTemplate.is_active == True
    ).all()
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    # Filter targeting templates by content's preferred_targeting_ids
    preferred_ids = content.preferred_targeting_ids or []
    if preferred_ids:
        # Only show targeting templates that content has marked as preferred
        filtered_templates = [t for t in targeting_templates if t.id in preferred_ids]
    else:
        # No preferred targeting = must set targeting first
        filtered_templates = []
    
    return templates.TemplateResponse("ads/create.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "contents_tiktok",
        "content": content,
        "advertisers": advertisers,
        "targeting": targeting,
        "targeting_id": targeting_id,
        "targeting_templates": filtered_templates,
        "all_targeting_templates": targeting_templates,  # For ABX modal
        "products": ",".join(content.product_codes or []),
        "ad_type": ad_type,  # Pre-select type if provided
        "has_preferred_targeting": len(preferred_ids) > 0,
    })


@router.get("/ads/ace/create", response_class=HTMLResponse)
async def ace_create_page(
    request: Request,
    content_id: int,
    targeting_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """ACE Ad Creation page - redirects to unified page"""
    from app.models.enums import Platform
    from app.models import AdAccount
    from app.models.platform import TargetingTemplate
    
    # Get content
    content = db.query(Content).filter(Content.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    # Get advertisers
    advertisers = db.query(AdAccount).filter(
        AdAccount.platform == Platform.TIKTOK,
        AdAccount.is_active == True
    ).all()
    
    # Get targeting template if provided
    targeting = None
    if targeting_id:
        targeting = db.query(TargetingTemplate).filter(
            TargetingTemplate.id == int(targeting_id)
        ).first()
    
    # Get all targeting templates for selection
    targeting_templates = db.query(TargetingTemplate).filter(
        TargetingTemplate.is_active == True
    ).all()
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("ads/ace_create.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "contents_tiktok",
        "content": content,
        "advertisers": advertisers,
        "targeting": targeting,
        "targeting_id": targeting_id,
        "targeting_templates": targeting_templates,
        "products": ",".join(content.product_codes or []),
    })


@router.get("/ads/abx/create", response_class=HTMLResponse)
async def abx_create_page(
    request: Request,
    content_id: int,
    targeting_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """ABX Ad Creation page - add content to existing adgroup"""
    from app.models.enums import Platform
    from app.models import AdAccount
    from app.models.platform import TargetingTemplate
    
    # Get content
    content = db.query(Content).filter(Content.id == content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    
    # Get advertisers
    advertisers = db.query(AdAccount).filter(
        AdAccount.platform == Platform.TIKTOK,
        AdAccount.is_active == True
    ).all()
    
    # Get targeting template if provided
    targeting = None
    if targeting_id:
        targeting = db.query(TargetingTemplate).filter(
            TargetingTemplate.id == int(targeting_id)
        ).first()
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("ads/abx_create.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "contents_tiktok",
        "content": content,
        "advertisers": advertisers,
        "targeting": targeting,
        "targeting_id": targeting_id,
        "products": ",".join(content.product_codes or []),
    })


# ============================================
# Spark Auth Pages (Influencer Auth Codes)
# ============================================

@router.get("/spark-auth", response_class=HTMLResponse)
async def spark_auth_list_page(request: Request, db: Session = Depends(get_db)):
    """Spark Auth Codes list page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("spark_auth/list.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "spark_auth",
    })


@router.get("/spark-auth/import", response_class=HTMLResponse)
async def spark_auth_import_page(request: Request, db: Session = Depends(get_db)):
    """Spark Auth Codes import page"""
    
    class MockUser:
        first_name = "Admin"
        full_name = "Admin WeBoostX"
        role = type('obj', (object,), {'value': 'admin'})()
    
    return templates.TemplateResponse("spark_auth/import.html", {
        "request": request,
        "current_user": MockUser(),
        "active_page": "spark_auth_import",
    })