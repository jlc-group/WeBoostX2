"""
Score calculation tasks
"""
from datetime import datetime
from decimal import Decimal

from app.core.database import SessionLocal
from app.models import Content, ContentScoreHistory
from app.models.enums import Platform


def calculate_all_scores():
    """Calculate PFM, FB score, and unified score for all content"""
    db = SessionLocal()
    
    try:
        # Get all active content
        contents = db.query(Content).filter(
            Content.deleted_at.is_(None)
        ).all()
        
        for content in contents:
            try:
                # Calculate platform-specific score
                if content.platform == Platform.TIKTOK:
                    pfm_score = calculate_pfm_score(content)
                    content.pfm_score = pfm_score
                elif content.platform in [Platform.FACEBOOK, Platform.INSTAGRAM]:
                    fb_score = calculate_fb_score(content)
                    content.fb_score = fb_score
                
                # Calculate unified score
                unified_score = calculate_unified_score(content)
                content.unified_score = unified_score
                
            except Exception as e:
                print(f"Error calculating score for content {content.id}: {e}")
                continue
        
        db.commit()
        print(f"Updated scores for {len(contents)} content items")
        
    finally:
        db.close()


def calculate_pfm_score(content: Content) -> Decimal:
    """
    Calculate TikTok PFM score
    
    PFM = Performance Factor Multiplier
    Based on: CTR, CVR, ViewTime, ROAS, Spend efficiency
    """
    # Base score components
    score = Decimal("1.0")
    
    # View engagement (views vs impressions)
    if content.impressions and content.impressions > 0:
        view_rate = content.views / content.impressions
        if view_rate > 0.5:
            score += Decimal("0.3")
        elif view_rate > 0.3:
            score += Decimal("0.15")
    
    # Watch time efficiency
    if content.video_duration and content.avg_watch_time:
        watch_rate = float(content.avg_watch_time) / float(content.video_duration)
        if watch_rate > 0.5:
            score += Decimal("0.4")
        elif watch_rate > 0.3:
            score += Decimal("0.2")
    
    # Engagement rate
    if content.views and content.views > 0:
        engagement = (content.likes + content.comments + content.shares) / content.views
        if engagement > 0.05:
            score += Decimal("0.3")
        elif engagement > 0.02:
            score += Decimal("0.15")
    
    # Completion rate
    if content.completion_rate:
        if content.completion_rate > 20:
            score += Decimal("0.3")
        elif content.completion_rate > 10:
            score += Decimal("0.15")
    
    # Ad performance (if has ads)
    if content.ads_total_cost and content.ads_total_cost > 0:
        # Cost efficiency - lower cost per view is better
        if content.views and content.views > 0:
            cpv = float(content.ads_total_cost) / content.views
            if cpv < 0.1:
                score += Decimal("0.2")
            elif cpv < 0.3:
                score += Decimal("0.1")
    
    return min(score, Decimal("3.0"))  # Cap at 3.0


def calculate_fb_score(content: Content) -> Decimal:
    """
    Calculate Facebook/Instagram performance score
    
    Based on: CTR, CPC, Cost per result, ROAS, Frequency, ThruPlay rate
    """
    score = Decimal("1.0")
    
    # Reach efficiency
    if content.impressions and content.impressions > 0:
        reach_rate = content.reach / content.impressions if content.reach else 0
        if reach_rate > 0.7:
            score += Decimal("0.2")
    
    # Engagement rate
    if content.reach and content.reach > 0:
        engagement = (content.likes + content.comments + content.shares) / content.reach
        if engagement > 0.05:
            score += Decimal("0.3")
        elif engagement > 0.02:
            score += Decimal("0.15")
    
    # Video completion (from platform_metrics)
    if content.platform_metrics:
        thruplay = content.platform_metrics.get("thruplay", 0)
        views_3s = content.platform_metrics.get("video_views_3s", 0)
        if thruplay and views_3s and views_3s > 0:
            completion_rate = thruplay / views_3s
            if completion_rate > 0.3:
                score += Decimal("0.3")
            elif completion_rate > 0.15:
                score += Decimal("0.15")
    
    # Ad cost efficiency
    if content.ads_total_cost and content.ads_total_cost > 0:
        if content.reach and content.reach > 0:
            cpr = float(content.ads_total_cost) / content.reach * 1000  # CPM
            if cpr < 50:
                score += Decimal("0.2")
            elif cpr < 100:
                score += Decimal("0.1")
    
    return min(score, Decimal("3.0"))


def calculate_unified_score(content: Content) -> Decimal:
    """
    Calculate Unified Content Impact Score
    
    Weights (MVP):
    - TikTok online performance: ~50%
    - Facebook/IG online performance: ~30%
    - Saversure/Offline demand: ~20% (SKU-level signal)
    """
    score = Decimal("0")
    
    # Platform performance (normalized to 0-50 scale)
    if content.pfm_score:
        # TikTok PFM contributes up to 50 points
        score += (content.pfm_score / Decimal("3.0")) * Decimal("50")
    
    if content.fb_score:
        # FB score contributes up to 30 points
        score += (content.fb_score / Decimal("3.0")) * Decimal("30")
    
    # TODO: Add SKU-level demand signal (up to 20 points)
    # This would come from SKUSignal table based on product_codes
    
    # Apply boost factor
    if content.boost_factor and content.boost_factor > 1:
        score *= content.boost_factor
    
    return min(score, Decimal("100"))  # Cap at 100

