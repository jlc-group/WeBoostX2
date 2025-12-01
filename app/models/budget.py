"""
Budget planning and allocation models
"""
from sqlalchemy import Column, Integer, String, Boolean, Enum, Text, Date, DateTime, JSON, Numeric, ForeignKey
from sqlalchemy.orm import relationship

from app.models.base import BaseModel
from app.models.enums import AllocationType, Platform


class BudgetPlan(BaseModel):
    """Monthly/periodic budget plan"""
    
    __tablename__ = "budget_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Plan Info
    # ============================================
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Period
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    # ============================================
    # Budget
    # ============================================
    total_budget = Column(Numeric(15, 2), nullable=False)
    
    # Allocation type
    allocation_type = Column(Enum(AllocationType), default=AllocationType.ACE)
    
    # Platform distribution (optional)
    platform_budgets = Column(JSON, nullable=True)
    # {"tiktok": 70000, "facebook": 30000}
    
    # ============================================
    # Status
    # ============================================
    is_active = Column(Boolean, default=True)
    is_current = Column(Boolean, default=False)  # Currently active plan
    
    # ============================================
    # Tracking
    # ============================================
    actual_spend = Column(Numeric(15, 2), default=0)
    
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # ============================================
    # Relationships
    # ============================================
    allocations = relationship("BudgetAllocation", back_populates="budget_plan")


class BudgetAllocation(BaseModel):
    """Budget allocation to product groups"""
    
    __tablename__ = "budget_allocations"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Links
    # ============================================
    budget_plan_id = Column(Integer, ForeignKey("budget_plans.id"), nullable=False, index=True)
    product_group_id = Column(Integer, ForeignKey("product_groups.id"), nullable=False, index=True)
    
    # Optional: platform-specific allocation
    platform = Column(Enum(Platform), nullable=True)
    
    # ============================================
    # Budget
    # ============================================
    allocated_budget = Column(Numeric(15, 2), nullable=False)
    actual_spend = Column(Numeric(15, 2), default=0)
    
    # ============================================
    # Control
    # ============================================
    is_locked = Column(Boolean, default=False)  # Lock from auto-adjustment
    
    # Content style distribution
    content_style_weights = Column(JSON, nullable=True)
    # {"SALE": 60, "REVIEW": 30, "BRANDING": 10}
    
    # ============================================
    # Tracking
    # ============================================
    last_optimized_at = Column(DateTime(timezone=True), nullable=True)
    
    # ============================================
    # Relationships
    # ============================================
    budget_plan = relationship("BudgetPlan", back_populates="allocations")
    product_group = relationship("ProductGroup", back_populates="budget_allocations")
    daily_budgets = relationship("DailyBudget", back_populates="allocation")


class DailyBudget(BaseModel):
    """Daily budget breakdown"""
    
    __tablename__ = "daily_budgets"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Links
    # ============================================
    allocation_id = Column(Integer, ForeignKey("budget_allocations.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    
    # ============================================
    # Budget
    # ============================================
    planned_budget = Column(Numeric(12, 2), nullable=False)
    actual_spend = Column(Numeric(12, 2), default=0)
    
    # ============================================
    # Control
    # ============================================
    is_locked = Column(Boolean, default=False)
    is_ace_allocated = Column(Boolean, default=False)  # ACE allocation done
    is_abx_allocated = Column(Boolean, default=False)  # ABX allocation done
    
    # Content style breakdown for this day
    content_style_budgets = Column(JSON, nullable=True)
    # {"SALE": 600, "REVIEW": 300, "BRANDING": 100}
    
    # ============================================
    # Relationships
    # ============================================
    allocation = relationship("BudgetAllocation", back_populates="daily_budgets")


class BudgetOptimizationLog(BaseModel):
    """Log of budget optimization runs"""
    
    __tablename__ = "budget_optimization_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # ============================================
    # Context
    # ============================================
    budget_plan_id = Column(Integer, ForeignKey("budget_plans.id"), nullable=True)
    allocation_id = Column(Integer, ForeignKey("budget_allocations.id"), nullable=True)
    
    optimization_type = Column(String(50), nullable=False)  # ace, abx, unified
    platform = Column(Enum(Platform), nullable=True)
    
    # ============================================
    # Execution
    # ============================================
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(50), nullable=False)  # running, completed, failed
    
    # ============================================
    # Results
    # ============================================
    changes_made = Column(Integer, default=0)
    total_budget_adjusted = Column(Numeric(15, 2), default=0)
    
    # Detailed changes
    changes_detail = Column(JSON, nullable=True)
    # [{"adgroup_id": 123, "old_budget": 100, "new_budget": 150, "reason": "high PFM"}, ...]
    
    # Error info
    error_message = Column(Text, nullable=True)
    
    # ============================================
    # Metrics at time of optimization
    # ============================================
    metrics_snapshot = Column(JSON, nullable=True)

