"""
Budget optimization tasks
"""
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict

from app.core.database import SessionLocal
from app.models import (
    BudgetPlan, BudgetAllocation, DailyBudget, 
    ABXAdgroup, Content, BudgetOptimizationLog
)
from app.models.enums import Platform, ContentType, AdStatus


def run_budget_optimization():
    """
    Main budget optimization routine
    Runs ACE and ABX optimization for all active budget plans
    """
    db = SessionLocal()
    
    try:
        # Get active budget plans
        today = date.today()
        active_plans = db.query(BudgetPlan).filter(
            BudgetPlan.is_active == True,
            BudgetPlan.start_date <= today,
            BudgetPlan.end_date >= today
        ).all()
        
        for plan in active_plans:
            print(f"Optimizing budget plan: {plan.name}")
            
            # Get allocations for this plan
            allocations = db.query(BudgetAllocation).filter(
                BudgetAllocation.budget_plan_id == plan.id,
                BudgetAllocation.is_locked == False
            ).all()
            
            for allocation in allocations:
                try:
                    if plan.allocation_type.value == "ace":
                        optimize_ace_allocation(db, allocation)
                    elif plan.allocation_type.value == "abx":
                        optimize_abx_allocation(db, allocation)
                except Exception as e:
                    print(f"Error optimizing allocation {allocation.id}: {e}")
                    continue
        
        db.commit()
        
    finally:
        db.close()


def optimize_ace_allocation(db, allocation: BudgetAllocation):
    """
    ACE (Content-based) budget optimization
    
    1. Get content for this product group
    2. Rank by unified score
    3. Distribute budget based on score
    """
    print(f"  Running ACE optimization for allocation {allocation.id}")
    
    # Get today's budget
    today = date.today()
    daily_budget = db.query(DailyBudget).filter(
        DailyBudget.allocation_id == allocation.id,
        DailyBudget.date == today,
        DailyBudget.is_locked == False
    ).first()
    
    if not daily_budget:
        return
    
    # Get content for this product group
    contents = db.query(Content).filter(
        Content.product_group_id == allocation.product_group_id,
        Content.deleted_at.is_(None),
        Content.unified_score.isnot(None)
    ).order_by(Content.unified_score.desc()).limit(50).all()
    
    if not contents:
        return
    
    # Calculate total score for distribution
    total_score = sum(float(c.unified_score or 0) for c in contents)
    
    if total_score == 0:
        return
    
    # Distribute budget based on score
    budget_to_distribute = float(daily_budget.planned_budget)
    
    distribution = []
    for content in contents:
        score_ratio = float(content.unified_score or 0) / total_score
        content_budget = budget_to_distribute * score_ratio
        
        # Minimum budget threshold
        if content_budget < 50:  # Skip if less than 50 THB
            continue
        
        distribution.append({
            "content_id": content.id,
            "platform": content.platform.value,
            "score": float(content.unified_score),
            "budget": round(content_budget, 2)
        })
    
    # Log the optimization
    log = BudgetOptimizationLog(
        budget_plan_id=allocation.budget_plan_id,
        allocation_id=allocation.id,
        optimization_type="ace",
        started_at=datetime.now(),
        completed_at=datetime.now(),
        status="completed",
        changes_made=len(distribution),
        total_budget_adjusted=Decimal(str(budget_to_distribute)),
        changes_detail=distribution
    )
    db.add(log)
    
    # Mark as allocated
    daily_budget.is_ace_allocated = True
    
    # TODO: Actually apply budget changes to ads via platform APIs
    print(f"    Distributed budget to {len(distribution)} content items")


def optimize_abx_allocation(db, allocation: BudgetAllocation):
    """
    ABX (Adgroup-based) budget optimization
    
    1. Get ABX adgroups for this product group
    2. Rank by PFM score
    3. Distribute budget based on performance
    """
    print(f"  Running ABX optimization for allocation {allocation.id}")
    
    # Get today's budget
    today = date.today()
    daily_budget = db.query(DailyBudget).filter(
        DailyBudget.allocation_id == allocation.id,
        DailyBudget.date == today,
        DailyBudget.is_locked == False
    ).first()
    
    if not daily_budget:
        return
    
    # Get ABX adgroups for this product group
    adgroups = db.query(ABXAdgroup).filter(
        ABXAdgroup.product_group_id == allocation.product_group_id,
        ABXAdgroup.is_active == True,
        ABXAdgroup.is_current_plan == True
    ).order_by(ABXAdgroup.pfm_score.desc().nullslast()).all()
    
    if not adgroups:
        return
    
    # Calculate distribution based on PFM score
    budget_to_distribute = float(daily_budget.planned_budget)
    
    # Group by content style
    style_budgets = daily_budget.content_style_budgets or {}
    
    distribution = []
    for adgroup in adgroups:
        style = adgroup.group_style.value if adgroup.group_style else "other"
        style_budget = style_budgets.get(style, budget_to_distribute / len(adgroups))
        
        # Adjust based on PFM
        pfm_multiplier = 1.0
        if adgroup.pfm_score:
            if adgroup.pfm_score >= 1.5:
                pfm_multiplier = 1.3  # Increase budget for high performers
            elif adgroup.pfm_score >= 1.0:
                pfm_multiplier = 1.0
            elif adgroup.pfm_score >= 0.5:
                pfm_multiplier = 0.7  # Decrease for low performers
            else:
                pfm_multiplier = 0.3  # Significantly reduce
        
        adgroup_budget = style_budget * pfm_multiplier
        
        distribution.append({
            "adgroup_id": adgroup.id,
            "external_adgroup_id": adgroup.external_adgroup_id,
            "style": style,
            "pfm_score": float(adgroup.pfm_score or 0),
            "budget": round(adgroup_budget, 2)
        })
    
    # Log the optimization
    log = BudgetOptimizationLog(
        budget_plan_id=allocation.budget_plan_id,
        allocation_id=allocation.id,
        optimization_type="abx",
        started_at=datetime.now(),
        completed_at=datetime.now(),
        status="completed",
        changes_made=len(distribution),
        total_budget_adjusted=Decimal(str(budget_to_distribute)),
        changes_detail=distribution
    )
    db.add(log)
    
    # Mark as allocated
    daily_budget.is_abx_allocated = True
    
    # TODO: Actually apply budget changes to adgroups via TikTok API
    print(f"    Distributed budget to {len(distribution)} adgroups")

