"""
Background task scheduler using APScheduler
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from app.core.config import settings

# Global scheduler instance
scheduler: BackgroundScheduler = None


def start_scheduler():
    """Initialize and start the scheduler"""
    global scheduler
    
    if scheduler is not None:
        return
    
    scheduler = BackgroundScheduler()
    
    # ============================================
    # Content Sync Jobs (every 60 minutes)
    # ============================================
    scheduler.add_job(
        func=sync_content_job,
        trigger=IntervalTrigger(minutes=settings.CONTENT_SYNC_INTERVAL_MINUTES),
        id="sync_content",
        name="Sync content from all platforms",
        replace_existing=True,
    )
    
    # ============================================
    # Ad Sync Jobs (every 30 minutes)
    # ============================================
    scheduler.add_job(
        func=sync_ads_job,
        trigger=IntervalTrigger(minutes=settings.AD_SYNC_INTERVAL_MINUTES),
        id="sync_ads",
        name="Sync ads from all platforms",
        replace_existing=True,
    )
    
    # ============================================
    # Ads Spend Sync (every 60 minutes)
    # ============================================
    scheduler.add_job(
        func=sync_ads_spend_job,
        trigger=IntervalTrigger(minutes=60),
        id="sync_ads_spend",
        name="Sync ads spend data from TikTok",
        replace_existing=True,
    )
    
    # ============================================
    # ACE/ABX Details Update (every 60 minutes, after ads sync)
    # ============================================
    scheduler.add_job(
        func=update_ace_abx_job,
        trigger=IntervalTrigger(minutes=60),
        id="update_ace_abx",
        name="Update ACE/ABX details from ads_details",
        replace_existing=True,
    )
    
    # ============================================
    # Score Calculation (every 30 minutes)
    # ============================================
    scheduler.add_job(
        func=calculate_scores_job,
        trigger=IntervalTrigger(minutes=30),
        id="calculate_scores",
        name="Calculate PFM and unified scores",
        replace_existing=True,
    )
    
    # ============================================
    # Budget Optimization (every 2-3 hours)
    # ============================================
    scheduler.add_job(
        func=optimize_budget_job,
        trigger=IntervalTrigger(hours=settings.OPTIMIZATION_INTERVAL_HOURS),
        id="optimize_budget",
        name="Run budget optimization",
        replace_existing=True,
    )
    
    # ============================================
    # Daily Jobs (run at specific times)
    # ============================================
    
    # Saversure scan sync - daily at 6 AM
    scheduler.add_job(
        func=sync_saversure_job,
        trigger=CronTrigger(hour=6, minute=0),
        id="sync_saversure",
        name="Sync Saversure scan data",
        replace_existing=True,
    )
    
    # Daily budget recalculation - at midnight
    scheduler.add_job(
        func=daily_budget_job,
        trigger=CronTrigger(hour=0, minute=5),
        id="daily_budget",
        name="Daily budget recalculation",
        replace_existing=True,
    )
    
    # ============================================
    # Weekly Jobs
    # ============================================
    
    # Offline sales sync - Monday at 7 AM
    scheduler.add_job(
        func=sync_offline_sales_job,
        trigger=CronTrigger(day_of_week="mon", hour=7, minute=0),
        id="sync_offline_sales",
        name="Sync offline sales data",
        replace_existing=True,
    )
    
    # Start the scheduler
    scheduler.start()
    print(f"[{datetime.now()}] Scheduler started with {len(scheduler.get_jobs())} jobs")


def stop_scheduler():
    """Stop the scheduler"""
    global scheduler
    
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        print(f"[{datetime.now()}] Scheduler stopped")


# ============================================
# Job Functions
# ============================================

def sync_content_job():
    """Sync content from all platforms"""
    print(f"[{datetime.now()}] Running content sync job...")
    try:
        # Import here to avoid circular imports
        from app.tasks.sync_tasks import sync_all_content
        sync_all_content()
        print(f"[{datetime.now()}] Content sync completed")
    except Exception as e:
        print(f"[{datetime.now()}] Content sync failed: {e}")


def sync_ads_job():
    """Sync ads from all platforms"""
    print(f"[{datetime.now()}] Running ads sync job...")
    try:
        from app.tasks.sync_tasks import sync_all_ads
        sync_all_ads()
        print(f"[{datetime.now()}] Ads sync completed")
    except Exception as e:
        print(f"[{datetime.now()}] Ads sync failed: {e}")


def sync_ads_spend_job():
    """Sync ads spend data from TikTok Report API"""
    print(f"[{datetime.now()}] Running ads spend sync job...")
    try:
        from app.tasks.sync_tasks import sync_ads_spend_data, update_all_ads_total_cost
        # Step 1: Fetch spend data from TikTok and update ads_details
        sync_ads_spend_data()
        # Step 2: Recalculate ads_total_cost from ads_details
        update_all_ads_total_cost()
        print(f"[{datetime.now()}] Ads spend sync completed")
    except Exception as e:
        print(f"[{datetime.now()}] Ads spend sync failed: {e}")


def update_ace_abx_job():
    """Update ACE/ABX ad counts and details from ads_details"""
    print(f"[{datetime.now()}] Running ACE/ABX update job...")
    try:
        from app.tasks.sync_tasks import update_ace_abx_details
        update_ace_abx_details()
        print(f"[{datetime.now()}] ACE/ABX update completed")
    except Exception as e:
        print(f"[{datetime.now()}] ACE/ABX update failed: {e}")


def calculate_scores_job():
    """Calculate PFM and unified scores"""
    print(f"[{datetime.now()}] Running score calculation job...")
    try:
        from app.tasks.score_tasks import calculate_all_scores
        calculate_all_scores()
        print(f"[{datetime.now()}] Score calculation completed")
    except Exception as e:
        print(f"[{datetime.now()}] Score calculation failed: {e}")


def optimize_budget_job():
    """Run budget optimization"""
    print(f"[{datetime.now()}] Running budget optimization job...")
    try:
        from app.tasks.optimization_tasks import run_budget_optimization
        run_budget_optimization()
        print(f"[{datetime.now()}] Budget optimization completed")
    except Exception as e:
        print(f"[{datetime.now()}] Budget optimization failed: {e}")


def sync_saversure_job():
    """Sync Saversure scan data"""
    print(f"[{datetime.now()}] Running Saversure sync job...")
    try:
        from app.tasks.sales_tasks import sync_saversure_data
        sync_saversure_data()
        print(f"[{datetime.now()}] Saversure sync completed")
    except Exception as e:
        print(f"[{datetime.now()}] Saversure sync failed: {e}")


def daily_budget_job():
    """Daily budget recalculation"""
    print(f"[{datetime.now()}] Running daily budget job...")
    try:
        from app.tasks.budget_tasks import recalculate_daily_budgets
        recalculate_daily_budgets()
        print(f"[{datetime.now()}] Daily budget job completed")
    except Exception as e:
        print(f"[{datetime.now()}] Daily budget job failed: {e}")


def sync_offline_sales_job():
    """Sync offline sales data"""
    print(f"[{datetime.now()}] Running offline sales sync job...")
    try:
        from app.tasks.sales_tasks import sync_offline_sales
        sync_offline_sales()
        print(f"[{datetime.now()}] Offline sales sync completed")
    except Exception as e:
        print(f"[{datetime.now()}] Offline sales sync failed: {e}")

