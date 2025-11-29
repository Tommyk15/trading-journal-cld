"""
Polygon.io Subscription Diagnostic Tool

Checks what endpoints are accessible with your API key to determine subscription level.
"""

import os
import requests
from dotenv import load_dotenv


def check_endpoint(api_key, endpoint_name, url, params=None):
    """
    Check if an endpoint is accessible

    Args:
        api_key: Polygon API key
        endpoint_name: Human-readable name
        url: Full URL to test
        params: Optional additional params

    Returns:
        Dict with status and details
    """
    if params is None:
        params = {}
    params['apiKey'] = api_key

    try:
        response = requests.get(url, params=params)

        if response.status_code == 200:
            return {"status": "✅ ACCESSIBLE", "code": 200, "message": "OK"}
        elif response.status_code == 403:
            return {"status": "🔒 FORBIDDEN", "code": 403, "message": "Requires higher subscription tier"}
        elif response.status_code == 404:
            return {"status": "❓ NOT FOUND", "code": 404, "message": "Endpoint exists but resource not found"}
        elif response.status_code == 401:
            return {"status": "❌ UNAUTHORIZED", "code": 401, "message": "Invalid API key"}
        else:
            return {"status": f"⚠️  {response.status_code}", "code": response.status_code, "message": response.text[:100]}

    except Exception as e:
        return {"status": "❌ ERROR", "code": None, "message": str(e)}


def diagnose_subscription(api_key):
    """
    Run diagnostic checks on Polygon.io subscription

    Args:
        api_key: Polygon.io API key
    """
    print("=" * 80)
    print("POLYGON.IO SUBSCRIPTION DIAGNOSTIC")
    print("=" * 80)

    base_url = "https://api.polygon.io"

    # Test endpoints from basic to premium
    endpoints = [
        {
            "name": "Stock Aggregates (Basic)",
            "url": f"{base_url}/v2/aggs/ticker/SPY/prev",
            "tier": "FREE/BASIC"
        },
        {
            "name": "Stock Snapshot (Basic)",
            "url": f"{base_url}/v2/snapshot/locale/us/markets/stocks/tickers/SPY",
            "tier": "FREE/BASIC"
        },
        {
            "name": "Options Contract Details",
            "url": f"{base_url}/v3/reference/options/contracts/O:SPY260102C00685000",
            "tier": "STARTER+"
        },
        {
            "name": "Options Snapshot (with Greeks)",
            "url": f"{base_url}/v3/snapshot/options/O:SPY260102C00685000",
            "tier": "OPTIONS TIER"
        },
        {
            "name": "Options Aggregates",
            "url": f"{base_url}/v2/aggs/ticker/O:SPY260102C00685000/prev",
            "tier": "STARTER+"
        }
    ]

    print("\n📊 Testing Polygon.io Endpoints:\n")

    results = {}
    for endpoint in endpoints:
        print(f"Testing: {endpoint['name']} (Requires: {endpoint['tier']})")
        result = check_endpoint(api_key, endpoint['name'], endpoint['url'])
        results[endpoint['name']] = result
        print(f"   {result['status']} - {result['message']}")
        print()

    # Analyze results
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Check basic access
    if results["Stock Aggregates (Basic)"]["code"] == 200:
        print("\n✅ Basic stock data: WORKING")
        print("   Your API key is valid and has basic market data access")
    else:
        print("\n❌ Basic stock data: FAILED")
        print("   Your API key may be invalid or expired")
        return

    # Check options access
    if results["Options Snapshot (with Greeks)"]["code"] == 200:
        print("\n✅ Options data with Greeks: WORKING")
        print("   You have full options data access - POC should work!")
    elif results["Options Snapshot (with Greeks)"]["code"] == 403:
        print("\n🔒 Options data with Greeks: BLOCKED (403 Forbidden)")
        print("   Your subscription does NOT include options snapshot data")
        print("\n💡 SOLUTIONS:")
        print("   1. Upgrade to Polygon.io Options subscription tier")
        print("      https://polygon.io/pricing")
        print("   2. Use alternative data source for Greeks (e.g., IBKR API)")
        print("   3. Use Options Contract endpoint for basic option data (no Greeks)")

        # Check if contract details work
        if results["Options Contract Details"]["code"] == 200:
            print("\n   ℹ️  You DO have access to Options Contract Details")
            print("      (This gives you contract info but NOT Greeks/IV)")

    # Check options aggregates
    if results.get("Options Aggregates", {}).get("code") in [200, 404]:
        print("\n✅ Options aggregates: ACCESSIBLE")
        print("   You can fetch historical options pricing data")

    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)

    if results["Options Snapshot (with Greeks)"]["code"] == 403:
        print("\n🎯 For this POC to work with Polygon.io:")
        print("   • You need to upgrade to an options-enabled subscription")
        print("   • Options data starts at ~$99/month on Polygon.io")
        print("\n🎯 Alternative approaches:")
        print("   • Use IBKR API for Greeks (already have connection)")
        print("   • Use a different options data provider")
        print("   • Skip Greeks for now and focus on trade import/grouping")
    else:
        print("\n✅ Your subscription supports the POC requirements!")

    print("=" * 80)


if __name__ == "__main__":
    load_dotenv()

    api_key = os.getenv("POLYGON_API_KEY")

    if not api_key:
        print("❌ ERROR: POLYGON_API_KEY not found in .env")
        exit(1)

    diagnose_subscription(api_key)
