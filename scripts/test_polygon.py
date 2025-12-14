#!/usr/bin/env python3
"""Test script for Polygon.io API integration."""

import asyncio
from datetime import datetime
from decimal import Decimal

import sys
sys.path.insert(0, "src")

from trading_journal.services.polygon_service import PolygonService, PolygonServiceError


async def test_polygon_service():
    """Test Polygon service functionality."""
    print("=" * 60)
    print("Testing Polygon.io API Integration")
    print("=" * 60)

    try:
        async with PolygonService() as polygon:
            # Test 1: Check API status and subscription tier
            print("\n1. Checking API status and subscription...")
            status = await polygon.check_api_status()
            print(f"   Basic Access (stocks): {'✓ Available' if status['basic'] else '✗ Not available'}")
            print(f"   Options Access: {'✓ Available' if status['options'] else '✗ Requires Options Starter ($29/mo)'}")

            if not status["basic"]:
                print("   API key appears invalid. Check POLYGON_API_KEY in .env")
                return

            # Test 2: Get underlying price
            print("\n2. Fetching SPY price...")
            quote = await polygon.get_underlying_price("SPY")
            if quote:
                print(f"   Symbol: {quote.symbol}")
                print(f"   Price: ${quote.price}")
                print(f"   Open: ${quote.open}")
                print(f"   High: ${quote.high}")
                print(f"   Low: ${quote.low}")
                print(f"   Volume: {quote.volume:,}" if quote.volume else "   Volume: N/A")
            else:
                print("   Failed to get quote")

            # Test 3: Get option Greeks (requires Options Starter subscription)
            print("\n3. Fetching option Greeks...")
            if status["options"]:
                # Use ATM option based on current price
                current_price = quote.price if quote else Decimal("680")
                strike = Decimal(str(round(float(current_price) / 5) * 5))  # Round to nearest $5
                expiration = datetime(2025, 12, 19)  # Dec 2025 monthly (3rd Friday)

                print(f"   Looking for SPY {expiration.strftime('%b %d')} ${strike} Call...")
                greeks = await polygon.get_option_greeks(
                    underlying="SPY",
                    expiration=expiration,
                    option_type="C",
                    strike=strike,
                )

                if greeks:
                    print(f"   Delta: {greeks.delta}")
                    print(f"   Gamma: {greeks.gamma}")
                    print(f"   Theta: {greeks.theta}")
                    print(f"   Vega: {greeks.vega}")
                    print(f"   IV: {greeks.iv}")
                    print(f"   Underlying: ${greeks.underlying_price}")
                    print(f"   Option Price: ${greeks.option_price}")
                    print(f"   Bid: ${greeks.bid}")
                    print(f"   Ask: ${greeks.ask}")
                    print(f"   Spread: ${greeks.bid_ask_spread}")
                    print(f"   Open Interest: {greeks.open_interest:,}" if greeks.open_interest else "   OI: N/A")
                    print(f"   Volume: {greeks.volume:,}" if greeks.volume else "   Volume: N/A")
                else:
                    print("   No Greeks data found (option may be expired or not available)")
            else:
                print("   Skipped - requires Options Starter subscription")

            # Test 4: Get option chain snapshot (requires Options Starter subscription)
            print("\n4. Fetching option chain snapshot...")
            if status["options"]:
                expiration = datetime(2025, 12, 19)  # Dec 2025 monthly (3rd Friday)
                chain = await polygon.get_option_chain_snapshot(
                    underlying="SPY",
                    expiration_date=expiration,
                    contract_type="call",
                    limit=5,
                )
                print(f"   Found {len(chain)} contracts for {expiration.strftime('%b %d, %Y')}")
                for contract in chain[:3]:
                    details = contract.get("details", {})
                    greeks_data = contract.get("greeks", {})
                    print(f"   - Strike ${details.get('strike_price')}: delta={greeks_data.get('delta', 'N/A'):.4f}" if greeks_data.get('delta') else f"   - Strike ${details.get('strike_price')}")
            else:
                print("   Skipped - requires Options Starter subscription")

    except PolygonServiceError as e:
        print(f"\n✗ Error: {e}")
        return

    print("\n" + "=" * 60)
    print("Polygon.io integration test complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_polygon_service())
