"""
Test Facebook Dashboard API (directly using mapper)

This tests the legacy mapper without running the full server.
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.facebook.fb_legacy_mapper import get_legacy_mapper


def main():
    print("\n" + "=" * 70)
    print("Facebook Dashboard API Test (Direct Mapper)")
    print("=" * 70)
    
    try:
        mapper = get_legacy_mapper()
        
        # Test 1: Dashboard Summary
        print("\n[1] Dashboard Summary")
        print("-" * 40)
        summary = mapper.get_dashboard_summary()
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"    {key}: {value:,.2f}")
            else:
                print(f"    {key}: {value:,}")
        
        # Test 2: Pages
        print("\n[2] Facebook Pages")
        print("-" * 40)
        pages = mapper.get_pages()
        for page in pages:
            print(f"    - {page['name']} (ID: {page['id']})")
            print(f"      Likes: {page.get('likes', 0):,}, Followers: {page.get('followers_count', 0):,}")
        
        # Test 3: Recent Posts
        print("\n[3] Recent Posts (5)")
        print("-" * 40)
        posts = mapper.get_recent_posts(limit=5)
        for post in posts:
            msg = (post.get('message') or '')[:50]
            print(f"    - [{post.get('type', 'unknown')}] {msg}...")
            print(f"      Created: {post.get('created_time')}")
        
        # Test 4: Top Performing Posts
        print("\n[4] Top Performing Posts (5)")
        print("-" * 40)
        top_posts = mapper.get_top_posts_by_performance(limit=5)
        for i, post in enumerate(top_posts, 1):
            msg = (post.get('message') or '')[:40]
            score = float(post.get('performance_score') or 0)
            cost = float(post.get('ads_total_cost') or 0)
            print(f"    {i}. Score: {score:.2f} - {msg}...")
            print(f"       Ads Cost: {cost:,.2f}")
        
        # Test 5: Campaigns
        print("\n[5] Campaigns (5)")
        print("-" * 40)
        campaigns = mapper.get_campaigns(limit=5)
        for camp in campaigns:
            print(f"    - {camp['name']}")
            print(f"      Status: {camp.get('status')}, Objective: {camp.get('objective')}")
        
        # Test 6: Campaigns Performance
        print("\n[6] Campaigns Performance (Top 5 by Spend)")
        print("-" * 40)
        camp_perf = mapper.get_campaigns_performance()[:5]
        for camp in camp_perf:
            spend = float(camp.get('total_spend') or 0)
            print(f"    - {camp['name']}")
            print(f"      Spend: {spend:,.2f}, AdSets: {camp.get('adsets_count', 0)}, Ads: {camp.get('ads_count', 0)}")
        
        # Test 7: Ad Accounts
        print("\n[7] Ad Accounts")
        print("-" * 40)
        accounts = mapper.get_ad_accounts()
        for acc in accounts:
            print(f"    - {acc.get('business_name', 'Unknown')} (ID: {acc.get('account_id')})")
        
        print("\n" + "=" * 70)
        print("[SUCCESS] All tests passed!")
        print("=" * 70)
        print("\nYou can now run the server and access:")
        print("  GET /api/v1/fb-dashboard/summary")
        print("  GET /api/v1/fb-dashboard/posts")
        print("  GET /api/v1/fb-dashboard/campaigns")
        print("  etc.")
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
