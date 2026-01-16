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
    # Campaigns & AdGroups Sync (every 15 minutes)
    # - For fast ABX/ACE ad creation flow
    # ============================================
    scheduler.add_job(
        func=sync_campaigns_adgroups_job,
        trigger=IntervalTrigger(minutes=15),
        id="sync_campaigns_adgroups",
        name="Sync campaigns & adgroups to local DB",
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
    # TikTok Ad Daily Performance (every 30 minutes)
    # - incremental/backfill into ad_performance_daily
    # ============================================
    scheduler.add_job(
        func=sync_tiktok_ad_daily_performance_job,
        trigger=IntervalTrigger(minutes=30),
        id="sync_tiktok_ad_daily_performance",
        name="Sync TikTok ad daily performance (incremental/backfill)",
        replace_existing=True,
    )

    # ============================================
    # Aggregate Content Cost from Daily (every 60 minutes)
    # - reads ad_performance_daily and updates contents.ads_total_cost
    # ============================================
    scheduler.add_job(
        func=aggregate_content_cost_from_daily_job,
        trigger=IntervalTrigger(minutes=60),
        id="aggregate_content_cost_from_daily",
        name="Aggregate Content ads_total_cost from ad_performance_daily",
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
    # Content Expire Date Update (every 60 minutes)
    # - Influencer: auth_end_time from Spark Ads
    # - Official/Other: platform_created_at + 2 years
    # ============================================
    scheduler.add_job(
        func=update_content_expire_dates_job,
        trigger=IntervalTrigger(minutes=60),
        id="update_content_expire_dates",
        name="Update content expire dates (influencer auth / official +2yr)",
        replace_existing=True,
    )
    
    # ============================================
    # Spark Auth Jobs (every 30 minutes)
    # - Auto-bind unbound auth codes with content
    # - Check and mark expired auth codes
    # ============================================
    scheduler.add_job(
        func=spark_auth_auto_bind_job,
        trigger=IntervalTrigger(minutes=30),
        id="spark_auth_auto_bind",
        name="Auto-bind Spark Auth codes with content",
        replace_existing=True,
    )
    
    scheduler.add_job(
        func=spark_auth_expire_check_job,
        trigger=CronTrigger(hour=1, minute=0),  # Daily at 1 AM
        id="spark_auth_expire_check",
        name="Check and mark expired Spark Auth codes",
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
    
    # Sync TikTok Targeting Data (interests, actions, regions) - daily at 3 AM
    scheduler.add_job(
        func=sync_targeting_cache_job,
        trigger=CronTrigger(hour=3, minute=0),
        id="sync_targeting_cache",
        name="Sync TikTok targeting options to local cache",
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


def sync_campaigns_adgroups_job():
    """Sync campaigns & adgroups to local DB for fast ad creation"""
    print(f"[{datetime.now()}] Running campaigns & adgroups sync job...")
    try:
        from app.tasks.sync_tasks import sync_campaigns_adgroups
        result = sync_campaigns_adgroups()
        print(f"[{datetime.now()}] Campaigns & adgroups sync completed: {result}")
    except Exception as e:
        print(f"[{datetime.now()}] Campaigns & adgroups sync failed: {e}")


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


def sync_tiktok_ad_daily_performance_job():
    """Incremental/backfill TikTok daily ad performance into ad_performance_daily."""
    print(f"[{datetime.now()}] Running TikTok ad daily performance job...")
    try:
        from app.tasks.sync_tasks import sync_tiktok_ad_performance_daily
        result = sync_tiktok_ad_performance_daily(chunk_days=2, default_start_days=30, max_accounts=0)
        print(f"[{datetime.now()}] TikTok ad daily performance job completed: {result}")
    except Exception as e:
        print(f"[{datetime.now()}] TikTok ad daily performance job failed: {e}")


def aggregate_content_cost_from_daily_job():
    """Aggregate Content ads_total_cost from ad_performance_daily (TikTok now, extend later)."""
    print(f"[{datetime.now()}] Running aggregate content cost from daily job...")
    try:
        from app.tasks.sync_tasks import aggregate_content_cost_from_ad_performance_daily
        result = aggregate_content_cost_from_ad_performance_daily(platform="TIKTOK", lookback_days=7)
        print(f"[{datetime.now()}] Aggregate content cost from daily completed: {result}")
    except Exception as e:
        print(f"[{datetime.now()}] Aggregate content cost from daily failed: {e}")


def update_ace_abx_job():
    """Update ACE/ABX ad counts and details from ads_details"""
    print(f"[{datetime.now()}] Running ACE/ABX update job...")
    try:
        from app.tasks.sync_tasks import update_ace_abx_details
        update_ace_abx_details()
        print(f"[{datetime.now()}] ACE/ABX update completed")
    except Exception as e:
        print(f"[{datetime.now()}] ACE/ABX update failed: {e}")


def update_content_expire_dates_job():
    """
    Update expire_date for all content:
    - INFLUENCER: auth_end_time from TikTok Spark Ads API
    - PAGE/STAFF/UGC: platform_created_at + 2 years
    """
    print(f"[{datetime.now()}] Running content expire dates update job...")
    try:
        from app.tasks.sync_tasks import update_content_expire_dates
        result = update_content_expire_dates()
        print(f"[{datetime.now()}] Content expire dates update completed: {result}")
    except Exception as e:
        print(f"[{datetime.now()}] Content expire dates update failed: {e}")


def spark_auth_auto_bind_job():
    """
    Auto-bind Spark Auth codes with content
    
    สำหรับกรณีที่ import auth codes ก่อน แล้ว content ถูก sync มาทีหลัง
    """
    print(f"[{datetime.now()}] Running Spark Auth auto-bind job...")
    try:
        from app.services.spark_auth_service import SparkAuthService
        result = SparkAuthService.run_auto_bind_job()
        print(f"[{datetime.now()}] Spark Auth auto-bind completed: {result}")
    except Exception as e:
        print(f"[{datetime.now()}] Spark Auth auto-bind failed: {e}")


def spark_auth_expire_check_job():
    """
    Check and mark expired Spark Auth codes
    """
    print(f"[{datetime.now()}] Running Spark Auth expire check job...")
    try:
        from app.services.spark_auth_service import SparkAuthService
        result = SparkAuthService.run_expire_check_job()
        print(f"[{datetime.now()}] Spark Auth expire check completed: {result}")
    except Exception as e:
        print(f"[{datetime.now()}] Spark Auth expire check failed: {e}")


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


def sync_targeting_cache_job():
    """Sync TikTok targeting options to local cache"""
    print(f"[{datetime.now()}] Running targeting cache sync job...")
    try:
        from app.tasks.sync_targeting import sync_all_tiktok_targeting
        result = sync_all_tiktok_targeting(language="th")
        print(f"[{datetime.now()}] Targeting cache sync completed: {result}")
    except Exception as e:
        print(f"[{datetime.now()}] Targeting cache sync failed: {e}")


def sync_offline_sales_job():
    """Sync offline sales data"""
    print(f"[{datetime.now()}] Running offline sales sync job...")
    try:
        from app.tasks.sales_tasks import sync_offline_sales
        sync_offline_sales()
        print(f"[{datetime.now()}] Offline sales sync completed")
    except Exception as e:
        print(f"[{datetime.now()}] Offline sales sync failed: {e}")

