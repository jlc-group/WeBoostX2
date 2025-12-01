"""
Sales data sync tasks
"""
from datetime import datetime, date

from app.core.database import SessionLocal
from app.models import SaversureScanDaily, OfflineSaleWeekly, SKUSignal


def sync_saversure_data():
    """
    Sync Saversure scan data
    This would connect to Saversure API or database
    """
    print("Syncing Saversure scan data...")
    
    # TODO: Implement Saversure API integration
    # 1. Connect to Saversure data source
    # 2. Fetch daily scan data
    # 3. Upsert into saversure_scans_daily table
    # 4. Update SKU signals
    
    pass


def sync_offline_sales():
    """
    Sync offline sales data (7-11, etc.)
    This would process weekly sales reports
    """
    print("Syncing offline sales data...")
    
    # TODO: Implement offline sales sync
    # 1. Read sales report (CSV/Excel/API)
    # 2. Parse and validate data
    # 3. Upsert into offline_sales_weekly table
    # 4. Update SKU signals
    
    pass


def update_sku_signals():
    """
    Update aggregated SKU signals from all sources
    """
    db = SessionLocal()
    
    try:
        today = date.today()
        
        # TODO: Aggregate signals from:
        # - online_sales_daily
        # - saversure_scans_daily
        # - offline_sales_weekly
        # 
        # Calculate demand_score and trend for each SKU
        
        pass
        
    finally:
        db.close()

