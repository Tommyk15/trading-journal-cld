#!/usr/bin/env python3
"""Test script for FRED API integration."""

import asyncio
import sys

sys.path.insert(0, "src")

from trading_journal.services.fred_service import FredService, FredServiceError


async def test_fred_service():
    """Test FRED service functionality."""
    print("=" * 60)
    print("Testing FRED API Integration")
    print("=" * 60)

    try:
        async with FredService() as fred:
            # Test 1: Check API status
            print("\n1. Checking API status...")
            is_valid = await fred.check_api_status()
            print(f"   API Status: {'✓ Available' if is_valid else '✗ Unavailable (will use fallback)'}")

            # Test 2: Get 3-month T-bill rate
            print("\n2. Fetching 3-month Treasury Bill rate (DTB3)...")
            rate = await fred.get_risk_free_rate()
            print(f"   Rate: {float(rate.rate) * 100:.2f}%")
            print(f"   Observation Date: {rate.observation_date.strftime('%Y-%m-%d')}")
            print(f"   Source: {rate.source}")
            print(f"   Fetched At: {rate.fetched_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")

            # Test 3: Test caching
            print("\n3. Testing cache...")
            rate2 = await fred.get_risk_free_rate()
            print(f"   Second fetch (should be cached): {float(rate2.rate) * 100:.2f}%")
            print(f"   Same object: {rate is rate2}")

            # Test 4: Fetch multiple treasury rates
            print("\n4. Fetching multiple treasury rates...")
            rates = await fred.get_treasury_rates()
            for maturity, r in rates.items():
                print(f"   {maturity}: {float(r.rate) * 100:.2f}% ({r.source})")

            # Test 5: Clear cache and refetch
            print("\n5. Testing cache clear...")
            fred.clear_cache()
            rate3 = await fred.get_risk_free_rate()
            print(f"   After cache clear: {float(rate3.rate) * 100:.2f}%")
            print(f"   New fetch (not same object): {rate is not rate3}")

    except FredServiceError as e:
        print(f"\n✗ Error: {e}")
        return

    print("\n" + "=" * 60)
    print("FRED API integration test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_fred_service())
