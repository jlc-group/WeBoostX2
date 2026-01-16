"""
Daily ad performance snapshots (platform-agnostic).

Rationale:
- We want daily analytics without re-calling external APIs.
- Keep external_ad_id so we can store history even if internal Ad rows are missing.
"""

from sqlalchemy import Column, Integer, String, Date, Enum, JSON, ForeignKey, Numeric, UniqueConstraint

from app.models.base import BaseModel
from app.models.enums import Platform


class AdPerformanceDaily(BaseModel):
    """Daily performance snapshot for an external ad (TikTok/Meta/etc)."""

    __tablename__ = "ad_performance_daily"

    id = Column(Integer, primary_key=True, index=True)

    platform = Column(Enum(Platform), nullable=False, index=True)
    ad_account_id = Column(Integer, ForeignKey("ad_accounts.id"), nullable=False, index=True)

    # External ad identifier from platform (TikTok ad_id / Meta ad.id)
    external_ad_id = Column(String(100), nullable=False, index=True)

    # Stat date (platform's day)
    date = Column(Date, nullable=False, index=True)

    # Core metrics (keep minimal + extensible)
    spend = Column(Numeric(15, 2), default=0)
    impressions = Column(Integer, default=0)
    clicks = Column(Integer, default=0)
    reach = Column(Integer, default=0)
    conversions = Column(Integer, default=0)
    purchases = Column(Integer, default=0)
    purchase_value = Column(Numeric(15, 2), default=0)

    # Raw/extended metrics as JSON
    metrics = Column(JSON, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "platform",
            "ad_account_id",
            "external_ad_id",
            "date",
            name="uq_ad_perf_daily_platform_account_ad_date",
        ),
        {"extend_existing": True},
    )


