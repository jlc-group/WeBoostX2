"""
Enums for database models
"""
import enum


class UserRole(str, enum.Enum):
    """User roles for access control"""
    ADMIN = "admin"              # Full system access
    AD_MANAGER = "ad_manager"    # Manage ads, budgets, optimization
    CONTENT_CREATOR = "content_creator"  # Manage content, view performance
    VIEWER = "viewer"            # View-only access (executives/reports)


class UserStatus(str, enum.Enum):
    """User account status"""
    PENDING = "pending"      # Waiting for approval
    ACTIVE = "active"        # Active user
    INACTIVE = "inactive"    # Deactivated
    SUSPENDED = "suspended"  # Temporarily suspended


class Platform(str, enum.Enum):
    """Supported advertising platforms"""
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"


class ContentType(str, enum.Enum):
    """Content type classification"""
    SALE = "sale"           # Sales-focused content
    REVIEW = "review"       # Product review
    BRANDING = "branding"   # Brand awareness
    ECOM = "ecom"           # E-commerce focused
    OTHER = "other"


class ContentSource(str, enum.Enum):
    """Content source/origin"""
    INFLUENCER = "influencer"
    PAGE = "page"           # Official page content
    STAFF = "staff"         # Internal staff created
    UGC = "ugc"             # User generated content


class ContentStatus(str, enum.Enum):
    """Content status in the system"""
    READY = "ready"         # Ready for ads
    TEST_AD = "test_ad"     # Being tested
    ACTIVE_AD = "active_ad" # Active in ads
    PAUSED = "paused"       # Paused
    EXPIRED = "expired"     # Expired
    DELETED = "deleted"     # Soft deleted


class AdAccountStatus(str, enum.Enum):
    """Ad account status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class CampaignObjective(str, enum.Enum):
    """Campaign objectives (unified across platforms)"""
    # TikTok objectives
    REACH = "reach"
    VIDEO_VIEWS = "video_views"
    TRAFFIC = "traffic"
    CONVERSIONS = "conversions"
    APP_INSTALL = "app_install"
    LEAD_GENERATION = "lead_generation"
    REACH_FREQUENCY = "reach_frequency"  # R&F
    GMV_MAX = "gmv_max"  # TikTok Shop GMV
    
    # Facebook/Meta objectives
    AWARENESS = "awareness"
    ENGAGEMENT = "engagement"
    LEADS = "leads"
    SALES = "sales"


class OptimizationGoal(str, enum.Enum):
    """Optimization goals for ad delivery"""
    # Common goals
    IMPRESSIONS = "impressions"
    REACH = "reach"
    VIDEO_VIEW = "video_view"
    THRUPLAY = "thruplay"
    LINK_CLICK = "link_click"
    LANDING_PAGE_VIEW = "landing_page_view"
    
    # Conversion goals
    CONVERSION = "conversion"
    ADD_TO_CART = "add_to_cart"
    PURCHASE = "purchase"
    VALUE = "value"  # ROAS optimization
    
    # Lead & App goals
    LEAD = "lead"
    APP_INSTALL = "app_install"


class AdStatus(str, enum.Enum):
    """Ad/Adgroup/Campaign status"""
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"
    PENDING = "pending"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class BudgetType(str, enum.Enum):
    """Budget type"""
    DAILY = "daily"
    LIFETIME = "lifetime"


class AllocationType(str, enum.Enum):
    """Budget allocation type (ACE vs ABX)"""
    ACE = "ace"     # Content-based allocation
    ABX = "abx"     # Adgroup-based allocation
    MANUAL = "manual"  # Manual allocation

