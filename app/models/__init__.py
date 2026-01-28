"""
Database models for WeBoostX 2.0
"""
# ABX models
from app.models.abx import ABXAdgroup, ABXBudgetLog
from app.models.ad_performance_daily import AdPerformanceDaily
from app.models.base import Base, BaseModel, SoftDeleteMixin, TimestampMixin

# Budget models
from app.models.budget import (
    BudgetAllocation,
    BudgetOptimizationLog,
    BudgetPlan,
    DailyBudget,
)

# Campaign/Ad models
from app.models.campaign import Ad, AdGroup, AdPerformanceHistory, Campaign

# Content models
from app.models.content import Content, ContentScoreHistory, ContentStaffAllocation

# Employee/Influencer models
from app.models.employee import ContentCreatorAssignment, Employee, Influencer
from app.models.enums import (
    AdAccountStatus,
    AdStatus,
    AllocationType,
    BudgetType,
    CampaignObjective,
    ContentSource,
    ContentStaffRole,
    ContentStatus,
    ContentType,
    OptimizationGoal,
    Platform,
    UserRole,
    UserStatus,
)

# Platform models
from app.models.platform import AdAccount, TargetingTemplate

# Product models
from app.models.product import Product, ProductGroup

# Sales models
from app.models.sales import (
    OfflineSaleWeekly,
    OnlineSaleDaily,
    SaversureScanDaily,
    SKUSignal,
)

# Spark Ad Auth models
from app.models.spark_auth import SparkAdAuth, SparkAuthImportLog, SparkAuthStatus

# System models
from app.models.system import AppSetting

# TikTok Legacy models (for backward compatibility with starcontent DB)
from app.models.tiktok_legacy import (
    TiktokPost,
    ABXAdgroupLegacy,
    TiktokTargeting,
    ProductGroupLegacy,
    ProductLegacy,
    DailyAdSpend,
)

# Facebook Legacy models (for local PostgreSQL DB)
from app.models.facebook_legacy import (
    FacebookPostPerformance,
    FacebookCampaign,
    FacebookAdset,
    FacebookAd,
    FacebookAdsInsights,
    FacebookPage,
    FacebookPost,
)

# Targeting Cache models
from app.models.targeting_cache import (
    TikTokActionCategory,
    TikTokInterestCategory,
    TikTokRegion,
)

# Task models
from app.models.task import SyncStatus, TaskLog, TaskStatus

# User models
from app.models.user import Notification, User

__all__ = [
    # Base
    "Base", "BaseModel", "TimestampMixin", "SoftDeleteMixin",
    
    # Enums
    "UserRole", "UserStatus", "Platform", "ContentType", "ContentSource",
    "ContentStatus", "ContentStaffRole", "AdAccountStatus", "CampaignObjective", "OptimizationGoal",
    "AdStatus", "BudgetType", "AllocationType", "TaskStatus",
    
    # User
    "User", "Notification",
    
    # Platform
    "AdAccount", "TargetingTemplate",
    
    # Product
    "Product", "ProductGroup",
    
    # Content
    "Content", "ContentScoreHistory", "ContentStaffAllocation",
    
    # Campaign/Ad
    "Campaign", "AdGroup", "Ad", "AdPerformanceHistory", "AdPerformanceDaily",
    
    # ABX
    "ABXAdgroup", "ABXBudgetLog",
    
    # Budget
    "BudgetPlan", "BudgetAllocation", "DailyBudget", "BudgetOptimizationLog",
    
    # Sales
    "OnlineSaleDaily", "SaversureScanDaily", "OfflineSaleWeekly", "SKUSignal",
    
    # Task
    "TaskLog", "SyncStatus",

    # System
    "AppSetting",
    
    # Employee/Influencer
    "Employee", "Influencer", "ContentCreatorAssignment",
    
    # Targeting Cache
    "TikTokInterestCategory", "TikTokActionCategory", "TikTokRegion",
    
    # Spark Ad Auth
    "SparkAdAuth", "SparkAuthImportLog", "SparkAuthStatus",
    
    # TikTok Legacy (backward compatibility)
    "TiktokPost", "ABXAdgroupLegacy", "TiktokTargeting", "ProductGroupLegacy", "ProductLegacy",
]
