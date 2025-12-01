"""
Sales and offline signals models
"""
from sqlalchemy import Column, Integer, String, Date, DateTime, JSON, Numeric

from app.models.base import BaseModel


class OnlineSaleDaily(BaseModel):
    """Daily online sales data (TikTok Shop, Shopee, Lazada)"""
    
    __tablename__ = "online_sales_daily"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Date
    date = Column(Date, nullable=False, index=True)
    
    # Platform
    platform = Column(String(50), nullable=False, index=True)  # tiktok_shop, shopee, lazada
    
    # Product
    product_code = Column(String(50), nullable=False, index=True)
    product_name = Column(String(255), nullable=True)
    
    # Sales metrics
    orders = Column(Integer, default=0)
    units_sold = Column(Integer, default=0)
    revenue = Column(Numeric(15, 2), default=0)
    
    # Additional data
    extra_data = Column(JSON, nullable=True)


class SaversureScanDaily(BaseModel):
    """Daily Saversure scan data"""
    
    __tablename__ = "saversure_scans_daily"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Date
    date = Column(Date, nullable=False, index=True)
    
    # Product
    product_code = Column(String(50), nullable=False, index=True)
    product_name = Column(String(255), nullable=True)
    
    # Scan metrics
    scan_count = Column(Integer, default=0)
    unique_users = Column(Integer, default=0)
    
    # Location breakdown (optional)
    region_breakdown = Column(JSON, nullable=True)


class OfflineSaleWeekly(BaseModel):
    """Weekly offline sales data (7-11, etc.)"""
    
    __tablename__ = "offline_sales_weekly"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Week
    week_start = Column(Date, nullable=False, index=True)
    week_end = Column(Date, nullable=False)
    
    # Channel
    channel = Column(String(50), nullable=False, index=True)  # 7-11, bigc, lotus, etc.
    
    # Product
    product_code = Column(String(50), nullable=False, index=True)
    product_name = Column(String(255), nullable=True)
    
    # Sales metrics
    units_sold = Column(Integer, default=0)
    revenue = Column(Numeric(15, 2), default=0)
    
    # Store count
    stores_sold = Column(Integer, default=0)
    
    # Additional data
    extra_data = Column(JSON, nullable=True)


class SKUSignal(BaseModel):
    """Aggregated SKU-level signals for optimization"""
    
    __tablename__ = "sku_signals"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Date
    date = Column(Date, nullable=False, index=True)
    
    # Product
    product_code = Column(String(50), nullable=False, index=True)
    
    # Aggregated signals
    online_revenue = Column(Numeric(15, 2), default=0)
    online_orders = Column(Integer, default=0)
    scan_count = Column(Integer, default=0)
    offline_units = Column(Integer, default=0)
    
    # Calculated demand score
    demand_score = Column(Numeric(5, 2), nullable=True)
    
    # Trend (vs previous period)
    trend_pct = Column(Numeric(6, 2), nullable=True)
    
    # Breakdown by source
    signal_breakdown = Column(JSON, nullable=True)

