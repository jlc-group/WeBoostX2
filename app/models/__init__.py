"""
Database models for WeBoostX 2.0
"""
from app.models.base import Base, BaseModel, TimestampMixin, SoftDeleteMixin
from app.models.enums import (
    UserRole, UserStatus, Platform, ContentType, ContentSource, ContentStatus,
    AdAccountStatus, CampaignObjective, OptimizationGoal, AdStatus, BudgetType,
    AllocationType
)

# User models
from app.models.user import User, Notification

# Platform models
from app.models.platform import AdAccount, TargetingTemplate

# Product models
from app.models.product import Product, ProductGroup

# Content models
from app.models.content import Content, ContentScoreHistory

# Campaign/Ad models
from app.models.campaign import Campaign, AdGroup, Ad, AdPerformanceHistory

# ABX models
from app.models.abx import ABXAdgroup, ABXBudgetLog

# Budget models
from app.models.budget import (
    BudgetPlan, BudgetAllocation, DailyBudget, BudgetOptimizationLog
)

# Sales models
from app.models.sales import (
    OnlineSaleDaily, SaversureScanDaily, OfflineSaleWeekly, SKUSignal
)

# Task models
from app.models.task import TaskLog, SyncStatus, TaskStatus

# System models
from app.models.system import AppSetting


__all__ = [
    # Base
    "Base", "BaseModel", "TimestampMixin", "SoftDeleteMixin",
    
    # Enums
    "UserRole", "UserStatus", "Platform", "ContentType", "ContentSource",
    "ContentStatus", "AdAccountStatus", "CampaignObjective", "OptimizationGoal",
    "AdStatus", "BudgetType", "AllocationType", "TaskStatus",
    
    # User
    "User", "Notification",
    
    # Platform
    "AdAccount", "TargetingTemplate",
    
    # Product
    "Product", "ProductGroup",
    
    # Content
    "Content", "ContentScoreHistory",
    
    # Campaign/Ad
    "Campaign", "AdGroup", "Ad", "AdPerformanceHistory",
    
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
]
