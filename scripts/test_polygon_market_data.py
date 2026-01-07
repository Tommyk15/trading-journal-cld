#!/usr/bin/env python3
"""POC script to test Polygon market data fetching.

Run with: PYTHONPATH=src python scripts/test_polygon_market_data.py
"""

import asyncio
from decimal import Decimal
from datetime import datetime, timedelta

from trading_journal.services.polygon_service import PolygonService


async def test_polygon_market_data():
    """Test fetching market data from Polygon."""
    print("=" * 60)
    print("Polygon Market Data POC Test")
    print("=" * 60)

    try:
        service = PolygonService()
    except Exception as e:
        print(f"\n✗ Failed to initialize Polygon service: {e}")
        print("  Make sure POLYGON_API_KEY is set in .env")
        return

    async with service:
        # Test 1: Check API access
        print("\n[1] Checking API access...")
        status = await service.check_api_status()
        print(f"    Basic access: {'✓' if status['basic'] else '✗'}")
        print(f"    Options access: {'✓' if status['options'] else '✗'}")

        if not status['basic']:
            print("\n    ✗ No API access. Check your API key.")
            return

        # Test 2: Fetch stock price
        print("\n[2] Fetching stock price for SPY...")
        quote = await service.get_underlying_price("SPY")
        if quote:
            print(f"    Symbol: {quote.symbol}")
            print(f"    Price (prev close): ${quote.price}")
            print(f"    Open: ${quote.open}")
            print(f"    High: ${quote.high}")
            print(f"    Low: ${quote.low}")
            print(f"    Volume: {quote.volume:,}")
            print(f"    Timestamp: {quote.timestamp}")
        else:
            print("    ✗ No quote data returned")

        # Test 3: Fetch option Greeks (if options access)
        if status['options']:
            print("\n[3] Fetching option Greeks...")

            # Use a near-term SPY option
            exp_date = datetime.now() + timedelta(days=7)
            # Round to next Friday
            days_until_friday = (4 - exp_date.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            exp_date = exp_date + timedelta(days=days_until_friday)

            strike = round(float(quote.price) / 5) * 5  # Round to nearest $5

            print(f"    Testing: SPY {exp_date.strftime('%Y-%m-%d')} C{strike}")

            greeks = await service.get_option_greeks(
                underlying="SPY",
                expiration=exp_date,
                option_type="C",
                strike=Decimal(str(strike)),
                fetch_underlying_price=False,  # Already have it
            )

            if greeks:
                print(f"\n    Option Data:")
                print(f"    Delta: {greeks.delta}")
                print(f"    Gamma: {greeks.gamma}")
                print(f"    Theta: {greeks.theta}")
                print(f"    Vega: {greeks.vega}")
                print(f"    IV: {greeks.iv}")
                print(f"    Option price: ${greeks.option_price}")
                print(f"    Bid: ${greeks.bid}")
                print(f"    Ask: ${greeks.ask}")
                print(f"    Spread: ${greeks.bid_ask_spread}")
                print(f"    Open Interest: {greeks.open_interest}")
                print(f"    Volume: {greeks.volume}")
            else:
                print("    ✗ No Greeks data returned (option may not exist)")

            # Test 4: Option chain snapshot
            print("\n[4] Fetching option chain snapshot...")
            chain = await service.get_option_chain_snapshot(
                underlying="SPY",
                expiration_date=exp_date,
                strike_price_gte=Decimal(str(strike - 10)),
                strike_price_lte=Decimal(str(strike + 10)),
                limit=10,
            )
            print(f"    Found {len(chain)} contracts")

            for contract in chain[:3]:
                details = contract.get("details", {})
                day = contract.get("day", {})
                print(f"\n    {details.get('ticker', 'N/A')}")
                print(f"      Strike: {details.get('strike_price')}")
                print(f"      Type: {details.get('contract_type')}")
                print(f"      Close: ${day.get('close', 'N/A')}")
        else:
            print("\n[3] Skipping option tests (no options subscription)")

        print("\n" + "=" * 60)
        print("POC Test Complete!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_polygon_market_data())
