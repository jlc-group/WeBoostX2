"""
Budget management tasks
"""
from datetime import datetime, date, timedelta
from decimal import Decimal

from app.core.database import SessionLocal
from app.models import BudgetPlan, BudgetAllocation, DailyBudget


def recalculate_daily_budgets():
    """
    Daily budget recalculation
    - Create daily budget entries for active plans
    - Redistribute remaining budget based on performance
    """
    db = SessionLocal()
    
    try:
        today = date.today()
        
        # Get active budget plans
        active_plans = db.query(BudgetPlan).filter(
            BudgetPlan.is_active == True,
            BudgetPlan.start_date <= today,
            BudgetPlan.end_date >= today
        ).all()
        
        for plan in active_plans:
            process_plan_daily_budget(db, plan, today)
        
        db.commit()
        print(f"Daily budget recalculation completed for {len(active_plans)} plans")
        
    finally:
        db.close()


def process_plan_daily_budget(db, plan: BudgetPlan, today: date):
    """Process daily budget for a single plan"""
    
    # Get all allocations for this plan
    allocations = db.query(BudgetAllocation).filter(
        BudgetAllocation.budget_plan_id == plan.id
    ).all()
    
    for allocation in allocations:
        # Check if daily budget exists for today
        existing = db.query(DailyBudget).filter(
            DailyBudget.allocation_id == allocation.id,
            DailyBudget.date == today
        ).first()
        
        if existing:
            # Update actual spend from yesterday
            update_yesterday_spend(db, allocation, today)
            continue
        
        # Calculate remaining days in plan
        days_remaining = (plan.end_date - today).days + 1
        if days_remaining <= 0:
            continue
        
        # Calculate remaining budget
        spent_so_far = db.query(DailyBudget).filter(
            DailyBudget.allocation_id == allocation.id,
            DailyBudget.date < today
        ).with_entities(
            db.func.coalesce(db.func.sum(DailyBudget.actual_spend), 0)
        ).scalar() or Decimal("0")
        
        remaining_budget = allocation.allocated_budget - spent_so_far
        
        # Calculate daily budget (simple even distribution for now)
        daily_amount = remaining_budget / days_remaining
        
        # Create daily budget entry
        daily_budget = DailyBudget(
            allocation_id=allocation.id,
            date=today,
            planned_budget=daily_amount,
            actual_spend=Decimal("0"),
            is_locked=False,
            content_style_budgets=allocation.content_style_weights
        )
        db.add(daily_budget)


def update_yesterday_spend(db, allocation: BudgetAllocation, today: date):
    """Update actual spend for yesterday"""
    yesterday = today - timedelta(days=1)
    
    daily_budget = db.query(DailyBudget).filter(
        DailyBudget.allocation_id == allocation.id,
        DailyBudget.date == yesterday
    ).first()
    
    if not daily_budget:
        return
    
    # TODO: Fetch actual spend from platform APIs
    # For now, we'll leave actual_spend as is (would be updated by ad sync)
    pass

