#!/usr/bin/env python3
"""Test the MarketDataService directly without running the API server.

Run with: PYTHONPATH=src python scripts/test_market_data_api.py
"""

import asyncio
from datetime import datetime
from decimal import Decimal

from trading_journal.services.market_data_service import MarketDataService


async def main():
    """Test MarketDataService."""
    print("=" * 70)
    print("MarketDataService Test")
    print("=" * 70)

    service = MarketDataService()

    async with service:
        # Test 1: Stock quote
        print("\n[1] Testing stock quote (BMNR)...")
        quote = await service.get_stock_quote("BMNR")
        print(f"    Price: ${float(quote.price):.2f}" if quote.price else "    Price: N/A")
        print(f"    Source: {quote.source.value}")

        # Test 2: Option data
        print("\n[2] Testing option data (BMNR 260116 $25 Put)...")
        opt_quote, greeks = await service.get_option_data(
            underlying="BMNR",
            expiration=datetime(2026, 1, 16),
            strike=Decimal("25"),
            option_type="P",
        )
        print(f"    Last: ${float(opt_quote.last):.2f}" if opt_quote.last else "    Last: N/A")
        print(f"    Delta: {float(greeks.delta):.4f}" if greeks.delta else "    Delta: N/A")
        print(f"    IV: {float(greeks.iv)*100:.1f}%" if greeks.iv else "    IV: N/A")
        print(f"    Source: {greeks.source.value}")

        # Test 3: Portfolio positions
        print("\n[3] Testing portfolio positions...")
        positions = await service.get_portfolio_positions()
        print(f"    Found {len(positions)} positions")
        if positions:
            total_unrealized = sum(float(p["unrealized_pnl"]) for p in positions)
            print(f"    Total Unrealized P&L: ${total_unrealized:,.2f}")

        # Test 4: Account P&L
        print("\n[4] Testing account P&L...")
        pnl = await service.get_account_pnl()
        if pnl:
            print(f"    Daily P&L: ${float(pnl['daily_pnl']):,.2f}" if pnl.get("daily_pnl") else "    Daily P&L: N/A")
            print(f"    Unrealized P&L: ${float(pnl['unrealized_pnl']):,.2f}" if pnl.get("unrealized_pnl") else "    Unrealized P&L: N/A")
        else:
            print("    Not connected to IBKR")

        # Test 5: Position market data
        print("\n[5] Testing position market data (BMNR Bull Put 25/30)...")
        position_data = await service.get_position_market_data(
            trade_id=999,
            underlying="BMNR",
            legs=[
                {"strike": Decimal("25"), "expiration": "20260116", "option_type": "P", "quantity": 40},
                {"strike": Decimal("30"), "expiration": "20260116", "option_type": "P", "quantity": -40},
            ],
            cost_basis=Decimal("-9577.40"),  # Credit received
        )
        print(f"    Underlying: ${float(position_data.underlying_price):.2f}" if position_data.underlying_price else "    Underlying: N/A")
        print(f"    Market Value: ${float(position_data.total_market_value):,.2f}" if position_data.total_market_value else "    Market Value: N/A")
        print(f"    Unrealized P&L: ${float(position_data.unrealized_pnl):,.2f}" if position_data.unrealized_pnl else "    Unrealized P&L: N/A")
        print(f"    Net Delta: {float(position_data.net_delta):.4f}" if position_data.net_delta else "    Net Delta: N/A")
        print(f"    Net Theta: ${float(position_data.net_theta)*100:.2f}/day" if position_data.net_theta else "    Net Theta: N/A")
        print(f"    Source: {position_data.source.value}")

    print("\n" + "=" * 70)
    print("Test Complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
